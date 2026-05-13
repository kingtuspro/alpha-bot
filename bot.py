"""
Alpha Pump Detector Bot - BingX Edition
Format: RSI đa khung + Funding + Phân kỳ + Rating sao
"""

import logging, os, time
from datetime import datetime, timezone
import numpy as np
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID        = os.environ.get("CHAT_ID", "")

MIN_PRICE_CHANGE = 2.0
MIN_QUOTE_VOLUME = 50_000
TOP_N            = 5

EXCLUDED = {
    "BTC-USDT","ETH-USDT","BNB-USDT","SOL-USDT","XRP-USDT",
    "ADA-USDT","DOGE-USDT","AVAX-USDT","DOT-USDT","MATIC-USDT",
    "USDC-USDT","BUSD-USDT","TUSD-USDT","SHIB-USDT",
    "LTC-USDT","LINK-USDT","ATOM-USDT","NEAR-USDT","APT-USDT",
}

BASE     = "https://open-api.bingx.com"
HEADERS  = {"User-Agent": "Mozilla/5.0 (compatible; AlphaBot/1.0)"}
TFS      = ["1m","5m","15m","1h","4h"]

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)


# ── TELEGRAM ──────────────────────────────────────────────────────────────────
def send_tg(text):
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"},
            timeout=10
        )
        return r.status_code == 200
    except Exception as e:
        log.error(f"TG error: {e}")
        return False


# ── RSI ───────────────────────────────────────────────────────────────────────
def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    arr    = np.array(closes, dtype=float)
    deltas = np.diff(arr)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    ag, al = np.mean(gains[:period]), np.mean(losses[:period])
    for i in range(period, len(gains)):
        ag = (ag * (period - 1) + gains[i]) / period
        al = (al * (period - 1) + losses[i]) / period
    return round(100.0 if al == 0 else 100 - 100 / (1 + ag / al), 1)

def rsi_emoji(v):
    if v is None: return "⚪"
    if v >= 70:   return "🔴"
    if v >= 55:   return "🟡"
    if v >= 45:   return "⚪"
    return "🟢"


# ── BINGX API ─────────────────────────────────────────────────────────────────
def get_tickers():
    """Lấy toàn bộ ticker 24h - BingX trả về data.data[]"""
    r = requests.get(f"{BASE}/openApi/spot/v1/ticker/24hr",
                     headers=HEADERS, timeout=15)
    r.raise_for_status()
    raw = r.json()
    # BingX trả về list trực tiếp hoặc trong data
    items = raw if isinstance(raw, list) else raw.get("data", [])
    result = []
    for t in items:
        sym = t.get("symbol", "")
        if not sym.endswith("-USDT") or sym in EXCLUDED:
            continue
        try:
            pct = float(t.get("priceChangePercent", 0) or 0)
            vol = float(t.get("quoteVolume", 0) or 0)
            if pct < MIN_PRICE_CHANGE or vol < MIN_QUOTE_VOLUME:
                continue
            result.append({
                "symbol":     sym,
                "change_24h": pct,
                "quoteVolume": vol,
                "price":      float(t.get("lastPrice", 0) or 0),
            })
        except Exception:
            continue
    result.sort(key=lambda x: x["change_24h"], reverse=True)
    return result[:30]  # Top 30 tăng mạnh nhất


def get_klines(symbol, interval, limit=50):
    try:
        r = requests.get(
            f"{BASE}/openApi/spot/v2/market/kline",
            params={"symbol": symbol, "interval": interval, "limit": limit},
            headers=HEADERS, timeout=8
        )
        if r.status_code != 200:
            return []
        raw = r.json()
        data = raw if isinstance(raw, list) else raw.get("data", [])
        return data
    except Exception:
        return []


def get_rsi_all_tf(symbol):
    rsis = {}
    for tf in TFS:
        candles = get_klines(symbol, tf)
        try:
            # BingX kline format: [time, open, high, low, close, volume, ...]
            closes = [float(k[4]) for k in candles] if candles else []
            rsis[tf] = calc_rsi(closes) if len(closes) > 15 else None
        except Exception:
            rsis[tf] = None
        time.sleep(0.06)
    return rsis


def get_volume_ratio(symbol):
    try:
        candles = get_klines(symbol, "1h", limit=169)
        if len(candles) < 2:
            return 1.0
        volumes = [float(k[5]) for k in candles]
        avg = np.mean(volumes[:-1])
        return round(volumes[-1] / avg, 2) if avg > 0 else 1.0
    except Exception:
        return 1.0


def get_price_1h_open(symbol):
    try:
        candles = get_klines(symbol, "1h", limit=2)
        return float(candles[-1][1]) if candles else None
    except Exception:
        return None


def get_funding_rate(symbol):
    """Funding rate từ BingX Perpetual Futures."""
    try:
        # BingX futures dùng BTC-USDT format
        r = requests.get(
            f"{BASE}/openApi/swap/v2/quote/fundingRate",
            params={"symbol": symbol},
            headers=HEADERS, timeout=6
        )
        if r.status_code == 200:
            raw = r.json()
            data = raw.get("data", {})
            rate = data.get("fundingRate", None)
            if rate is not None:
                return round(float(rate) * 100, 4)
    except Exception:
        pass
    return None


def detect_divergence(symbol):
    try:
        candles = get_klines(symbol, "15m", limit=60)
        if len(candles) < 30:
            return None
        closes = [float(k[4]) for k in candles]
        rsis   = [calc_rsi(closes[:i+1]) for i in range(14, len(closes))]
        rsis   = [r for r in rsis if r is not None]
        if len(rsis) < 10:
            return None
        rc, rr = closes[-20:], rsis[-20:]
        if rc[-1] > max(rc[:-5]) and rr[-1] < max(rr[:-5]):
            return "bearish"
        if rc[-1] < min(rc[:-5]) and rr[-1] > min(rr[:-5]):
            return "bullish"
    except Exception:
        pass
    return None


# ── SCORING ───────────────────────────────────────────────────────────────────
def norm(v, lo, hi):
    if hi == lo: return 0.0
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))

def compute_score(p24h, p1h, vol_ratio, rsi_1h, funding):
    return round(
        norm(p24h,     2, 60)  * 10 * 0.30 +
        norm(p1h,      0, 20)  * 10 * 0.25 +
        norm(vol_ratio,1, 20)  * 10 * 0.25 +
        norm(rsi_1h or 50, 40, 75) * 10 * 0.15 +
        norm(funding or 0, 0, 0.02) * 10 * 0.05,
        2
    )

def stars(score):
    if score >= 8:   return "⭐⭐⭐⭐⭐"
    if score >= 6.5: return "⭐⭐⭐⭐"
    if score >= 5:   return "⭐⭐⭐"
    if score >= 3.5: return "⭐⭐"
    return "⭐"

def vol_str(v):
    return f"{v/1e6:.2f}M" if v >= 1e6 else f"{v/1000:.1f}K"


# ── FORMAT TIN NHẮN ───────────────────────────────────────────────────────────
def format_msg(c):
    sym, price = c["symbol"], c["price"]
    p1h, p24h  = c["change_1h"], c["change_24h"]
    rsis, div  = c["rsis"], c["divergence"]
    funding    = c["funding"]
    score      = c["score"]
    open_1h    = c["open_1h"]
    vol_r      = c["vol_ratio"]
    now        = datetime.now(timezone.utc).strftime("%-m/%-d/%Y, %-I:%M:%S %p")

    rsi_1h    = rsis.get("1h")
    rsi_sc    = 3 if (rsi_1h and 55 <= rsi_1h < 70) else (2 if (rsi_1h and rsi_1h >= 70) else 1)
    div_sc    = 1
    total     = min(rsi_sc + div_sc, 5)
    emoji_1h  = "🟡" if p1h >= 5 else ("🟢" if p1h >= 0 else "🔴")
    fund_str  = f"{funding:.4f}%" if funding is not None else "N/A"
    rsi_line  = " • ".join(f"{tf} {rsi_emoji(rsis.get(tf))}{rsis.get(tf) or 'N/A'}" for tf in TFS)
    ob_tfs    = [tf for tf, v in rsis.items() if v and v >= 70]

    if div == "bearish":
        div_str = "• 15m: ⚠️ Phân kỳ giảm (2 đỉnh – RSI14)"
    elif div == "bullish":
        div_str = "• 15m: ✅ Phân kỳ tăng (2 đáy – RSI14)"
    else:
        div_str = "• 15m: Không phát hiện phân kỳ"

    p1h_str = f"{open_1h:.6f} → {price:.6f}" if open_1h else f"{price:.6f}"

    lines = [
        f"🚨 *${sym}* - Giá hiện tại: {price:.6f}",
        f"",
        f"📈 Biến động 1h: {emoji_1h}+{p1h:.2f}%",
        f"🇮🇹 Biến động 24h: +{p24h:.2f}%",
        f"",
        f"💰 Funding: {fund_str}",
        f"",
        f"⚡ Tín hiệu RSI & Funding (RSI:{rsi_sc} / Div:{div_sc} / Tổng:{total}/5):",
        stars(score),
        f"",
        f"🔘 Phân kỳ đa khung (RSI14 – nên động):",
        div_str,
        f"",
        f"🇮🇹 RSI đa khung: {rsi_line}",
    ]
    if ob_tfs:
        lines.append(f"🔥 OVERBOUGHT: {', '.join(ob_tfs)}")
    lines += [
        f"",
        f"📊 Vol ratio: `{vol_r}x` | Score: `{score}/10`",
        f"💲 Giá 1h: {p1h_str}",
        f"📦 Volume 24h: {vol_str(c['quoteVolume'])}",
        f"",
        f"⏰ {now}",
        f"📍 Alpha Pump Bot",
    ]
    return "\n".join(lines)


# ── MAIN ──────────────────────────────────────────────────────────────────────
def main():
    log.info("Bắt đầu quét BingX...")
    tickers = get_tickers()
    now     = datetime.now(timezone.utc).strftime("%H:%M UTC %d/%m/%Y")
    log.info(f"{len(tickers)} candidates.")

    if not tickers:
        send_tg(f"❌ *BingX API lỗi* — {now}\nKhông lấy được dữ liệu!")
        return

    # Debug: top 5 đang tăng mạnh nhất
    dbg = [f"🛠 *Debug BingX* — {now}\nTop gainers:\n"]
    for t in tickers[:5]:
        dbg.append(f"• *{t['symbol']}* +{t['change_24h']:.1f}% | Vol ${t['quoteVolume']:,.0f}")
    send_tg("\n".join(dbg))

    results = []
    for coin in tickers:
        sym = coin["symbol"]
        try:
            rsis    = get_rsi_all_tf(sym)
            vol_r   = get_volume_ratio(sym)
            open_1h = get_price_1h_open(sym)
            p1h     = round((coin["price"] - open_1h) / open_1h * 100, 2) if (open_1h and open_1h > 0) else 0.0
            funding = get_funding_rate(sym)
            div     = detect_divergence(sym)
            score   = compute_score(coin["change_24h"], p1h, vol_r, rsis.get("1h"), funding)

            results.append({**coin,
                "change_1h": p1h, "vol_ratio": vol_r,
                "rsis": rsis, "funding": funding,
                "divergence": div, "open_1h": open_1h, "score": score,
            })
            log.info(f"✅ {sym} score={score} 24h={coin['change_24h']:.1f}% vol={vol_r}x")
        except Exception as e:
            log.warning(f"Lỗi {sym}: {e}")
        time.sleep(0.1)

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:TOP_N]

    if not top:
        send_tg(f"🔇 *BingX Alpha Scanner* — {now}\nKhông có coin đủ tiêu chuẩn.")
        return

    send_tg(f"🔍 *BingX Alpha Scanner* — {now}\nTop {len(top)} coin đáng chú ý:")
    time.sleep(0.3)
    for c in top:
        send_tg(format_msg(c))
        time.sleep(0.5)

    log.info(f"Đã gửi {len(top)} coin.")


if __name__ == "__main__":
    main()
