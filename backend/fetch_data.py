import yfinance as yf
import numpy as np

THRESHOLD = 0.10

def analyze_stock(ticker, buy_price):
    df = yf.Ticker(ticker).history(period="2mo", interval="1d")

    if df.empty:
        return None

    close = df["Close"]
    current = close.iloc[-1]

    avg7 = close.tail(7).mean()
    avg14 = close.tail(14).mean()
    avg30 = close.tail(30).mean()

    signals = []

    def check(avg, label):
        diff = (current - avg) / avg

        if diff >= THRESHOLD:
            signals.append(f"{label}: 🔺 +{diff*100:.1f}%")
        elif diff <= -THRESHOLD:
            signals.append(f"{label}: 🔻 {diff*100:.1f}%")

    check(avg7, "7d")
    check(avg14, "14d")
    check(avg30, "30d")

    # =========================
    # 📈 P&L vs buy price (SAFE)
    # =========================
    if buy_price == 0:
        pnl_pct = 0
    else:
        pnl_pct = ((current - buy_price) / buy_price) * 100

    # =========================
    # 🧠 RSI Calculation
    # =========================
    delta = close.diff()

    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    # avoid divide-by-zero
    rs = avg_gain / avg_loss.replace(0, np.nan)

    rsi = 100 - (100 / (1 + rs))
    rsi_value = round(rsi.iloc[-1], 2) if not np.isnan(rsi.iloc[-1]) else 50

    # =========================
    # 🤖 AI SCORING ENGINE
    # =========================
    score = 0
    reasons = []

    # Undervalued / Overvalued (30D baseline)
    if current < avg30 * 0.9:
        score += 2
        reasons.append("Below 30D avg")

    if current > avg30 * 1.1:
        score -= 2
        reasons.append("Above 30D avg")

    # RSI signals
    if rsi_value < 35:
        score += 2
        reasons.append("Oversold (RSI)")

    if rsi_value > 70:
        score -= 2
        reasons.append("Overbought (RSI)")

    # Trend signals
    if avg7 > avg14:
        score += 1
        reasons.append("Uptrend")

    if avg7 < avg14:
        score -= 1
        reasons.append("Downtrend")

    # =========================
    # 🏷 Recommendation
    # =========================
    if score >= 3:
        recommendation = "STRONG BUY"
    elif score >= 1:
        recommendation = "BUY"
    elif score <= -3:
        recommendation = "STRONG SELL"
    elif score <= -1:
        recommendation = "SELL"
    else:
        recommendation = "HOLD"

    # =========================
    # 📦 Final Output (extended)
    # =========================
    return {
        "ticker": ticker,
        "buy_price": buy_price,
        "current": round(current, 2),
        "avg7": round(avg7, 2),
        "avg14": round(avg14, 2),
        "avg30": round(avg30, 2),
        "pnl": round(pnl_pct, 2),
        "signals": signals or ["No signal"],

        # 🔥 NEW FIELDS (used in ai.html)
        "rsi": rsi_value,
        "ai_score": score,
        "recommendation": recommendation,
        "reasons": reasons or ["Neutral"],
        "history": close.tail(30).round(2).tolist()
    }