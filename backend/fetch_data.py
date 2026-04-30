import yfinance as yf

THRESHOLD = 0.10

def analyze_stock(ticker):
    df = yf.Ticker(ticker).history(period="2mo", interval="1d")

    if df.empty:
        return None

    close = df["Close"]

    current = close.iloc[-1]

    avg_7 = close.tail(7).mean()
    avg_14 = close.tail(14).mean()
    avg_30 = close.tail(30).mean()

    signals = []

    def check(avg, label):
        diff = (current - avg) / avg

        if diff >= THRESHOLD:
            signals.append(f"{label}: 🔺 +{diff*100:.1f}% above avg")
        elif diff <= -THRESHOLD:
            signals.append(f"{label}: 🔻 {diff*100:.1f}% below avg")

    check(avg_7, "7d")
    check(avg_14, "14d")
    check(avg_30, "30d")

    return {
        "ticker": ticker,
        "current": round(current, 2),
        "avg7": round(avg_7, 2),
        "avg14": round(avg_14, 2),
        "avg30": round(avg_30, 2),
        "signals": signals or ["No signal"]
    }