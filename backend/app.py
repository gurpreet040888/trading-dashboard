from flask import Flask, jsonify
from fetch_data import analyze_stock

app = Flask(__name__)

STOCKS = ["AAPL", "MSFT", "RELIANCE.NS", "TCS.NS", "^NSEI"]

@app.route("/data")
def get_data():
    results = []

    for stock in STOCKS:
        data = analyze_stock(stock)
        if data:
            results.append(data)

    return jsonify(results)

if __name__ == "__main__":
    app.run()