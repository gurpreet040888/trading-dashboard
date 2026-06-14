import json
import pandas as pd
import yfinance as yf

INPUT_FILE = "stocks.csv"
OUTPUT_FILE = "historical_prices.json"

stocks = pd.read_csv(INPUT_FILE)

result = {}
failed = []

for _, row in stocks.iterrows():
    ticker = str(row["ticker"]).strip()

    try:
        print(f"Downloading {ticker}")

        df = yf.download(
            ticker,
            period="3y",
            interval="1d",
            auto_adjust=True,
            progress=False
        )

        if df.empty:
            print(f"  Skipping {ticker} - no data (possibly delisted or bad ticker)")
            failed.append(ticker)
            continue

        # Safely extract Close as a 1D Series regardless of yfinance version
        close = df["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.squeeze()  # ensure it's always a Series

        close = close.ffill().dropna()

        if len(close) < 30:
            print(f"  Skipping {ticker} - insufficient history ({len(close)} days)")
            failed.append(ticker)
            continue

        result[ticker] = {
            "dates": [d.strftime("%Y-%m-%d") for d in close.index],
            "prices": [round(float(x), 2) for x in close.values.tolist()]  # .values.tolist() is safer
        }

        print(f"  ✓ Saved {ticker} ({len(close)} days)")

    except Exception as e:
        print(f"  ERROR {ticker}: {e}")
        failed.append(ticker)
        continue

with open(OUTPUT_FILE, "w") as f:
    json.dump(result, f, indent=2)

print(f"\n✓ Saved {len(result)} stocks")
if failed:
    print(f"✗ Failed ({len(failed)}): {failed}")