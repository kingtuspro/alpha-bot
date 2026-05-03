"""
Alpha Pump Detector Bot - MEXC Edition (fixed)
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

import numpy as np
import requests
from telegram import Bot
from telegram.constants import ParseMode

TELEGRAM_TOKEN = "8608021789:AAEUUZiHs3j8e1Xv5lbuEyMhpylpfkxe7HE"
CHAT_ID        = "5259562355"

SCAN_INTERVAL_SEC = 1800
TOP_N             = 5
MIN_VOLUME_RATIO  = 3.0
MIN_PRICE_CHANGE  = 5.0
MIN_QUOTE_VOLUME  = 200_000

EXCLUDED_SYMBOLS = {
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
    "ADAUSDT","DOGEUSDT","AVAXUSDT","DOTUSDT","MATICUSDT",
    "USDCUSDT","BUSDUSDT","TUSDUSDT","USDTUSDT","SHIBUSDT",
    "LTCUSDT","LINKUSDT","ATOMUSDT","NEARUSDT","APTUSDT",
}

MEXC_BASE = "https://api.mexc.com"
HEADERS   = {"User-Agent": "Mozilla/5.0 (compatible; AlphaBot/1.0)"}

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)


def get_all_tickers():
    r = requests.get(f"{MEXC_BASE}/api/v3/ticker/24hr", headers=HEADERS, timeout=15)
    r.raise_for_status()
    result = []
    for t in r.json():
        sym = t.get("symbol", "")
        if not sym.endswith("USDT") or sym in EXCLUDED_SYMBOLS:
            continue
        try:
            result.append({
                "symbol":             sym,
                "priceChangePercent": float(t.get("priceChangePercent", 0)),
                "quoteVolume":        float(t.get("quoteVolume", 0)),
                "lastPrice":          float(t.get("lastPrice", 0)),
            })
        except Exception:
            continue
    return result


def get_volume_ratio(symbol):
    r = requests.get(f"{MEXC_BASE}/api/v3/klines",
                     params={"symbol": symbol, "interval": "1h", "limit": 169},
                     headers=HEADERS, timeout=10)
    if r.status_code != 200:
        return 1.0
    candles = r.json()
    if len(candles) < 2:
        return 1.0
    volumes = [float(k[5]) for k in candles]
    avg = np.mean(volumes[:-1])
    return volumes[-1] / avg if avg > 0 else 1.0


def get_orderbook_pressure(symbol):
    r = requests.get(f"{MEXC_BASE}/api/v3/depth",
                     params={"symbol": symbol, "limit": 20},
                     headers=HEADERS, timeout=8)
    if r.status_code != 200:
        return 1.0
    data = r.json()
    bid = sum(float(b[1]) for b in data.get("bids", []))
    ask = sum(float(a[1]) for a in data.get("asks", []))
    return bid / ask if ask > 0 else 1.0


def get_price_change_1h(symbol):
    r = requests.get(f"{MEXC_BASE}/api/v3/klines",
                     params={"symbol": symbol, "interval": "1h", "limit": 2},
                     headers=HEADERS, timeout=8)
    if r.status_code != 200:
        return 0.0
    candles = r.json()
    if not candles:
        return 0.0
    o = float(candles[-1][1])
    c = float(candles[-1][4])
    return ((c - o) / o * 100) if o > 0 else 0.0


def normalize(value, low, high):
    if high == low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def compute_score(vol_ratio, p24h, p1h, ob):
    return round(
        normalize(vol_ratio, 1, 20) * 10 * 0.35 +
        normalize(p24h, 5, 60)      * 10 * 0.25 +
        normalize(p1h, 2, 20)       * 10 * 0.25 +
        normalize(ob, 1, 3)         * 10 * 0.15,
        2
    )


def scan_alpha_coins():
    log.info("Bắt đầu quét MEXC...")
    tickers = get_all_tickers()
    candidates = [t for t in tickers
                  if t["priceChangePercent"] >= MIN_PRICE_CHANGE
                  and t["quoteVolume"] >= MIN_QUOTE_VOLUME]
    log.info(f"{len(candidates)} candidates.")
    results = []
    for coin in candidates:
        sym = coin["symbol"]
        try:
            vol = get_volume_ratio(sym)
            if vol < MIN_VOLUME_RATIO:
                time.sleep(0.1)
                continue
            ob    = get_orderbook_pressure(sym)
            p1h   = get_price_change_1h(sym)
            score = compute_score(vol, coin["priceChangePercent"], p1h, ob)
            results.append({
                "symbol": sym, "price": coin["lastPrice"],
                "change_24h": coin["priceChangePercent"],
                "change_1h": round(p1h, 2),
                "vol_ratio": round(vol, 2),
                "ob": round(ob, 2), "score": score,
            })
        except Exception as e:
            log.warning(f"Lỗi {sym}: {e}")
        time.sleep(0.15)
    results.sort(key=lambda x: x["score"], reverse=True)
    log.info(f"{len(results)} coin đủ điều kiện.")
    return results[:TOP_N]


def build_message(coins):
    now = datetime.now(timezone.utc).strftime("%H:%M UTC %d/%m/%Y")
    lines = [f"🔍 *MEXC Alpha Scanner* — {now}", f"Top {len(coins)} coin:\n"]
    emojis = ["🥇","🥈","🥉","4️⃣","5️⃣"]
    for i, c in enumerate(coins):
        risk = "🔴 Rất cao" if c["vol_ratio"] > 10 else ("🟠 Cao" if c["vol_ratio"] > 5 else "🟢 Vừa")
        lines += [
            f"{emojis[i]} *{c['symbol']}*",
            f"   Score: `{c['score']:.1f}/10` | Giá: `${c['price']:.6f}`",
            f"   +{c['change_24h']:.1f}% (24h) | +{c['change_1h']:.1f}% (1h)",
            f"   Vol ratio: `{c['vol_ratio']}x` | OB: `{c['ob']}`",
            f"   Rủi ro: {risk}\n",
        ]
    lines += ["─────────────────────", "⚠️ _Không phải tư vấn đầu tư. DYOR._"]
    return "\n".join(lines)


async def run_bot():
    bot = Bot(token=TELEGRAM_TOKEN)
    await bot.send_message(chat_id=CHAT_ID,
                           text="✅ *MEXC Alpha Bot đã khởi động!*\nQuét mỗi 30 phút.",
                           parse_mode=ParseMode.MARKDOWN)
    while True:
        try:
            coins = scan_alpha_coins()
            msg = build_message(coins) if coins else "🔇 Không có coin đủ tiêu chuẩn lần này."
            await bot.send_message(chat_id=CHAT_ID, text=msg,
                                   parse_mode=ParseMode.MARKDOWN if coins else None)
            if coins:
                log.info(f"Alert: {[c['symbol'] for c in coins]}")
        except Exception as e:
            log.error(f"Lỗi: {e}")
            try:
                await bot.send_message(chat_id=CHAT_ID, text=f"❌ Lỗi: `{e}`",
                                       parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass
        log.info("Ngủ 30 phút...")
        await asyncio.sleep(SCAN_INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(run_bot())
