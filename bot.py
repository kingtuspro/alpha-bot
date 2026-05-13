import os
import time
import logging
from datetime import datetime, timezone

import requests
import numpy as np

# =========================================================
# CONFIG
# =========================================================

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID = os.environ.get("CHAT_ID", "")

BASE = "https://api.bybit.com"

MIN_24H_CHANGE = 8
MIN_VOLUME_USDT = 10_000_000

TOP_COINS = 25

RSI_5M_LIMIT = 78
RSI_15M_LIMIT = 75

# =========================================================
# LOGGING
# =========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)

log = logging.getLogger(__name__)

# =========================================================
# TELEGRAM
# =========================================================

def send_tg(text):

    try:

        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={
                "chat_id": CHAT_ID,
                "text": text
            },
            timeout=10
        )

        return r.status_code == 200

    except Exception as e:

        log.error(f"Telegram error: {e}")

        return False

# =========================================================
# REQUEST RETRY
# =========================================================

def safe_get(url, params=None, retries=3):

    for i in range(retries):

        try:

            r = requests.get(
                url,
                params=params,
                timeout=15
            )

            if r.status_code == 200:
                return r.json()

            log.warning(f"HTTP {r.status_code} | retry {i+1}")

        except Exception as e:

            log.warning(f"Request error: {e}")

        time.sleep(1)

    return None

# =========================================================
# RSI
# =========================================================

def calc_rsi(closes, period=14):

    if len(closes) < period + 1:
        return None

    arr = np.array(closes, dtype=float)

    deltas = np.diff(arr)

    gains = np.where(deltas > 0, deltas, 0)
    losses = np.where(deltas < 0, -deltas, 0)

    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])

    for i in range(period, len(gains)):

        avg_gain = (
            (avg_gain * (period - 1)) + gains[i]
        ) / period

        avg_loss = (
            (avg_loss * (period - 1)) + losses[i]
        ) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss

    return round(
        100 - (100 / (1 + rs)),
        1
    )

# =========================================================
# FUTURES TICKERS
# =========================================================

def get_futures_tickers():

    url = f"{BASE}/v5/market/tickers"

    params = {
        "category": "linear"
    }

    raw = safe_get(url, params)

    if not raw:
        return []

    data = raw["result"]["list"]

    results = []

    for t in data:

        symbol = t["symbol"]

        if not symbol.endswith("USDT"):
            continue

        try:

            change = float(t["price24hPcnt"]) * 100
            volume = float(t["turnover24h"])
            price = float(t["lastPrice"])

            if change < MIN_24H_CHANGE:
                continue

            if volume < MIN_VOLUME_USDT:
                continue

            results.append({
                "symbol": symbol,
                "change_24h": round(change, 2),
                "quoteVolume": volume,
                "price": price
            })

        except:
            continue

    results.sort(
        key=lambda x: x["change_24h"],
        reverse=True
    )

    return results[:TOP_COINS]

# =========================================================
# KLINES
# =========================================================

def get_klines(symbol, interval="5m", limit=100):

    interval_map = {
        "5m": "5",
        "15m": "15",
        "1h": "60"
    }

    url = f"{BASE}/v5/market/kline"

    params = {
        "category": "linear",
        "symbol": symbol,
        "interval": interval_map[interval],
        "limit": limit
    }

    raw = safe_get(url, params)

    if not raw:
        return []

    return raw["result"]["list"]

# =========================================================
# ANALYSIS
# =========================================================

def get_rsi(symbol, tf):

    try:

        klines = get_klines(
            symbol,
            tf,
            100
        )

        klines = list(reversed(klines))

        closes = [float(k[4]) for k in klines]

        return calc_rsi(closes)

    except:

        return None

def get_volume_spike(symbol):

    try:

        klines = get_klines(
            symbol,
            "5m",
            50
        )

        klines = list(reversed(klines))

        vols = [float(k[5]) for k in klines]

        current = vols[-1]

        avg = np.mean(vols[:-1])

        if avg == 0:
            return 1

        return round(current / avg, 2)

    except:

        return 1

def get_1h_change(symbol):

    try:

        klines = get_klines(
            symbol,
            "1h",
            2
        )

        klines = list(reversed(klines))

        open_price = float(klines[0][1])

        current_price = float(klines[-1][4])

        change = (
            (current_price - open_price)
            / open_price
        ) * 100

        return round(change, 2)

    except:

        return 0

def get_funding(symbol):

    try:

        url = f"{BASE}/v5/market/tickers"

        raw = safe_get(
            url,
            {
                "category": "linear",
                "symbol": symbol
            }
        )

        if not raw:
            return 0

        data = raw["result"]["list"][0]

        return round(
            float(data["fundingRate"]) * 100,
            4
        )

    except:

        return 0

# =========================================================
# ALERT LEVEL
# =========================================================

def get_alert_level(
    rsi5,
    rsi15,
    vol_spike,
    p1h
):

    score = 0

    if rsi5 >= 80:
        score += 1

    if rsi15 >= 75:
        score += 1

    if vol_spike >= 3:
        score += 1

    if p1h >= 10:
        score += 1

    if score >= 4:
        return 3

    if score >= 2:
        return 2

    return 1

def level_emoji(level):

    if level == 3:
        return "🚨🚨🚨"

    if level == 2:
        return "🚨🚨"

    return "🚨"

# =========================================================
# FORMAT MESSAGE
# =========================================================

def format_msg(c):

    level = c["level"]

    emoji = level_emoji(level)

    now = datetime.now(
        timezone.utc
    ).strftime("%H:%M UTC")

    return f"""
{emoji} FUTURES PUMP ALERT

🔥 {c['symbol']}
💰 Price: {c['price']}

📈 1h: +{c['change_1h']}%
📈 24h: +{c['change_24h']}%

⚡ RSI
5m: {c['rsi_5m']}
15m: {c['rsi_15m']}

📦 Vol spike: {c['vol_spike']}x
💸 Funding: {c['funding']}%

🔥 LEVEL {level}
👀 SHORT WATCHLIST

⏰ {now}
""".strip()

# =========================================================
# MAIN
# =========================================================

def main():

    now = datetime.now(
        timezone.utc
    ).strftime("%H:%M UTC %d/%m/%Y")

    log.info("Scanning Bybit Futures...")

    tickers = get_futures_tickers()

    if not tickers:

        send_tg(
            f"❌ Bybit API failed\n{now}"
        )

        return

    log.info(f"{len(tickers)} candidates found")

    results = []

    for coin in tickers:

        symbol = coin["symbol"]

        try:

            rsi5 = get_rsi(symbol, "5m")

            time.sleep(0.05)

            rsi15 = get_rsi(symbol, "15m")

            vol_spike = get_volume_spike(symbol)

            p1h = get_1h_change(symbol)

            funding = get_funding(symbol)

            if not rsi5 or not rsi15:
                continue

            if rsi5 < RSI_5M_LIMIT:
                continue

            level = get_alert_level(
                rsi5,
                rsi15,
                vol_spike,
                p1h
            )

            results.append({
                **coin,
                "rsi_5m": rsi5,
                "rsi_15m": rsi15,
                "vol_spike": vol_spike,
                "change_1h": p1h,
                "funding": funding,
                "level": level
            })

            log.info(
                f"{symbol} | "
                f"RSI5={rsi5} | "
                f"RSI15={rsi15}"
            )

        except Exception as e:

            log.warning(
                f"{symbol} error: {e}"
            )

        time.sleep(0.08)

    if not results:

        send_tg(
            f"🔇 No hot setups\n{now}"
        )

        return

    results.sort(
        key=lambda x: (
            x["level"],
            x["rsi_5m"],
            x["vol_spike"]
        ),
        reverse=True
    )

    send_tg(
        f"🔥 Bybit Futures Scanner\n"
        f"{len(results)} hot coins\n"
        f"{now}"
    )

    time.sleep(0.5)

    for r in results:

        send_tg(format_msg(r))

        time.sleep(0.5)

    log.info(
        f"Sent {len(results)} alerts"
    )

if __name__ == "__main__":
    main()
