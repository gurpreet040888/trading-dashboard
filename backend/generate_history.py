import json
import pandas as pd
import yfinance as yf

INPUT_FILE = "stocks.csv"
OUTPUT_FILE = "historical_prices.json"

stocks = pd.read_csv(INPUT_FILE)

result = {}

for _, row in stocks.iterrows():

ticker = row["ticker"]

try:

    print(f"Downloading {ticker}")

    df = yf.download(
        ticker,
        period="3y",
        interval="1d",
        progress=False,
        auto_adjust=True
    )

    if df.empty:
        print(f"Skipping {ticker}")
        continue

    close = df["Close"].fillna(method="ffill")

    result[ticker] = {
        "dates": [
            d.strftime("%Y-%m-%d")
            for d in close.index
        ],
        "prices": [
            round(float(x), 2)
            for x in close.tolist()
        ]
    }

except Exception as e:
    print("Error:", ticker, e)

with open(OUTPUT_FILE, "w") as f:
json.dump(result, f)

print(f"Saved {len(result)} stocks")
