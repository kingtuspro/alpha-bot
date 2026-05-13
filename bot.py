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

            results.append({
                "id": c["id"],
                "symbol": c["symbol"].upper(),
                "price": c["current_price"],
                "change": round(change, 2),
                "volume": volume,
                "market_cap": market_cap
            })

        except:
            continue

    return results

# =========================================================
# GET PRICE CHART
# =========================================================

def get_chart(coin_id, days):

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

# =========================================================
# MULTI RSI
# =========================================================

def get_multi_rsi(coin_id):

    try:

        rsi_15m = calc_rsi(
            get_chart(coin_id, "1")[-20:]
        )

        rsi_1h = calc_rsi(
            get_chart(coin_id, "1")[-40:]
        )

        rsi_4h = calc_rsi(
            get_chart(coin_id, "7")[-40:]
        )

        rsi_12h = calc_rsi(
            get_chart(coin_id, "14")[-40:]
        )

        rsi_1d = calc_rsi(
            get_chart(coin_id, "30")[-40:]
        )

        return {
            "15m": rsi_15m,
            "1h": rsi_1h,
            "4h": rsi_4h,
            "12h": rsi_12h,
            "1d": rsi_1d
        }

    except:

        return None

# =========================================================
# CLASSIFY
# =========================================================

def classify_pump(rsis):

    hot = 0

    for r in rsis.values():

        if r >= 70:
            hot += 1

    if hot >= 5:
        return "☠️ BLOWOFF TOP"

    if (
        rsis["4h"] >= 75
        and rsis["12h"] >= 75
        and rsis["1d"] >= 70
    ):
        return "🚀 SUPER PUMP"

    if (
        rsis["15m"] >= 70
        and rsis["1h"] >= 70
        and rsis["4h"] >= 70
    ):
        return "🔥 STRONG PUMP"

    if rsis["15m"] >= 70:
        return "🌱 EARLY PUMP"

    return "🟡 NORMAL"

# =========================================================
# SCORE
# =========================================================

def calc_score(change, volume, market_cap, rsis):

    score = change

    vol_mc = volume / max(market_cap, 1)

    score += min(
        vol_mc * 100,
        80
    )

    if market_cap < 500_000_000:
        score += 15

    if volume > 50_000_000:
        score += 10

    # RSI bonuses

    for r in rsis.values():

        if r >= 70:
            score += 5

        if r >= 80:
            score += 5

    return round(score, 1)

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

    final = []

    for c in coins[:20]:

        try:

            rsis = get_multi_rsi(c["id"])

            if not rsis:
                continue

            pump_type = classify_pump(rsis)

            score = calc_score(
                c["change"],
                c["volume"],
                c["market_cap"],
                rsis
            )

            c["rsis"] = rsis
            c["score"] = score
            c["pump_type"] = pump_type

            final.append(c)

            time.sleep(1)

        except Exception as e:

            print(e)

            continue

    final.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    send(
        f"🔥 MULTI RSI FUTURES SCANNER\n"
        f"{len(final)} hot coins\n"
        f"{now}"
    )

    for c in final[:15]:

        try:

            level = get_level(c["score"])

            msg = f"""
{level} {c['pump_type']}

🔥 {c['symbol']}
💰 ${c['price']}

📈 24h: +{c['change']}%

⚡ Score: {c['score']}

RSI:
15m: {c['rsis']['15m']}
1h: {c['rsis']['1h']}
4h: {c['rsis']['4h']}
12h: {c['rsis']['12h']}
1D: {c['rsis']['1d']}

💵 Vol: ${round(c['volume']/1_000_000,1)}M

👀 SHORT WATCHLIST
"""

            send(msg.strip())

            time.sleep(1)

        except:
            continue

if __name__ == "__main__":
    main()
