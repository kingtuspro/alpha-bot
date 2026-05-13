import requests
import time
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
        timeout=15
    )

# =========================================================
# GET GAINERS
# =========================================================

def get_gainers():

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

            change_24h = c.get(
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

            if change_24h < MIN_24H_CHANGE:
                continue

            if volume < MIN_VOLUME:
                continue

            # =================================================
            # ALPHA SCORE
            # =================================================

            vol_mc_ratio = volume / max(market_cap, 1)

            score = (
                change_24h
                + min(vol_mc_ratio * 100, 100)
            )

            # small-mid cap bonus
            if market_cap < 500_000_000:
                score += 15

            elif market_cap < 2_000_000_000:
                score += 8

            # mega volume bonus
            if volume > 50_000_000:
                score += 10

            if score < 25:
                continue

            results.append({
                "symbol": c["symbol"].upper(),
                "name": c["name"],
                "price": c["current_price"],
                "change": round(change_24h, 2),
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
# ALERT LEVEL
# =========================================================

def get_level(score):

    if score >= 80:
        return "🚨🚨🚨"

    if score >= 50:
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

        gainers = get_gainers()

    except Exception as e:

        send(f"❌ API ERROR\n{e}")

        return

    if not gainers:

        send("❌ No alpha coins found")

        return

    send(
        f"🔥 ALPHA FUTURES SCANNER\n"
        f"{len(gainers)} hot coins found\n"
        f"{now}"
    )

    for c in gainers:

        try:

            level = get_level(c["score"])

            volume_m = round(
                c["volume"] / 1_000_000,
                1
            )

            marketcap_m = round(
                c["market_cap"] / 1_000_000,
                1
            )

            msg = f"""
{level} ALPHA PUMP ALERT

🔥 {c['symbol']}
💰 ${c['price']}

📈 24h: +{c['change']}%

⚡ Alpha Score: {c['score']}

💵 Volume: ${volume_m}M
🏦 MCap: ${marketcap_m}M

👀 SHORT WATCHLIST
"""

            send(msg.strip())

            time.sleep(1)

        except Exception as e:

            print(e)

            continue

if __name__ == "__main__":
    main()
