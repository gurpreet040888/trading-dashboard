#!/usr/bin/env python3
"""
Indian Mutual Fund Data Pipeline
Fetches all funds from mfapi.in, calculates returns, Smart Score, and saves funds.json
"""

import json
import time
import math
import logging
import requests
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

MFAPI_BASE = "https://api.mfapi.in/mf"
OUTPUT_FILE = "../funds.json"
MAX_WORKERS = 20
REQUEST_TIMEOUT = 15
DELAY_BETWEEN_BATCHES = 0.5

# Category classification keywords
CATEGORY_MAP = {
    "Large Cap": ["large cap", "largecap", "large-cap", "bluechip", "blue chip"],
    "Mid Cap": ["mid cap", "midcap", "mid-cap"],
    "Small Cap": ["small cap", "smallcap", "small-cap"],
    "Multi Cap": ["multi cap", "multicap", "multi-cap", "flexi cap", "flexicap"],
    "Large & Mid Cap": ["large & mid", "large and mid"],
    "ELSS": ["elss", "tax saver", "tax saving", "linked saving"],
    "Hybrid": ["hybrid", "balanced", "aggressive hybrid", "conservative hybrid", "equity savings", "arbitrage"],
    "Debt": ["debt", "liquid", "overnight", "ultra short", "short duration", "medium duration",
             "long duration", "gilt", "credit risk", "floater", "dynamic bond", "money market",
             "banking and psu", "corporate bond", "low duration"],
    "Index": ["index", "nifty", "sensex", "bse", "nse"],
    "International": ["international", "global", "overseas", "world", "us equity", "nasdaq", "s&p"],
    "Sectoral": ["sector", "pharma", "infra", "infrastructure", "banking", "fmcg", "technology",
                 "consumption", "energy", "healthcare", "realty", "psu"],
    "Thematic": ["thematic", "esg", "dividend", "value", "contra", "focused"],
    "Fund of Funds": ["fund of fund", "fof"],
    "Gold": ["gold"],
}

def classify_category(scheme_name: str, category_hint: str = "") -> str:
    text = (scheme_name + " " + category_hint).lower()
    for cat, keywords in CATEGORY_MAP.items():
        if any(kw in text for kw in keywords):
            return cat
    return "Other"

def fetch_all_funds():
    log.info("Fetching master fund list...")
    r = requests.get(MFAPI_BASE, timeout=REQUEST_TIMEOUT)
    r.raise_for_status()
    funds = r.json()
    log.info(f"Total funds: {len(funds)}")
    return funds

def fetch_nav_history(scheme_code: str):
    try:
        r = requests.get(f"{MFAPI_BASE}/{scheme_code}", timeout=REQUEST_TIMEOUT)
        if r.status_code != 200:
            return None
        data = r.json()
        meta = data.get("meta", {})
        nav_data = data.get("data", [])
        return meta, nav_data
    except Exception:
        return None

def parse_nav(nav_str):
    try:
        return float(str(nav_str).replace(",", "").strip())
    except:
        return None

def nav_on_or_before(nav_data, target_date):
    """Return NAV closest to but not after target_date"""
    for entry in nav_data:
        try:
            d = datetime.strptime(entry["date"], "%d-%m-%Y")
            if d <= target_date:
                return parse_nav(entry["nav"])
        except:
            continue
    return None

def calculate_returns(nav_data):
    if not nav_data:
        return {}

    now = datetime.now()
    latest_nav = parse_nav(nav_data[0]["nav"])
    if not latest_nav:
        return {}

    periods = {
        "1m": 30, "3m": 91, "6m": 182,
        "1y": 365, "2y": 730, "3y": 1095,
        "4y": 1460, "5y": 1825
    }

    returns = {}
    for key, days in periods.items():
        target = now - timedelta(days=days)
        past_nav = nav_on_or_before(nav_data, target)
        if past_nav and past_nav > 0:
            ret = ((latest_nav - past_nav) / past_nav) * 100
            # Annualize for periods > 1 year
            years = days / 365
            if years > 1:
                ret = (math.pow((latest_nav / past_nav), 1 / years) - 1) * 100
            returns[key] = round(ret, 2)
        else:
            returns[key] = None

    return returns

def calculate_volatility(nav_data, months=12):
    """Monthly std dev of returns over last N months"""
    if len(nav_data) < 30:
        return None
    monthly_returns = []
    now = datetime.now()
    for i in range(1, months + 1):
        t1 = now - timedelta(days=30 * i)
        t2 = now - timedelta(days=30 * (i - 1))
        n1 = nav_on_or_before(nav_data, t1)
        n2 = nav_on_or_before(nav_data, t2)
        if n1 and n2 and n1 > 0:
            monthly_returns.append((n2 - n1) / n1 * 100)
    if len(monthly_returns) < 3:
        return None
    mean = sum(monthly_returns) / len(monthly_returns)
    variance = sum((x - mean) ** 2 for x in monthly_returns) / len(monthly_returns)
    return round(math.sqrt(variance), 2)

def calculate_sharpe(nav_data, risk_free_rate=6.5):
    """Annualised Sharpe using monthly returns, risk-free = 6.5% p.a."""
    if len(nav_data) < 60:
        return None
    monthly_rf = risk_free_rate / 12
    monthly_returns = []
    now = datetime.now()
    for i in range(1, 37):  # 3 years
        t1 = now - timedelta(days=30 * i)
        t2 = now - timedelta(days=30 * (i - 1))
        n1 = nav_on_or_before(nav_data, t1)
        n2 = nav_on_or_before(nav_data, t2)
        if n1 and n2 and n1 > 0:
            monthly_returns.append((n2 - n1) / n1 * 100)
    if len(monthly_returns) < 12:
        return None
    mean = sum(monthly_returns) / len(monthly_returns)
    variance = sum((x - mean) ** 2 for x in monthly_returns) / len(monthly_returns)
    std = math.sqrt(variance)
    if std == 0:
        return None
    sharpe = ((mean - monthly_rf) / std) * math.sqrt(12)
    return round(sharpe, 2)

def calculate_max_drawdown(nav_data):
    """Max peak-to-trough drawdown over full history"""
    navs = []
    for entry in nav_data:
        v = parse_nav(entry["nav"])
        if v:
            navs.append(v)
    if len(navs) < 10:
        return None
    navs = navs[::-1]  # oldest first
    peak = navs[0]
    max_dd = 0
    for nav in navs:
        if nav > peak:
            peak = nav
        dd = (peak - nav) / peak * 100
        if dd > max_dd:
            max_dd = dd
    return round(max_dd, 2)

def calculate_consistency(nav_data):
    """% of calendar years (last 5) where fund gave positive return"""
    now = datetime.now()
    positive_years = 0
    total_years = 0
    for y in range(1, 6):
        start = now - timedelta(days=365 * y)
        end = now - timedelta(days=365 * (y - 1))
        n_start = nav_on_or_before(nav_data, start)
        n_end = nav_on_or_before(nav_data, end)
        if n_start and n_end and n_start > 0:
            total_years += 1
            if n_end > n_start:
                positive_years += 1
    if total_years == 0:
        return None
    return round((positive_years / total_years) * 100, 1)

def calculate_smart_score(ret, volatility, sharpe, max_drawdown, consistency, aum):
    """
    Weighted smart score out of 100 for long-term mild-risk investors
    """
    score = 0
    total_weight = 0

    # 3Y return (30%)
    if ret.get("3y") is not None:
        r3 = ret["3y"]
        s = min(max((r3 - 5) / 20 * 100, 0), 100)
        score += s * 0.30
        total_weight += 0.30

    # 1Y return (15%)
    if ret.get("1y") is not None:
        r1 = ret["1y"]
        s = min(max((r1 - 5) / 30 * 100, 0), 100)
        score += s * 0.15
        total_weight += 0.15

    # 5Y return (15%)
    if ret.get("5y") is not None:
        r5 = ret["5y"]
        s = min(max((r5 - 8) / 15 * 100, 0), 100)
        score += s * 0.15
        total_weight += 0.15

    # Sharpe ratio (20%)
    if sharpe is not None:
        s = min(max((sharpe + 0.5) / 2.5 * 100, 0), 100)
        score += s * 0.20
        total_weight += 0.20

    # Consistency (10%)
    if consistency is not None:
        score += consistency * 0.10
        total_weight += 0.10

    # Low volatility (5%) — lower is better, normalize 0-8% range
    if volatility is not None:
        s = min(max((8 - volatility) / 8 * 100, 0), 100)
        score += s * 0.05
        total_weight += 0.05

    # Low drawdown (5%) — lower is better
    if max_drawdown is not None:
        s = min(max((60 - max_drawdown) / 60 * 100, 0), 100)
        score += s * 0.05
        total_weight += 0.05

    if total_weight < 0.3:
        return None

    normalized = score / total_weight
    return round(normalized, 1)

def score_label(score):
    if score is None:
        return "N/A", "neutral"
    if score >= 75:
        return "Strong Pick", "strong"
    if score >= 55:
        return "Watch", "watch"
    return "Avoid", "avoid"

def process_fund(fund):
    scheme_code = str(fund.get("schemeCode", ""))
    scheme_name = fund.get("schemeName", "")

    result = fetch_nav_history(scheme_code)
    if not result:
        return None
    meta, nav_data = result

    if not nav_data or len(nav_data) < 30:
        return None

    latest_nav = parse_nav(nav_data[0]["nav"])
    if not latest_nav:
        return None

    nav_date = nav_data[0].get("date", "")
    isin = meta.get("isin_growth", meta.get("isin_div_reinvestment", ""))
    amc = meta.get("fund_house", "")
    scheme_type = meta.get("scheme_type", "")
    scheme_category = meta.get("scheme_category", "")

    category = classify_category(scheme_name, scheme_category)

    returns = calculate_returns(nav_data)
    volatility = calculate_volatility(nav_data)
    sharpe = calculate_sharpe(nav_data)
    max_drawdown = calculate_max_drawdown(nav_data)
    consistency = calculate_consistency(nav_data)

    # AUM placeholder — mfapi doesn't provide this, we'll use fund age as proxy for stability
    fund_age_days = len(nav_data)
    aum_proxy = min(fund_age_days / 3650 * 100, 100)  # normalize to 0-100

    smart_score = calculate_smart_score(returns, volatility, sharpe, max_drawdown, consistency, aum_proxy)
    label, label_class = score_label(smart_score)

    return {
        "schemeCode": scheme_code,
        "schemeName": scheme_name,
        "isin": isin,
        "amc": amc,
        "category": category,
        "schemeCategory": scheme_category,
        "nav": latest_nav,
        "navDate": nav_date,
        "returns": returns,
        "volatility": volatility,
        "sharpe": sharpe,
        "maxDrawdown": max_drawdown,
        "consistency": consistency,
        "smartScore": smart_score,
        "smartLabel": label,
        "smartLabelClass": label_class,
        "dataPoints": len(nav_data),
    }

def compute_top5_per_category(funds):
    from collections import defaultdict
    by_cat = defaultdict(list)
    for f in funds:
        if f.get("smartScore") is not None and f.get("returns", {}).get("3y") is not None:
            by_cat[f["category"]].append(f)

    top5 = {}
    for cat, items in by_cat.items():
        sorted_items = sorted(items, key=lambda x: x["smartScore"], reverse=True)
        top5[cat] = [
            {
                "schemeCode": f["schemeCode"],
                "schemeName": f["schemeName"],
                "isin": f["isin"],
                "amc": f["amc"],
                "nav": f["nav"],
                "returns": f["returns"],
                "smartScore": f["smartScore"],
                "smartLabel": f["smartLabel"],
                "smartLabelClass": f["smartLabelClass"],
                "volatility": f["volatility"],
                "sharpe": f["sharpe"],
                "maxDrawdown": f["maxDrawdown"],
                "consistency": f["consistency"],
            }
            for f in sorted_items[:5]
        ]

    return top5

def main():
    start = time.time()
    all_funds_list = fetch_all_funds()

    processed = []
    failed = 0
    batch_size = 100

    log.info(f"Processing {len(all_funds_list)} funds with {MAX_WORKERS} workers...")

    for i in range(0, len(all_funds_list), batch_size):
        batch = all_funds_list[i:i + batch_size]
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(process_fund, f): f for f in batch}
            for future in as_completed(futures):
                try:
                    result = future.result()
                    if result:
                        processed.append(result)
                except Exception as e:
                    failed += 1

        log.info(f"Progress: {min(i + batch_size, len(all_funds_list))}/{len(all_funds_list)} | Processed: {len(processed)} | Failed: {failed}")
        time.sleep(DELAY_BETWEEN_BATCHES)

    top5 = compute_top5_per_category(processed)

    output = {
        "lastUpdated": datetime.now().strftime("%Y-%m-%d %H:%M:%S IST"),
        "totalFunds": len(processed),
        "funds": processed,
        "top5PerCategory": top5,
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, separators=(",", ":"))

    elapsed = time.time() - start
    log.info(f"Done! {len(processed)} funds saved to {OUTPUT_FILE} in {elapsed:.1f}s")

if __name__ == "__main__":
    main()