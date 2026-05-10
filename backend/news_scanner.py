import yfinance as yf

        pct_change = round(((current-prev)/prev)*100,2)

        avg20 = close.tail(20).mean()

        volume_spike = volume.iloc[-1] > volume.tail(20).mean()*1.5

        momentum = round(((current-avg20)/avg20)*100,2)

        news = get_news(ticker)

        reasons, news_score = detect_reason(news)

        total_score = 0

        if pct_change > 3:
            total_score += 20

        if momentum > 5:
            total_score += 25

        if volume_spike:
            total_score += 20

        total_score += news_score

        total_score = min(total_score, 100)

        if total_score >= 80:
            signal = "🚀 VERY HIGH"
        elif total_score >= 60:
            signal = "🟢 HIGH"
        elif total_score >= 40:
            signal = "🟡 MEDIUM"
        else:
            signal = "⚪ LOW"

        return {
            "ticker": ticker,
            "current": round(current,2),
            "change_pct": pct_change,
            "momentum": momentum,
            "volume_spike": volume_spike,
            "score": total_score,
            "signal": signal,
            "reasons": reasons,
            "news": news,
            "history": close.tail(30).round(2).tolist()
        }

    except Exception as e:
        print("Error", ticker, e)
        return None


results = []

for ticker in WATCHLIST:
    r = analyze_stock(ticker)

    if r:
        results.append(r)

results = sorted(results, key=lambda x: x["score"], reverse=True)

with open("news_data.json", "w") as f:
    json.dump(results, f)

print("news_data.json created")