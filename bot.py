"""
Alpha Pump Detector Bot - MEXC Edition
Chạy 1 lần rồi thoát (GitHub Actions gọi mỗi 30 phút)
"""

import logging
import time
from datetime import datetime, timezone

import numpy as np
import requests

# ─── CONFIG ────────────────────────────────────────────────────────────────────
import os
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID        = os.environ.get("CHAT_ID", "")

MIN_PRICE_CHANGE = 3.0
MIN_VOLUME_RATIO = 2.0
MIN_QUOTE_VOLUME = 50_000
TOP_N            = 5

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


# ─── TELEGRAM ─────────────────────────────────────────────────────────────────

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown"
    }, timeout=10)
    return r.status_code == 200


# ─── MEXC API ─────────────────────────────────────────────────────────────────

def get_all_tickers():
    r = requests.get(f"{MEXC_BASE}/api/v3/ticker/24hr", headers=HEADERS, timeout=15)
    r.raise_for_status()
    result = []
    for t in r.json():
        sym = t.get("symbol", "")
        if not sym.endswith("USDT") or sym in EXCLUDED_SYMBOLS:
            continue
        try:
            pct = float(t.get("priceChangePercent", 0))
            vol = float(t.get("quoteVolume", 0))
            if pct < MIN_PRICE_CHANGE or vol < MIN_QUOTE_VOLUME:
                continue
            result.append({
                "symbol":             sym,
                "priceChangePercent": pct,
                "quoteVolume":        vol,
                "lastPrice":          float(t.get("lastPrice", 0)),
            })
        except Exception:
            continue
    return result


def get_volume_ratio(symbol):
    try:
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
    except Exception:
        return 1.0


def get_orderbook_pressure(symbol):
    try:
        r = requests.get(f"{MEXC_BASE}/api/v3/depth",
                         params={"symbol": symbol, "limit": 20},
                         headers=HEADERS, timeout=8)
        if r.status_code != 200:
            return 1.0
        data = r.json()
        bid = sum(float(b[1]) for b in data.get("bids", []))
        ask = sum(float(a[1]) for a in data.get("asks", []))
        return bid / ask if ask > 0 else 1.0
    except Exception:
        return 1.0


def get_price_change_1h(symbol):
    try:
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
    except Exception:
        return 0.0


# ─── SCORING ──────────────────────────────────────────────────────────────────

def normalize(value, low, high):
    if high == low:
        return 0.0
    return max(0.0, min(1.0, (value - low) / (high - low)))


def compute_score(vol_ratio, p24h, p1h, ob):
    return round(
        normalize(vol_ratio, 1, 20) * 10 * 0.35 +
        normalize(p24h, 3, 60)      * 10 * 0.25 +
        normalize(p1h, 1, 20)       * 10 * 0.25 +
        normalize(ob, 1, 3)         * 10 * 0.15,
        2
    )


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    log.info("Bắt đầu quét MEXC...")
    tickers = get_all_tickers()
    log.info(f"{len(tickers)} candidates.")

    results = []
    for coin in tickers:
        sym = coin["symbol"]
        try:
            vol = get_volume_ratio(sym)
            ob  = get_orderbook_pressure(sym)
            p1h = get_price_change_1h(sym)
            if vol < MIN_VOLUME_RATIO:
                time.sleep(0.08)
                continue
            score = compute_score(vol, coin["priceChangePercent"], p1h, ob)
            results.append({
                "symbol":     sym,
                "price":      coin["lastPrice"],
                "change_24h": coin["priceChangePercent"],
                "change_1h":  round(p1h, 2),
                "vol_ratio":  round(vol, 2),
                "ob":         round(ob, 2),
                "score":      score,
            })
            log.info(f"✅ {sym} score={score} vol={vol:.1f}x 24h={coin['priceChangePercent']:.1f}%")
        except Exception as e:
            log.warning(f"Lỗi {sym}: {e}")
        time.sleep(0.12)

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:TOP_N]

    now    = datetime.now(timezone.utc).strftime("%H:%M UTC %d/%m/%Y")

    if not top:
        send_telegram(f"🔇 *MEXC Alpha Scanner* — {now}\nKhông có coin đủ tiêu chuẩn lần quét này.")
        log.info("Không có coin đủ tiêu chuẩn.")
        return

    lines  = [f"🔍 *MEXC Alpha Scanner* — {now}", f"Top {len(top)} coin:\n"]
    emojis = ["🥇","🥈","🥉","4️⃣","5️⃣"]

    for i, c in enumerate(top):
        risk = "🔴 Rất cao" if c["vol_ratio"] > 10 else ("🟠 Cao" if c["vol_ratio"] > 5 else "🟢 Vừa")
        lines += [
            f"{emojis[i]} *{c['symbol']}*",
            f"   Score: `{c['score']:.1f}/10` | Giá: `${c['price']:.6f}`",
            f"   +{c['change_24h']:.1f}% (24h) | +{c['change_1h']:.1f}% (1h)",
            f"   Vol ratio: `{c['vol_ratio']}x` | OB: `{c['ob']}`",
            f"   Rủi ro: {risk}\n",
        ]
    lines += ["─────────────────────", "⚠️ _Không phải tư vấn đầu tư. DYOR._"]

    msg = "\n".join(lines)
    if send_telegram(msg):
        log.info(f"Đã gửi alert: {[c['symbol'] for c in top]}")
    else:
        log.error("Gửi Telegram thất bại!")


if __name__ == "__main__":
    main()
