import requests
import time
import numpy as np
from datetime import datetime

# =========================================================
# CONFIG
# =========================================================

TELEGRAM_TOKEN = "8608021789:AAEUUZiHs3j8e1Xv5lbuEyMhpylpfkxe7HE"
CHAT_ID = "5259562355"

MIN_24H_CHANGE = 5
MIN_VOLUME = 1_000_000

# =========================================================
# TELEGRAM
# =========================================================

def send(text):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    requests.post(
        url,
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
        return 50

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
# TELEGRAM
# =========================================================

def send(text):

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"

    requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": text
        },
        timeout=15
    )

# =========================================================
# GET GAINERS
# =========================================================

def get_coins():

    url = "https://api.coingecko.com/api/v3/coins/markets"

    params = {
        "vs_currency": "usd",
        "order": "price_change_percentage_24h_desc",
        "per_page": 100,
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

            market_cap = c.get(
                "market_cap",
                1
            )

            if change < MIN_24H_CHANGE:
                continue

            if volume < MIN_VOLUME:
                continue

            # =============================================
            # BASE SCORE
            # =============================================

            score = change

            vol_mc = volume / max(market_cap, 1)

            score += min(
                vol_mc * 100,
                80
            )

            if market_cap < 500_000_000:
                score += 15

            elif market_cap < 2_000_000_000:
                score += 8

            if volume > 50_000_000:
                score += 10

            results.append({
                "id": c["id"],
                "symbol": c["symbol"].upper(),
                "price": c["current_price"],
                "change": round(change, 2),
                "volume": volume,
                "market_cap": market_cap,
                "score": round(score, 1)
            })

        except:
            continue

    results.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    return results[:20]

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

        return [p[1] for p in prices]

    except:

        return []

# =========================================================
# MULTI RSI
# =========================================================

def get_multi_rsi(coin_id):

    try:

        day1 = get_chart(coin_id, "1")
        day7 = get_chart(coin_id, "7")
        day30 = get_chart(coin_id, "30")

        rsi_15m = calc_rsi(day1[-20:])
        rsi_1h = calc_rsi(day1[-40:])
        rsi_4h = calc_rsi(day7[-40:])
        rsi_12h = calc_rsi(day30[-30:])
        rsi_1d = calc_rsi(day30[-60:])

        return {
            "15m": rsi_15m,
            "1h": rsi_1h,
            "4h": rsi_4h,
            "12h": rsi_12h,
            "1d": rsi_1d
        }

    except:

        return {
            "15m": 50,
            "1h": 50,
            "4h": 50,
            "12h": 50,
            "1d": 50
        }

# =========================================================
# CLASSIFY
# =========================================================

def classify(rsis):

    r15 = rsis["15m"]
    r1h = rsis["1h"]
    r4h = rsis["4h"]
    r12 = rsis["12h"]
    r1d = rsis["1d"]

    if (
        r4h >= 80
        and r12 >= 80
        and r1d >= 75
    ):
        return "☠️ BLOWOFF TOP"

    if (
        r1h >= 75
        and r4h >= 75
        and r12 >= 70
    ):
        return "🚀 SUPER PUMP"

    if (
        r15 >= 70
        and r1h >= 70
    ):
        return "🔥 STRONG PUMP"

    if r15 >= 65:
        return "🌱 EARLY PUMP"

    return "🟡 NORMAL"

# =========================================================
# LEVEL
# =========================================================

def get_level(score):

    if score >= 100:
        return "☠️☠️☠️"

    if score >= 70:
        return "🚨🚨🚨"

    if score >= 45:
        return "🚨🚨"

    return "🚨"

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

    if not coins:

        send("❌ No coins found")

        return

    send(
        f"🔥 MULTI RSI FUTURES SCANNER\n"
        f"{len(coins)} hot coins\n"
        f"{now}"
    )

    for c in coins:

        try:

            rsis = get_multi_rsi(c["id"])

            pump_type = classify(rsis)

            level = get_level(c["score"])

            msg = f"""
{level} {pump_type}

🔥 {c['symbol']}
💰 ${c['price']}

📈 24h: +{c['change']}%

⚡ Score: {c['score']}

RSI:
15m: {rsis['15m']}
1h: {rsis['1h']}
4h: {rsis['4h']}
12h: {rsis['12h']}
1D: {rsis['1d']}

💵 Vol: ${round(c['volume']/1_000_000,1)}M
🏦 MCap: ${round(c['market_cap']/1_000_000,1)}M

👀 SHORT WATCHLIST
"""

            send(msg.strip())

            time.sleep(1)

        except Exception as e:

            print(e)

            continue

if __name__ == "__main__":
    main()
