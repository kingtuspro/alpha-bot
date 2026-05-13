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
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(
        url,
        json={"chat_id": CHAT_ID, "text": text},
        timeout=20
    )

# =========================================================
# RSI CALC
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
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)

# =========================================================
# MARKET SCANNER (ONLY ACTIVE PUMPS)
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

    r = requests.get(url, params=params, timeout=30)
    data = r.json()

    results = []

    for c in data:
        try:
            change = c.get("price_change_percentage_24h", 0)
            volume = c.get("total_volume", 0)

            # ONLY ACTIVE PUMPS
            if change < 10:
                continue
            if volume < 10_000_000:
                continue

            momentum = change + min(volume / 50_000_000, 40)

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

    results.sort(key=lambda x: x["momentum"], reverse=True)
    return results[:25]

# =========================================================
# CHART DATA
# =========================================================

def get_chart(coin_id, days):
    try:
        url = f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart"

        params = {
            "vs_currency": "usd",
            "days": days
        }

        r = requests.get(url, params=params, timeout=30)
        data = r.json()

        return [p[1] for p in data["prices"]]

    except:
        return []

# =========================================================
# MULTI RSI (5 TIMEFRAMES)
# =========================================================

def get_rsis(coin_id):

    d1 = get_chart(coin_id, "1")
    d7 = get_chart(coin_id, "7")
    d30 = get_chart(coin_id, "30")

    return {
        "15m": calc_rsi(d1[-20:]),
        "1h": calc_rsi(d1[-40:]),
        "4h": calc_rsi(d7[-40:]),
        "12h": calc_rsi(d30[-30:]),
        "1d": calc_rsi(d30[-80:])
    }

# =========================================================
# CLASSIFY PUMP TYPE
# =========================================================

def classify(rsis):

    r15 = rsis["15m"]
    r1h = rsis["1h"]
    r4h = rsis["4h"]
    r12 = rsis["12h"]
    r1d = rsis["1d"]

    if r15 >= 85 and r1h >= 80:
        return "☠️ LIVE SHORT SQUEEZE"

    if r15 >= 80 and r1h >= 75 and r4h >= 70:
        return "🚀 SUPER PUMP"

    if r15 >= 70 and r1h >= 70:
        return "🔥 STRONG PUMP"

    if r15 >= 65:
        return "🌱 EARLY PUMP"

    return "🟡 NORMAL"

# =========================================================
# RSI ICON
# =========================================================

def icon(v):
    if v >= 90:
        return "🔴"
    if v >= 75:
        return "🟡"
    return "⚪️"

# =========================================================
# MAIN
# =========================================================

def main():

    now = datetime.utcnow().strftime("%H:%M UTC %d/%m/%Y")

    coins = get_coins()

    send(f"🔥 LIVE PUMP SCANNER\n{len(coins)} movers\n{now}")

    for c in coins:

        try:
            rsis = get_rsis(c["id"])
            pump = classify(rsis)

            # FILTER ONLY STRONG SIGNALS
            if pump == "🟡 NORMAL":
                continue

            msg = f"""
🚨 ${c['symbol']}_USDT - Giá hiện tại: {c['price']}

Biến động 24h: +{c['change']}%

Tín hiệu: {pump}

RSI đa khung:
15m {icon(rsis['15m'])} {rsis['15m']}
1h  {icon(rsis['1h'])} {rsis['1h']}
4h  {icon(rsis['4h'])} {rsis['4h']}
12h {icon(rsis['12h'])} {rsis['12h']}
1d  {icon(rsis['1d'])} {rsis['1d']}

⚡ Momentum: {c['momentum']}
💵 Volume: {round(c['volume']/1_000_000,2)}M

👀 SHORT WATCHLIST
"""

            send(msg.strip())
            time.sleep(1)

        except:
            continue

if __name__ == "__main__":
    main()
