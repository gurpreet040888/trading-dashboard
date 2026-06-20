# 📊 MF Tracker India

A self-hosted mutual fund tracker for all 10,000+ Indian MFs with Smart Score rankings, daily auto-refresh, and holdings breakup.

---

## Features
- **All Indian Mutual Funds** from AMFI via [mfapi.in](https://api.mfapi.in)
- **Returns**: 1M, 3M, 6M, 1Y, 2Y, 3Y, 4Y, 5Y (CAGR for >1Y)
- **Smart Score** (0–100): weighted ranking for long-term mild-risk investors
  - 3Y Return (30%) · 1Y Return (15%) · 5Y Return (15%)
  - Sharpe Ratio (20%) · Consistency (10%) · Volatility (5%) · Max Drawdown (5%)
- **Top-5 per Category**: Large Cap, Mid Cap, Small Cap, Hybrid, ELSS, Debt, Index, etc.
- **Holdings Breakup**: sector allocation donut, asset allocation bars, top holdings table
- **Virtual Scroll**: shows top 100 per sort, loads more on scroll
- **Daily refresh** via GitHub Actions (Mon–Fri, 7 PM IST)

---

## File Structure

```
├── funds.html                      ← Main webapp (all funds + top-5)
├── fund_detail.html                ← Holdings breakup page
├── funds.json                      ← Generated daily (do not edit manually)
├── fetch_funds.py                  ← Data pipeline script
└── .github/workflows/
    └── fetch_funds.yml             ← GitHub Actions daily workflow
```

---

## Setup

### 1. Enable GitHub Pages
- Go to your repo → **Settings → Pages**
- Source: **Deploy from a branch** → Branch: `main`, Folder: `/ (root)`
- Save. Your site will be at `https://gurpreet040888.github.io/trading-dashboard/funds.html`

### 2. Run the first data fetch
The `funds.json` needs to be generated before the site works.

**Option A — Run locally:**
```bash
pip install requests
python fetch_funds.py
git add funds.json
git commit -m "Initial funds data"
git push
```

**Option B — Trigger GitHub Action manually:**
- Go to repo → **Actions → Fetch Indian MF Data → Run workflow**
- This will take ~30–60 minutes for all 10,000+ funds

### 3. Verify
- Open `https://gurpreet040888.github.io/trading-dashboard/funds.html`
- You should see the full fund table with Smart Scores

---

## Smart Score Formula

```
Smart Score =
  (3Y CAGR × 0.30) +        ← Core long-term return
  (1Y Return × 0.15) +       ← Recent momentum
  (5Y CAGR × 0.15) +         ← Long-term consistency
  (Sharpe Ratio × 0.20) +    ← Risk-adjusted return quality
  (Consistency × 0.10) +     ← % of years with positive return
  (Low Volatility × 0.05) +  ← Monthly NAV stability
  (Low Drawdown × 0.05)      ← Worst peak-to-trough loss
```

### Rating Labels
| Label | Score | Meaning |
|---|---|---|
| 🟢 Strong Pick | ≥ 75 | Excellent risk-adjusted returns, consistent |
| 🟡 Watch | 55–74 | Decent but monitor closely |
| 🔴 Avoid | < 55 | Poor risk-adjusted returns |

---

## GitHub Action Schedule

Runs Monday–Friday at **7:00 PM IST** (13:30 UTC).  
To trigger manually: Actions → Fetch Indian MF Data → Run workflow.

The action:
1. Fetches all fund metadata from mfapi.in
2. Downloads historical NAV for each fund
3. Calculates all returns, Sharpe, volatility, drawdown, Smart Score
4. Saves `funds.json` and commits it back to the repo
5. GitHub Pages serves the updated data automatically

---

## Notes

- **AUM data**: mfapi.in does not provide AUM. Smart Score uses fund age as a stability proxy.
- **Holdings data**: Available for most funds; loaded live from mfapi.in on the detail page.
- **Expense ratio / Alpha**: Not available from free sources; can be added later from AMFI factsheets.
- **First run time**: ~30–60 min for 10,000+ funds. Subsequent runs are same speed.
- **Rate limits**: The script uses 20 threads with batching to stay within mfapi.in limits.