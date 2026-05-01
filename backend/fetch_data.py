import yfinance as yf

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

    # 🔥 NEW: P&L vs your buy price
    if buy_price == 0:
        pnl_pct = 0
    else:
        pnl_pct = ((current - buy_price) / buy_price) * 100

    return {
        "ticker": ticker,
        "buy_price": buy_price,
        "current": round(current, 2),
        "avg7": round(avg7, 2),
        "avg14": round(avg14, 2),
        "avg30": round(avg30, 2),
        "pnl": round(pnl_pct, 2),
        "signals": signals or ["No signal"]
    }