import requests
import time
import numpy as np
from datetime import datetime

TELEGRAM_TOKEN = "8608021789:AAEUUZiHs3j8e1Xv5lbuEyMhpylpfkxe7HE"
CHAT_ID = "5259562355"

MIN_24H = 8

# ==========================================
# TELEGRAM
# ==========================================

def send(text):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": text
        },
        timeout=10
    )

# ==========================================
# RSI
# ==========================================

def calc_rsi(closes, period=14):

    if len(closes) < period + 1:
        return None

    deltas = np.diff(closes)

    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(gains)):

        avg_gain = (
            avg_gain * (period - 1)
            + gains[i]
        ) / period

        avg_loss = (
            avg_loss * (period - 1)
            + losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return round(
        100 - (100 / (1 + rs)),
        1
    )

# ==========================================
# GET TOP GAINERS
# ==========================================

def get_gainers():

    url = "https://api.coingecko.com/api/v3/coins/markets"

    params = {
        "vs_currency": "usd",
        "order": "price_change_percentage_24h_desc",
        "per_page": 50,
        "page": 1,
        "sparkline": False
    }

    r = requests.get(
        url,
        params=params,
        timeout=20
    )

    data = r.json()

    results = []

    for c in data:

        try:

            change = c.get(
                "price_change_percentage_24h",
                0
            )

            volume = c.get(
                "total_volume",
                0
            )

            if change < MIN_24H:
                continue

            if volume < 5_000_000:
                continue

            results.append({
                "id": c["id"],
                "symbol": c["symbol"].upper(),
                "name": c["name"],
                "price": c["current_price"],
                "change": round(change, 2),
                "volume": volume
            })

        except:
            continue

    return results[:20]

# ==========================================
# GET CHART
# ==========================================

def get_chart(coin_id):

    url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"

    params = {
        "vs_currency": "usd",
        "days": "1",
        "interval": "hourly"
    }

    r = requests.get(
        url,
        params=params,
        timeout=20
    )

    data = r.json()

    prices = data["prices"]

    closes = [p[1] for p in prices]

    return closes

# ==========================================
# MAIN
# ==========================================

def main():

    now = datetime.utcnow().strftime(
        "%H:%M UTC %d/%m/%Y"
    )

    try:

        gainers = get_gainers()

    except Exception as e:

        send(f"❌ API ERROR\n{e}")

        return

    if not gainers:

        send("❌ No gainers found")

        return

    send(
        f"🔥 Alpha Scanner Started\n"
        f"{len(gainers)} gainers\n"
        f"{now}"
    )

    for c in gainers:

        try:

            closes = get_chart(c["id"])

            rsi = calc_rsi(closes)

            if not rsi:
                continue

            if rsi < 70:
                continue

            level = "🚨"

            if rsi >= 85:
                level = "🚨🚨🚨"

            elif rsi >= 78:
                level = "🚨🚨"

            msg = f"""
{level} PUMP ALERT

🔥 {c['symbol']}
💰 ${c['price']}

📈 24h: +{c['change']}%
📊 RSI: {rsi}

💵 Vol: ${round(c['volume']/1_000_000,1)}M

👀 SHORT WATCHLIST
"""

            send(msg.strip())

            time.sleep(1)

        except Exception as e:

            print(e)

            continue

if __name__ == "__main__":
    main()
