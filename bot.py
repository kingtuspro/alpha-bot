import requests
import time
import numpy as np
from datetime import datetime

# =========================================================
# CONFIG
# =========================================================

TELEGRAM_TOKEN = "8608021789:AAEUUZiHs3j8e1Xv5lbuEyMhpylpfkxe7HE"
CHAT_ID = "5259562355"

# =========================================================
# TELEGRAM
# =========================================================

def send(text):

    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        json={
            "chat_id": CHAT_ID,
            "text": text
        },
        timeout=20
    )

# =========================================================
# RSI
# =========================================================

def calc_rsi(closes, period=14):

    if len(closes) < period + 1:
        return None

    closes = np.array(closes)

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

# =========================================================
# GET COINS
# =========================================================

def get_coins():

    url = "https://api.coingecko.com/api/v3/coins/markets"

    params = {
        "vs_currency": "usd",
        "order": "volume_desc",
        "per_page": 250,
        "page": 1,
        "sparkline": False
    }

    r = requests.get(
        url,
        params=params,
        timeout=30
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

            # ONLY ACTIVE PUMPS

            if change < 12:
                continue

            if volume < 20_000_000:
                continue

            momentum = (
                change
                + min(volume / 50_000_000, 40)
            )

            results.append({
                "id": c["id"],
                "symbol": c["symbol"].upper(),
                "price": c["current_price"],
                "change": round(change, 2),
                "volume": volume,
                "momentum": round(momentum, 1)
            })

        except:
            continue

    results.sort(
        key=lambda x: x["momentum"],
        reverse=True
    )

    return results[:25]

# =========================================================
# GET CHART
# =========================================================

def get_chart(coin_id, days):

    try:

        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"

        params = {
            "vs_currency": "usd",
            "days": days
        }

        r = requests.get(
            url,
            params=params,
            timeout=30
        )

        data = r.json()

        prices = data["prices"]

        closes = [p[1] for p in prices]

        if len(closes) < 20:
            return None

        return closes

    except:

        return None

# =========================================================
# RSI SET
# =========================================================

def get_rsis(coin_id):

    d1 = get_chart(coin_id, "1")
    d7 = get_chart(coin_id, "7")

    if not d1 or not d7:
        return None

    return {
        "15m": calc_rsi(d1[-20:]),
        "1h": calc_rsi(d1[-40:]),
        "4h": calc_rsi(d7[-40:])
    }

# =========================================================
# CLASSIFY
# =========================================================

def classify(rsis):

    r15 = rsis["15m"]
    r1h = rsis["1h"]
    r4h = rsis["4h"]

    if (
        r15 >= 85
        and r1h >= 80
    ):
        return "☠️ LIVE SHORT SQUEEZE"

    if (
        r15 >= 80
        and r1h >= 75
        and r4h >= 70
    ):
        return "🚀 SUPER PUMP"

    if (
        r15 >= 70
        and r1h >= 70
    ):
        return "🔥 STRONG PUMP"

    return None

# =========================================================
# MAIN
# =========================================================

def main():

    now = datetime.utcnow().strftime(
        "%H:%M UTC %d/%m/%Y"
    )

    try:

        coins = get_coins()

    except Exception as e:

        send(f"❌ API ERROR\n{e}")

        return

    final = []

    for c in coins:

        try:

            rsis = get_rsis(c["id"])

            if not rsis:
                continue

            pump = classify(rsis)

            # ONLY HOT PUMPS

            if not pump:
                continue

            c["rsis"] = rsis
            c["pump"] = pump

            final.append(c)

            time.sleep(0.8)

        except:
            continue

    # SORT HOTTEST
    final.sort(
        key=lambda x: (
            x["rsis"]["15m"]
            + x["rsis"]["1h"]
            + x["momentum"]
        ),
        reverse=True
    )

    if not final:

        send("🟡 No strong live pumps now")

        return

    send(
        f"🔥 LIVE PUMP SCANNER\n"
        f"{len(final)} strong pumps\n"
        f"{now}"
    )

    for c in final[:10]:

        msg = f"""
{c['pump']}

🔥 {c['symbol']}
💰 ${c['price']}

📈 24h: +{c['change']}%

⚡ Momentum: {c['momentum']}

RSI:
15m: {c['rsis']['15m']}
1h: {c['rsis']['1h']}
4h: {c['rsis']['4h']}

💵 Vol: ${round(c['volume']/1_000_000,1)}M

👀 SHORT WATCHLIST
"""

        send(msg.strip())

        time.sleep(1)

if __name__ == "__main__":
    main()
