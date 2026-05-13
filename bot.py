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
        timeout=20
    )

# =========================================================
# COINGECKO GAINERS
# =========================================================

def get_coingecko():

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

            score = change

            # volume strength
            vol_mc = volume / max(market_cap, 1)

            score += min(
                vol_mc * 100,
                80
            )

            # small cap bonus
            if market_cap < 500_000_000:
                score += 15

            elif market_cap < 2_000_000_000:
                score += 8

            # giga volume
            if volume > 50_000_000:
                score += 10

            results.append({
                "symbol": c["symbol"].upper(),
                "price": c["current_price"],
                "change": round(change, 2),
                "volume": volume,
                "market_cap": market_cap,
                "score": round(score, 1),
                "source": "CoinGecko"
            })

        except:
            continue

    return results

# =========================================================
# DEXSCREENER TRENDING
# =========================================================

def get_dexscreener():

    url = "https://api.dexscreener.com/latest/dex/search"

    keywords = [
        "lab",
        "cos",
        "bill",
        "meme",
        "ai"
    ]

    results = []

    for k in keywords:

        try:

            r = requests.get(
                url,
                params={"q": k},
                timeout=20
            )

            data = r.json()

            pairs = data.get("pairs", [])

            for p in pairs[:5]:

                try:

                    symbol = p["baseToken"]["symbol"]

                    volume = float(
                        p.get("volume", {}).get(
                            "h24",
                            0
                        )
                    )

                    change = float(
                        p.get("priceChange", {}).get(
                            "h24",
                            0
                        )
                    )

                    liquidity = float(
                        p.get("liquidity", {}).get(
                            "usd",
                            0
                        )
                    )

                    price = float(
                        p.get("priceUsd", 0)
                    )

                    if change < 10:
                        continue

                    score = (
                        change
                        + min(volume / 1_000_000, 50)
                    )

                    if liquidity < 100_000:
                        score += 10

                    results.append({
                        "symbol": symbol,
                        "price": price,
                        "change": round(change, 2),
                        "volume": volume,
                        "market_cap": liquidity,
                        "score": round(score, 1),
                        "source": "DexScreener"
                    })

                except:
                    continue

        except:
            continue

        time.sleep(0.5)

    return results

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

    all_coins = []

    # =====================================================
    # COINGECKO
    # =====================================================

    try:

        cg = get_coingecko()

        all_coins.extend(cg)

    except Exception as e:

        print("CG ERROR", e)

    # =====================================================
    # DEXSCREENER
    # =====================================================

    try:

        ds = get_dexscreener()

        all_coins.extend(ds)

    except Exception as e:

        print("DEX ERROR", e)

    if not all_coins:

        send("❌ No alpha coins found")

        return

    # =====================================================
    # SORT
    # =====================================================

    all_coins.sort(
        key=lambda x: x["score"],
        reverse=True
    )

    # remove duplicates
    final = []

    seen = set()

    for c in all_coins:

        if c["symbol"] in seen:
            continue

        seen.add(c["symbol"])

        final.append(c)

    final = final[:20]

    # =====================================================
    # HEADER
    # =====================================================

    send(
        f"🔥 ALPHA FUTURES SCANNER\n"
        f"{len(final)} hot coins\n"
        f"{now}"
    )

    # =====================================================
    # SEND ALERTS
    # =====================================================

    for c in final:

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

⚡ Score: {c['score']}

💵 Volume: ${volume_m}M
🏦 Size: ${marketcap_m}M

📡 Source: {c['source']}

👀 SHORT WATCHLIST
"""

            send(msg.strip())

            time.sleep(1)

        except Exception as e:

            print(e)

            continue

if __name__ == "__main__":
    main()
