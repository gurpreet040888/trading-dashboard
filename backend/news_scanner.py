import yfinance as yf
import json
import feedparser
import math

# ====================================
# MARKET WATCHLISTS
# ====================================

US_STOCKS = [
    "NVDA",
    "AMD",
    "MU",
    "AVGO",
    "PLTR",
    "META",
    "AMZN",
    "GOOGL",
    "MSFT",
    "SNOW",
    "TSLA",
    "NFLX",
    "COIN",
    "LLY",
    "NET",
    "CRWD",
    "PANW",
    "ARM",
    "SMCI",
    "ANET"
]

INDIA_STOCKS = [
    "RELIANCE.NS",
    "TCS.NS",
    "INFY.NS",
    "HAL.NS",
    "BEL.NS",
    "IRFC.NS",
    "RVNL.NS",
    "IREDA.NS",
    "TRENT.NS",
    "MCX.NS",
    "OLECTRA.NS",
    "COALINDIA.NS",
    "POWERGRID.NS",
    "ADANIPORTS.NS",
    "TATAELXSI.NS",
    "CDSL.NS",
    "KFINTECH.NS",
    "BSE.NS",
    "POLICYBZR.NS",
    "ZOMATO.NS"
]

WATCHLIST = US_STOCKS + INDIA_STOCKS

# ====================================
# SAFE VALUE HANDLER
# ====================================


def safe(value, default=0):

    try:

        if value is None:
            return default

        if isinstance(value, float):

            if math.isnan(value) or math.isinf(value):
                return default

        return round(float(value), 2)

    except:

        return default


# ====================================
# NEWS FETCHER
# ====================================


def get_news(ticker):

    try:

        url = (
            f"https://feeds.finance.yahoo.com/rss/2.0/headline"
            f"?s={ticker}&region=US&lang=en-US"
        )

        feed = feedparser.parse(url)

        news = []

        for entry in feed.entries[:5]:

            news.append({
                "title": entry.title,
                "link": entry.link
            })

        return news

    except Exception as e:

        print("News Error:", ticker, e)

        return []


# ====================================
# AI REASON DETECTOR
# ====================================


def detect_reason(news_items):

    text = " ".join(
        [x['title'].lower() for x in news_items]
    )

    score = 0

    reasons = []

    keywords = {
        "earnings": 25,
        "guidance": 20,
        "acquisition": 30,
        "ai": 20,
        "gpu": 20,
        "data center": 20,
        "contract": 15,
        "partnership": 15,
        "upgrade": 15,
        "beat": 20,
        "growth": 10,
        "government": 10,
        "cloud": 15,
        "semiconductor": 15,
        "chip": 15,
        "order win": 20,
        "capacity expansion": 20,
        "railway": 15,
        "defense": 15,
        "battery": 15
    }

    for word, pts in keywords.items():

        if word in text:

            reasons.append(word.title())

            score += pts

    return reasons, min(score, 100)


# ====================================
# STOCK ANALYZER
# ====================================


def analyze_stock(ticker):

    try:

        stock = yf.Ticker(ticker)

        df = stock.history(period="3mo")

        if df.empty:
            return None

        close = df["Close"]
        volume = df["Volume"]

        current = safe(close.iloc[-1])
        prev = safe(close.iloc[-2])

        avg20 = safe(close.tail(20).mean())
        avg50 = safe(close.tail(50).mean())

        # ============================
        # DAILY CHANGE
        # ============================

        if prev == 0:
            pct_change = 0
        else:
            pct_change = safe(
                ((current - prev) / prev) * 100
            )

        # ============================
        # MOMENTUM
        # ============================

        if avg20 == 0:
            momentum = 0
        else:
            momentum = safe(
                ((current - avg20) / avg20) * 100
            )

        # ============================
        # TREND STRENGTH
        # ============================

        if avg50 == 0:
            trend_strength = 0
        else:
            trend_strength = safe(
                ((current - avg50) / avg50) * 100
            )

        # ============================
        # VOLUME SPIKE
        # ============================

        avg_volume = volume.tail(20).mean()

        volume_spike = False

        try:

            volume_spike = (
                volume.iloc[-1] > avg_volume * 1.5
            )

        except:
            pass

        # ============================
        # FETCH NEWS
        # ============================

        news = get_news(ticker)

        reasons, news_score = detect_reason(news)

        # ============================
        # AI SCORE ENGINE
        # ============================

        total_score = 0

        if pct_change > 3:
            total_score += 20

        if momentum > 5:
            total_score += 25

        if trend_strength > 10:
            total_score += 15

        if volume_spike:
            total_score += 20

        total_score += news_score

        total_score = min(total_score, 100)

        # ============================
        # SIGNALS
        # ============================

        if total_score >= 85:
            signal = "🚀 STRONG CONTINUATION"

        elif total_score >= 70:
            signal = "🟢 HIGH MOMENTUM"

        elif total_score >= 50:
            signal = "🟡 BUILDING STRENGTH"

        elif total_score >= 30:
            signal = "⚪ WATCHLIST"

        else:
            signal = "🔴 WEAK"

        # ============================
        # LABELS
        # ============================

        labels = []

        if volume_spike:
            labels.append("Volume Spike")

        if momentum > 5:
            labels.append("Breakout")

        if trend_strength > 10:
            labels.append("Strong Trend")

        if news_score > 20:
            labels.append("News Catalyst")

        # ============================
        # RETURN DATA
        # ============================

        return {

            "ticker": ticker,

            "current": current,

            "change_pct": pct_change,

            "momentum": momentum,

            "trend_strength": trend_strength,

            "volume_spike": volume_spike,

            "score": total_score,

            "signal": signal,

            "labels": labels,

            "reasons": reasons if reasons else ["Momentum"],

            "news": news,

            "history": [
                safe(x)
                for x in close.tail(30).tolist()
            ]
        }

    except Exception as e:

        print("Error:", ticker, e)

        return None


# ====================================
# RUN SCANNER
# ====================================

results = []

for ticker in WATCHLIST:

    data = analyze_stock(ticker)

    if data:
        results.append(data)


# ====================================
# SORT BY SCORE
# ====================================

results = sorted(
    results,
    key=lambda x: x["score"],
    reverse=True
)


# ====================================
# SAVE JSON
# ====================================

with open("../news_data.json", "w") as f:

    json.dump(
        results,
        f,
        allow_nan=False
    )

print("news_data.json created successfully")