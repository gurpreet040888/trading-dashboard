import yfinance as yf

THRESHOLD = 0.10

def analyze_stock(ticker):
    df = yf.Ticker(ticker).history(period="6mo", interval="1d")

    if df.empty:
        return None

    current = df["Close"].iloc[-1]
    high = df["High"].iloc[-1]
    low = df["Low"].iloc[-1]

    ranges = {"7d":7, "15d":15, "1m":30, "6m":180}
    signals = []

    for label, days in ranges.items():
        subset = df.tail(days)
        max_p = subset["Close"].max()
        min_p = subset["Close"].min()

        if (current - max_p)/max_p >= THRESHOLD:
            signals.append(f"{label} breakout")
        if (current - min_p)/min_p <= -THRESHOLD:
            signals.append(f"{label} dip")

    return {
        "ticker": ticker,
        "current": round(current, 2),
        "high": round(high, 2),
        "low": round(low, 2),
        "signals": signals or ["No alert"]
    }