"""
Alpha Pump Detector Bot - MEXC Edition
Quét MEXC mỗi 30 phút, tính composite score, alert Telegram.
"""

import asyncio
import logging
import time
from datetime import datetime, timezone

import numpy as np
import requests
from telegram import Bot
from telegram.constants import ParseMode

# ─── CONFIG ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = "8608021789:AAEUUZiHs3j8e1Xv5lbuEyMhpylpfkxe7HE"
CHAT_ID        = "5259562355"

SCAN_INTERVAL_SEC = 1800
TOP_N             = 5

MIN_VOLUME_RATIO  = 3.0
MIN_PRICE_CHANGE  = 5.0
MIN_QUOTE_VOLUME  = 200_000   # MEXC coin nhỏ hơn nên để 200K

EXCLUDED_SYMBOLS = {
    "BTCUSDT", "ETHUSDT", "BNBUSDT", "SOLUSDT", "XRPUSDT",
    "ADAUSDT", "DOGEUSDT", "AVAXUSDT", "DOTUSDT", "MATICUSDT",
    "USDCUSDT", "BUSDUSDT", "TUSDUSDT", "USDTUSDT", "SHIBUSDT",
    "LTCUSDT", "LINKUSDT", "ATOMUSDT", "NEARUSDT", "APTUSDT",
}

MEXC_BASE = "https://api.mexc.com"

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    level=logging.INFO,
)
log = logging.getLogger(__name__)


# ─── MEXC HELPERS ─────────────────────────────────────────────────────────────

def get_all_tickers():
    r = requests.get(f"{MEXC_BASE}/api/v3/tickers/24hr", timeout=15)
    r.raise_for_status()
    data = r.json()
    result = []
    for t in data:
        sym = t.get("symbol", "")
        if not sym.endswith("USDT"):
            continue
        if sym in EXCLUDED_SYMBOLS:
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


def get_volume_ratio(symbol: str) -> float:
    """Volume 1h gần nhất / avg volume 1h trong 7 ngày."""
    url = f"{MEXC_BASE}/api/v3/klines"
    params = {"symbol": symbol, "interval": "1h", "limit": 169}
    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        candles = r.json()
        if len(candles) < 2:
            return 1.0
        volumes = [float(k[5]) for k in candles]
        current = volumes[-1]
        avg     = np.mean(volumes[:-1])
        return current / avg if avg > 0 else 1.0
    except Exception as e:
        log.warning(f"klines error {symbol}: {e}")
        return 1.0


def get_orderbook_pressure(symbol: str) -> float:
    """Tỉ lệ bid/ask volume trong order book."""
    url = f"{MEXC_BASE}/api/v3/depth"
    try:
        r = requests.get(url, params={"symbol": symbol, "limit": 20}, timeout=8)
        r.raise_for_status()
        data    = r.json()
        bid_vol = sum(float(b[1]) for b in data.get("bids", []))
        ask_vol = sum(float(a[1]) for a in data.get("asks", []))
        return bid_vol / ask_vol if ask_vol > 0 else 1.0
    except Exception:
        return 1.0


def get_price_change_1h(symbol: str) -> float:
    """% thay đổi giá trong 1 giờ gần nhất."""
    url = f"{MEXC_BASE}/api/v3/klines"
    params = {"symbol": symbol, "interval": "1h", "limit": 2}
    try:
        r = requests.get(url, params=params, timeout=8)
        r.raise_for_status()
        candles = r.json()
        if len(candles) < 2:
            return 0.0
        open_price  = float(candles[-1][1])
        close_price = float(candles[-1][4])
        return ((close_price - open_price) / open_price * 100) if open_price > 0 else 0.0
    except Exception:
        return 0.0


# ─── SCORING ──────────────────────────────────────────────────────────────────

def normalize(value, low, high):
    if high == low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def compute_score(volume_ratio, price_change_24h, price_change_1h, ob_pressure):
    s_vol  = normalize(volume_ratio,     1,  20) * 10
    s_24h  = normalize(price_change_24h, 5,  60) * 10
    s_1h   = normalize(price_change_1h,  2,  20) * 10
    s_ob   = normalize(ob_pressure,      1,   3) * 10
    return round(s_vol * 0.35 + s_24h * 0.25 + s_1h * 0.25 + s_ob * 0.15, 2)


# ─── MAIN SCAN ────────────────────────────────────────────────────────────────

def scan_alpha_coins():
    log.info("Bắt đầu quét MEXC...")
    tickers = get_all_tickers()

    candidates = [
        t for t in tickers
        if t["priceChangePercent"] >= MIN_PRICE_CHANGE
        and t["quoteVolume"]       >= MIN_QUOTE_VOLUME
    ]

    log.info(f"{len(candidates)} candidates sau lọc cứng.")
    results = []

    for coin in candidates:
        symbol = coin["symbol"]

        vol_ratio = get_volume_ratio(symbol)
        if vol_ratio < MIN_VOLUME_RATIO:
            time.sleep(0.1)
            continue

        ob       = get_orderbook_pressure(symbol)
        chg_1h   = get_price_change_1h(symbol)

        score = compute_score(
            volume_ratio=vol_ratio,
            price_change_24h=coin["priceChangePercent"],
            price_change_1h=chg_1h,
            ob_pressure=ob,
        )

        results.append({
            "symbol":      symbol,
            "price":       coin["lastPrice"],
            "change_24h":  coin["priceChangePercent"],
            "change_1h":   round(chg_1h, 2),
            "volume_usd":  coin["quoteVolume"],
            "vol_ratio":   round(vol_ratio, 2),
            "ob":          round(ob, 2),
            "score":       score,
        })

        time.sleep(0.15)

    results.sort(key=lambda x: x["score"], reverse=True)
    log.info(f"Tìm thấy {len(results)} coin đủ điều kiện.")
    return results[:TOP_N]


# ─── TELEGRAM MESSAGE ─────────────────────────────────────────────────────────

def build_message(coins):
    now   = datetime.now(timezone.utc).strftime("%H:%M UTC %d/%m/%Y")
    lines = [
        f"🔍 *MEXC Alpha Scanner* — {now}",
        f"Top {len(coins)} coin đáng chú ý:\n",
    ]
    emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]

    for i, c in enumerate(coins):
        risk = "🔴 Rất cao" if c["vol_ratio"] > 10 else ("🟠 Cao" if c["vol_ratio"] > 5 else "🟢 Vừa")
        lines += [
            f"{emojis[i]} *{c['symbol']}*",
            f"   Score: `{c['score']:.1f}/10` | Giá: `${c['price']:.6f}`",
            f"   +{c['change_24h']:.1f}% (24h) | +{c['change_1h']:.1f}% (1h)",
            f"   Volume ratio: `{c['vol_ratio']}x` | OB: `{c['ob']}`",
            f"   Rủi ro: {risk}\n",
        ]

    lines += [
        "─────────────────────",
        "⚠️ _Không phải tư vấn đầu tư. DYOR._",
    ]
    return "\n".join(lines)


# ─── BOT LOOP ─────────────────────────────────────────────────────────────────

async def run_bot():
    bot = Bot(token=TELEGRAM_TOKEN)

    await bot.send_message(
        chat_id=CHAT_ID,
        text="✅ *MEXC Alpha Bot đã khởi động!*\nQuét mỗi 30 phút.",
        parse_mode=ParseMode.MARKDOWN,
    )

    while True:
        try:
            coins = scan_alpha_coins()
            if coins:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text=build_message(coins),
                    parse_mode=ParseMode.MARKDOWN,
                )
                log.info(f"Đã alert: {[c['symbol'] for c in coins]}")
            else:
                await bot.send_message(
                    chat_id=CHAT_ID,
                    text="🔇 Không có coin đủ tiêu chuẩn lần này.",
                )
        except Exception as e:
            log.error(f"Lỗi: {e}")
            try:
                await bot.send_message(chat_id=CHAT_ID, text=f"❌ Lỗi: `{e}`", parse_mode=ParseMode.MARKDOWN)
            except Exception:
                pass

        log.info(f"Ngủ 30 phút...")
        await asyncio.sleep(SCAN_INTERVAL_SEC)


if __name__ == "__main__":
    asyncio.run(run_bot())
