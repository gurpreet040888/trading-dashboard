#!/usr/bin/env python3
"""
Indian Mutual Fund Incremental Data Pipeline
- Reads existing funds.csv (if present)
- Only refreshes funds not updated in last 7 days
- Writes progress to CSV every 50 funds (crash-safe)
- Rebuilds funds.json from full CSV at end
- Designed to run 4x/day, 55 min each
"""

import json
import math
import time
import logging
import os
import csv
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MFAPI_BASE       = "https://api.mfapi.in/mf"
CSV_FILE         = os.path.join(os.path.dirname(__file__), "../funds.csv")
JSON_FILE        = os.path.join(os.path.dirname(__file__), "../funds.json")
MAX_WORKERS      = 15
REQUEST_TIMEOUT  = 15
STALE_DAYS       = 7        # re-fetch if older than this
RUN_MINUTES      = 25       # safety ceiling — should finish well within this for ~2,400 funds
SAVE_EVERY       = 50       # write CSV checkpoint every N funds processed

CSV_FIELDS = [
    "schemeCode","schemeName","isin","amc","category","schemeCategory",
    "nav","navDate","dataPoints",
    "ret_1m","ret_3m","ret_6m","ret_1y","ret_2y","ret_3y","ret_4y","ret_5y",
    "volatility","sharpe","maxDrawdown","consistency",
    "smartScore","smartLabel","smartLabelClass",
    "last_updated",
]

# ── Category classification ──────────────────────────────────────────────────
CATEGORY_MAP = {
    "Large Cap":       ["large cap","largecap","large-cap","bluechip","blue chip"],
    "Mid Cap":         ["mid cap","midcap","mid-cap"],
    "Small Cap":       ["small cap","smallcap","small-cap"],
    "Multi Cap":       ["multi cap","multicap","multi-cap","flexi cap","flexicap"],
    "Large & Mid Cap": ["large & mid","large and mid"],
    "ELSS":            ["elss","tax saver","tax saving","linked saving"],
    "Hybrid":          ["hybrid","balanced","aggressive hybrid","conservative hybrid",
                        "equity savings","arbitrage","asset allocator","multi asset"],
    "Debt":            ["debt","liquid","overnight","ultra short","short duration",
                        "medium duration","long duration","gilt","credit risk","floater",
                        "dynamic bond","money market","banking and psu","corporate bond",
                        "low duration","medium to long"],
    "Index / ETF":     ["index","nifty","sensex","bse","nse","etf","s&p","nasdaq",
                        "dow jones","hang seng","crisil"],
    "International":   ["international","global","overseas","world","us equity",
                        "greater china","europe","japan","emerging market","em equity"],
    "Sectoral":        ["pharma","infra","infrastructure","banking","fmcg","technology",
                        "consumption","energy","healthcare","realty","psu","it fund",
                        "financial services","defence","manufacturing","auto","automobile",
                        "chemical","textile","steel","metal","mining","cement","media",
                        "telecom","utilities","power","digital","resources","commodities",
                        "agri","agriculture","rural","transportation","logistics",
                        "hospitality","retail","export","quant","consumer","services","business"],
    "Thematic":        ["thematic","esg","value","contra","focused","opportunities",
                        "innovation","pioneer","special situation","business cycle",
                        "next generation","future","new age","momentum","alpha",
                        "dividend yield","equity savings","quantitative"],
    "Fund of Funds":   ["fund of fund","fof"],
    "Gold":            ["gold","silver"],
}

def classify_category(name, hint=""):
    text = (name + " " + hint).lower()
    for cat, kws in CATEGORY_MAP.items():
        if any(k in text for k in kws):
            return cat
    return "Other"

# ── CSV helpers ──────────────────────────────────────────────────────────────
def load_csv():
    """Returns dict: schemeCode -> row dict"""
    existing = {}
    if not os.path.exists(CSV_FILE):
        return existing
    with open(CSV_FILE, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            existing[row["schemeCode"]] = row
    log.info(f"Loaded {len(existing)} existing records from CSV")
    return existing

def save_csv(records: dict):
    """Write full CSV from records dict"""
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        w.writeheader()
        w.writerows(records.values())

def is_stale(row):
    lu = row.get("last_updated","")
    if not lu:
        return True
    try:
        dt = datetime.strptime(lu, "%Y-%m-%d %H:%M:%S")
        return datetime.now() - dt > timedelta(days=STALE_DAYS)
    except:
        return True

# ── MF API helpers ───────────────────────────────────────────────────────────
def is_relevant_fund(name: str) -> tuple:
    """
    Keep only: Direct Plan + Growth option + Open-ended funds.
    Filters out ~92% of the mfapi list which is noise:
      - Regular plans (higher expense ratio, inferior to Direct)
      - IDCW / Dividend variants (same fund, different payout)
      - FMPs / Fixed Maturity Plans (closed-ended, matured)
      - Interval / Capital Protection / Close-ended schemes
      - Segregated portfolios (credit event haircuts, not investable)
      - Sweep / Bonus plans
    """
    n = name.lower()

    if "direct" not in n:
        return False, "Regular plan"

    for t in ["idcw", "dividend", "payout", "reinvestment", "bonus"]:
        if t in n:
            return False, "Dividend/IDCW variant"

    for t in ["fmp", "fixed maturity", "fixed term"]:
        if t in n:
            return False, "FMP"

    for t in ["interval", "capital protection", "close ended", "closed ended", "dual advantage"]:
        if t in n:
            return False, "Closed-ended"

    if "segregated" in n:
        return False, "Segregated portfolio"

    if "sweep" in n:
        return False, "Sweep plan"

    return True, "OK"


def fetch_all_fund_list():
    log.info("Fetching master fund list from mfapi.in …")
    r = requests.get(MFAPI_BASE, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    all_funds = r.json()
    log.info(f"Total funds in master list: {len(all_funds)}")

    filtered = [f for f in all_funds if is_relevant_fund(f.get("schemeName", ""))[0]]
    skipped = len(all_funds) - len(filtered)
    log.info(f"After filter -> keeping {len(filtered)} funds "
             f"(removed {skipped} inactive/duplicate/regular-plan funds)")
    return filtered

def fetch_nav_history(scheme_code):
    try:
        r = requests.get(f"{MFAPI_BASE}/{scheme_code}", timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        d = r.json()
        return d.get("meta", {}), d.get("data", [])
    except:
        return None

def parse_nav(s):
    try:
        return float(str(s).replace(",","").strip())
    except:
        return None

def nav_on_or_before(nav_data, target):
    for e in nav_data:
        try:
            d = datetime.strptime(e["date"], "%d-%m-%Y")
            if d <= target:
                return parse_nav(e["nav"])
        except:
            continue
    return None

# ── Calculations ─────────────────────────────────────────────────────────────
def calc_returns(nav_data):
    if not nav_data:
        return {}
    now = datetime.now()
    latest = parse_nav(nav_data[0]["nav"])
    if not latest:
        return {}
    periods = {"1m":30,"3m":91,"6m":182,"1y":365,"2y":730,"3y":1095,"4y":1460,"5y":1825}
    out = {}
    for k, days in periods.items():
        past = nav_on_or_before(nav_data, now - timedelta(days=days))
        if past and past > 0:
            yrs = days / 365
            ret = ((latest - past) / past) * 100
            if yrs > 1:
                ret = (math.pow(latest / past, 1/yrs) - 1) * 100
            out[k] = round(ret, 2)
        else:
            out[k] = None
    return out

def calc_volatility(nav_data, months=12):
    now = datetime.now()
    rets = []
    for i in range(1, months+1):
        n1 = nav_on_or_before(nav_data, now - timedelta(days=30*i))
        n2 = nav_on_or_before(nav_data, now - timedelta(days=30*(i-1)))
        if n1 and n2 and n1 > 0:
            rets.append((n2-n1)/n1*100)
    if len(rets) < 3:
        return None
    mean = sum(rets)/len(rets)
    return round(math.sqrt(sum((x-mean)**2 for x in rets)/len(rets)), 2)

def calc_sharpe(nav_data, rf=6.5):
    now = datetime.now()
    mrf = rf / 12
    rets = []
    for i in range(1, 37):
        n1 = nav_on_or_before(nav_data, now - timedelta(days=30*i))
        n2 = nav_on_or_before(nav_data, now - timedelta(days=30*(i-1)))
        if n1 and n2 and n1 > 0:
            rets.append((n2-n1)/n1*100)
    if len(rets) < 12:
        return None
    mean = sum(rets)/len(rets)
    std  = math.sqrt(sum((x-mean)**2 for x in rets)/len(rets))
    return round(((mean-mrf)/std)*math.sqrt(12), 2) if std else None

def calc_max_drawdown(nav_data):
    navs = [parse_nav(e["nav"]) for e in nav_data if parse_nav(e["nav"])]
    if len(navs) < 10:
        return None
    navs = navs[::-1]
    peak, mx = navs[0], 0
    for v in navs:
        peak = max(peak, v)
        mx = max(mx, (peak-v)/peak*100)
    return round(mx, 2)

def calc_consistency(nav_data):
    now = datetime.now()
    pos = tot = 0
    for y in range(1, 6):
        n1 = nav_on_or_before(nav_data, now - timedelta(days=365*y))
        n2 = nav_on_or_before(nav_data, now - timedelta(days=365*(y-1)))
        if n1 and n2 and n1 > 0:
            tot += 1
            if n2 > n1:
                pos += 1
    return round(pos/tot*100, 1) if tot else None

def calc_smart_score(ret, vol, sharpe, dd, cons):
    score = wt = 0
    def add(val, lo, hi, weight):
        nonlocal score, wt
        if val is None:
            return
        s = min(max((val-lo)/(hi-lo)*100, 0), 100)
        score += s * weight
        wt    += weight

    add(ret.get("3y"),    5,  25, 0.30)
    add(ret.get("1y"),    5,  35, 0.15)
    add(ret.get("5y"),    8,  23, 0.15)
    add(sharpe,          -0.5, 2,  0.20)
    add(cons,             0, 100, 0.10)
    if vol is not None:
        add(8-vol,        0,   8, 0.05)
    if dd is not None:
        add(60-dd,        0,  60, 0.05)

    return round(score/wt, 1) if wt >= 0.3 else None

def score_label(s):
    if s is None:   return "N/A", "neutral"
    if s >= 75:     return "Strong Pick", "strong"
    if s >= 55:     return "Watch", "watch"
    return "Avoid", "avoid"

# ── Process one fund ─────────────────────────────────────────────────────────
def process_fund(fund):
    code = str(fund.get("schemeCode",""))
    name = fund.get("schemeName","")

    result = fetch_nav_history(code)
    if not result:
        return None
    meta, nav_data = result
    if not nav_data or len(nav_data) < 30:
        return None

    latest = parse_nav(nav_data[0]["nav"])
    if not latest:
        return None

    ret  = calc_returns(nav_data)
    vol  = calc_volatility(nav_data)
    sh   = calc_sharpe(nav_data)
    dd   = calc_max_drawdown(nav_data)
    cons = calc_consistency(nav_data)
    ss   = calc_smart_score(ret, vol, sh, dd, cons)
    lbl, lcls = score_label(ss)

    return {
        "schemeCode":     code,
        "schemeName":     name,
        "isin":           meta.get("isin_growth", meta.get("isin_div_reinvestment","")),
        "amc":            meta.get("fund_house",""),
        "category":       classify_category(name, meta.get("scheme_category","")),
        "schemeCategory": meta.get("scheme_category",""),
        "nav":            latest,
        "navDate":        nav_data[0].get("date",""),
        "dataPoints":     len(nav_data),
        "ret_1m":  ret.get("1m"), "ret_3m":  ret.get("3m"),
        "ret_6m":  ret.get("6m"), "ret_1y":  ret.get("1y"),
        "ret_2y":  ret.get("2y"), "ret_3y":  ret.get("3y"),
        "ret_4y":  ret.get("4y"), "ret_5y":  ret.get("5y"),
        "volatility":     vol,
        "sharpe":         sh,
        "maxDrawdown":    dd,
        "consistency":    cons,
        "smartScore":     ss,
        "smartLabel":     lbl,
        "smartLabelClass":lcls,
        "last_updated":   datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }

# ── Build JSON from CSV records ───────────────────────────────────────────────
def build_json(records: dict):
    def flt(v):
        try:    return float(v) if v not in (None,"","None") else None
        except: return None

    funds = []
    for r in records.values():
        funds.append({
            "schemeCode":      r["schemeCode"],
            "schemeName":      r["schemeName"],
            "isin":            r["isin"],
            "amc":             r["amc"],
            "category":        r["category"],
            "schemeCategory":  r["schemeCategory"],
            "nav":             flt(r["nav"]),
            "navDate":         r["navDate"],
            "returns": {
                "1m": flt(r["ret_1m"]), "3m": flt(r["ret_3m"]),
                "6m": flt(r["ret_6m"]), "1y": flt(r["ret_1y"]),
                "2y": flt(r["ret_2y"]), "3y": flt(r["ret_3y"]),
                "4y": flt(r["ret_4y"]), "5y": flt(r["ret_5y"]),
            },
            "volatility":      flt(r["volatility"]),
            "sharpe":          flt(r["sharpe"]),
            "maxDrawdown":     flt(r["maxDrawdown"]),
            "consistency":     flt(r["consistency"]),
            "smartScore":      flt(r["smartScore"]),
            "smartLabel":      r["smartLabel"],
            "smartLabelClass": r["smartLabelClass"],
            "last_updated":    r["last_updated"],
        })

    # Top-5 per category
    from collections import defaultdict
    by_cat = defaultdict(list)
    for f in funds:
        if f["smartScore"] and f["returns"].get("3y"):
            by_cat[f["category"]].append(f)

    top5 = {}
    for cat, items in by_cat.items():
        top5[cat] = sorted(items, key=lambda x: x["smartScore"], reverse=True)[:5]

    out = {
        "lastUpdated":   datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "totalFunds":    len(funds),
        "totalInCSV":    len(records),
        "funds":         funds,
        "top5PerCategory": top5,
    }
    with open(JSON_FILE, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, separators=(",",":"))
    log.info(f"funds.json written with {len(funds)} funds")

# ── Main ─────────────────────────────────────────────────────────────────────
def main():
    start   = time.time()
    cutoff  = start + RUN_MINUTES * 60

    # 1. Load existing CSV
    records = load_csv()

    # 2. Get full master list
    all_funds = fetch_all_fund_list()

    # 3. Determine which funds need refreshing
    stale = [f for f in all_funds if is_stale(records.get(str(f["schemeCode"]),{}))]
    log.info(f"Stale / never-fetched funds: {len(stale)} out of {len(all_funds)}")

    if not stale:
        log.info("All funds are fresh — rebuilding JSON and exiting.")
        build_json(records)
        return

    # 4. Process stale funds in batches, checkpoint every SAVE_EVERY
    processed = 0
    failed    = 0
    pending   = []   # buffer before checkpoint write

    def flush(force=False):
        nonlocal pending
        if not pending:
            return
        if force or len(pending) >= SAVE_EVERY:
            for r in pending:
                records[r["schemeCode"]] = r
            save_csv(records)
            log.info(f"  ✔ Checkpoint saved — {len(records)} total records in CSV")
            pending = []

    batch_size = 50
    for i in range(0, len(stale), batch_size):
        if time.time() >= cutoff:
            log.info("⏱ Time limit reached — saving checkpoint and exiting.")
            flush(force=True)
            break

        batch = stale[i:i+batch_size]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
            futures = {ex.submit(process_fund, f): f for f in batch}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        pending.append(result)
                        processed += 1
                    else:
                        failed += 1
                except Exception as e:
                    failed += 1

        flush()

        elapsed = (time.time() - start) / 60
        remaining = len(stale) - i - len(batch)
        log.info(f"Progress: {min(i+batch_size, len(stale))}/{len(stale)} stale | "
                 f"Done: {processed} | Failed: {failed} | "
                 f"Elapsed: {elapsed:.1f}m | CSV total: {len(records)}")

    flush(force=True)

    # 5. Rebuild JSON from full CSV
    log.info("Rebuilding funds.json from full CSV …")
    build_json(records)

    elapsed = (time.time() - start) / 60
    log.info(f"Run complete. Processed {processed} funds in {elapsed:.1f} min. "
             f"Total in CSV: {len(records)}")

if __name__ == "__main__":
    main()