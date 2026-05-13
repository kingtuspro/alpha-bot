"""
Alpha Pump Detector Bot - MEXC Edition v3
Format: RSI đa khung + Funding + Phân kỳ + Rating sao
"""

import logging
import os
import time
from datetime import datetime, timezone

import numpy as np
import requests

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "")
CHAT_ID        = os.environ.get("CHAT_ID", "")

# ── Ngưỡng lọc ──────────────────────────────────────────────────────────────
MIN_PRICE_CHANGE  = 3.0    # % thay đổi 24h
MIN_QUOTE_VOLUME  = 100_000
MIN_VOL_RATIO     = 2.0    # volume 1h / avg 7 ngày
TOP_N             = 5

EXCLUDED = {
    "BTCUSDT","ETHUSDT","BNBUSDT","SOLUSDT","XRPUSDT",
    "ADAUSDT","DOGEUSDT","AVAXUSDT","DOTUSDT","MATICUSDT",
    "USDCUSDT","BUSDUSDT","TUSDUSDT","USDTUSDT","SHIBUSDT",
    "LTCUSDT","LINKUSDT","ATOMUSDT","NEARUSDT","APTUSDT",
}

MEXC_SPOT    = "https://api.mexc.com"
MEXC_FUTURES = "https://contract.mexc.com"
HEADERS      = {"User-Agent": "Mozilla/5.0 (compatible; AlphaBot/1.0)"}
TIMEFRAMES   = ["1m","5m","15m","1h","4h"]

logging.basicConfig(format="%(asctime)s [%(levelname)s] %(message)s", level=logging.INFO)
log = logging.getLogger(__name__)


# ── TELEGRAM ─────────────────────────────────────────────────────────────────

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": CHAT_ID, "text": text, "parse_mode": "Markdown"
        }, timeout=10)
        return r.status_code == 200
    except Exception as e:
        log.error(f"Telegram error: {e}")
        return False


# ── RSI ──────────────────────────────────────────────────────────────────────

def calc_rsi(closes, period=14):
    """Tính RSI từ danh sách giá đóng cửa."""
    if len(closes) < period + 1:
        return None
    closes = np.array(closes, dtype=float)
    deltas = np.diff(closes)
    gains  = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = np.mean(gains[:period])
    avg_loss = np.mean(losses[:period])
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 1)


def rsi_emoji(rsi):
    if rsi is None:
        return "⚪"
    if rsi >= 70:
        return "🔴"
    if rsi >= 55:
        return "🟡"
    if rsi >= 45:
        return "⚪"
    return "🟢"


# ── KLINES ───────────────────────────────────────────────────────────────────

def get_klines(symbol, interval, limit=50):
    try:
        r = requests.get(f"{MEXC_SPOT}/api/v3/klines",
                         params={"symbol": symbol, "interval": interval, "limit": limit},
                         headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        return r.json()
    except Exception:
        return []


def get_rsi_all_tf(symbol):
    """Lấy RSI 14 cho tất cả timeframe."""
    result = {}
    for tf in TIMEFRAMES:
        candles = get_klines(symbol, tf, limit=50)
        if candles:
            closes = [float(k[4]) for k in candles]
            result[tf] = calc_rsi(closes)
        else:
            result[tf] = None
        time.sleep(0.08)
    return result


def get_volume_ratio(symbol):
    candles = get_klines(symbol, "1h", limit=169)
    if len(candles) < 2:
        return 1.0
    volumes = [float(k[5]) for k in candles]
    avg = np.mean(volumes[:-1])
    return round(volumes[-1] / avg, 2) if avg > 0 else 1.0


def get_price_1h_open(symbol):
    candles = get_klines(symbol, "1h", limit=2)
    if not candles:
        return None
    return float(candles[-1][1])  # open của nến 1h hiện tại


def get_volume_24h(symbol):
    try:
        r = requests.get(f"{MEXC_SPOT}/api/v3/ticker/24hr",
                         params={"symbol": symbol},
                         headers=HEADERS, timeout=8)
        if r.status_code == 200:
            data = r.json()
            vol = float(data.get("quoteVolume", 0))
            if vol >= 1_000_000:
                return f"{vol/1_000_000:.2f}M"
            return f"{vol/1000:.1f}K"
    except Exception:
        pass
    return "N/A"


# ── FUNDING RATE ─────────────────────────────────────────────────────────────

def get_funding_rate(symbol):
    """Lấy funding rate từ MEXC Futures."""
    try:
        # Thử futures symbol (bỏ USDT, thêm _USDT)
        fsym = symbol.replace("USDT", "_USDT")
        r = requests.get(f"{MEXC_FUTURES}/api/v1/contract/funding_rate/{fsym}",
                         headers=HEADERS, timeout=8)
        if r.status_code == 200:
            data = r.json()
            rate = data.get("data", {}).get("fundingRate", None)
            if rate is not None:
                return round(float(rate) * 100, 4)
    except Exception:
        pass
    return None


# ── PHÂN KỲ ──────────────────────────────────────────────────────────────────

def detect_divergence(symbol):
    """
    Phát hiện phân kỳ RSI14 trên khung 15m.
    Trả về: 'bearish' | 'bullish' | None
    """
    candles = get_klines(symbol, "15m", limit=60)
    if len(candles) < 30:
        return None
    closes = [float(k[4]) for k in candles]
    highs  = [float(k[2]) for k in candles]
    lows   = [float(k[3]) for k in candles]

    # Tính RSI từng nến
    rsis = []
    for i in range(14, len(closes)):
        r = calc_rsi(closes[:i+1], 14)
        rsis.append(r)

    if len(rsis) < 10:
        return None

    # Lấy 20 nến gần nhất
    recent_closes = closes[-20:]
    recent_highs  = highs[-20:]
    recent_lows   = lows[-20:]
    recent_rsis   = rsis[-20:]

    # Bearish: giá tạo đỉnh cao hơn, RSI tạo đỉnh thấp hơn
    if (recent_closes[-1] > max(recent_closes[:-5]) and
            recent_rsis[-1] is not None and
            recent_rsis[-1] < max(r for r in recent_rsis[:-5] if r is not None)):
        return "bearish"

    # Bullish: giá tạo đáy thấp hơn, RSI tạo đáy cao hơn
    if (recent_closes[-1] < min(recent_closes[:-5]) and
            recent_rsis[-1] is not None and
            recent_rsis[-1] > min(r for r in recent_rsis[:-5] if r is not None)):
        return "bullish"

    return None


# ── SCORING & RATING ─────────────────────────────────────────────────────────

def normalize(v, lo, hi):
    if hi == lo: return 0.0
    return max(0.0, min(1.0, (v - lo) / (hi - lo)))


def compute_score(vol_ratio, p24h, p1h, rsi_1h, funding):
    s_vol  = normalize(vol_ratio, 1, 20) * 10
    s_24h  = normalize(p24h, 3, 60)     * 10
    s_1h   = normalize(p1h, 1, 20)      * 10
    # RSI 1h: điểm cao khi RSI 55-75 (đang tăng nhưng chưa overbought)
    s_rsi  = normalize(rsi_1h or 50, 40, 75) * 10
    # Funding dương = nhiều long = dễ pump thêm
    s_fund = normalize(funding or 0, 0, 0.02) * 10
    score  = s_vol*0.30 + s_24h*0.25 + s_1h*0.20 + s_rsi*0.15 + s_fund*0.10
    return round(score, 2)


def score_to_stars(score):
    if score >= 8:   return "⭐⭐⭐⭐⭐"
    if score >= 6.5: return "⭐⭐⭐⭐"
    if score >= 5:   return "⭐⭐⭐"
    if score >= 3.5: return "⭐⭐"
    return "⭐"


def score_to_rsi_div_score(score, rsi_1h):
    """Tính điểm RSI+Div kiểu 'RSI:X / Div:Y / Tổng:Z/5'"""
    rsi_score = 0
    if rsi_1h:
        if 55 <= rsi_1h < 70: rsi_score = 3
        elif 70 <= rsi_1h < 80: rsi_score = 2
        elif rsi_1h >= 80: rsi_score = 1
        elif 45 <= rsi_1h < 55: rsi_score = 2
    div_score = 1  # Mặc định 1
    total = min(rsi_score + div_score, 8)
    return rsi_score, div_score, total


# ── OVERBOUGHT CHECK ─────────────────────────────────────────────────────────

def get_overbought_tfs(rsi_dict):
    ob = [tf for tf, v in rsi_dict.items() if v and v >= 70]
    return ob


# ── FORMAT MESSAGE ───────────────────────────────────────────────────────────

def format_coin_message(coin):
    sym      = coin["symbol"]
    price    = coin["price"]
    p1h      = coin["change_1h"]
    p24h     = coin["change_24h"]
    funding  = coin["funding"]
    rsis     = coin["rsis"]
    div      = coin["divergence"]
    vol24h   = coin["vol24h"]
    open_1h  = coin["open_1h"]
    score    = coin["score"]
    stars    = score_to_stars(score)
    now      = datetime.now(timezone.utc).strftime("%-m/%-d/%Y, %-I:%M:%S %p")

    rsi_1h   = rsis.get("1h")
    rsi_score, div_score, total = score_to_rsi_div_score(score, rsi_1h)

    # Màu biến động 1h
    emoji_1h = "🟡" if p1h >= 5 else ("🟢" if p1h >= 0 else "🔴")

    # Funding
    fund_str = f"{funding:.4f}%" if funding is not None else "N/A"

    # RSI đa khung
    rsi_line = " • ".join(
        f"{tf} {rsi_emoji(rsis.get(tf))}{rsis.get(tf) or 'N/A'}"
        for tf in TIMEFRAMES
    )

    # Overbought
    ob_tfs = get_overbought_tfs(rsis)
    ob_str = ", ".join(ob_tfs) if ob_tfs else "Không có"

    # Phân kỳ 15m
    if div == "bearish":
        div_str = "• 15m: ⚠️ Phân kỳ giảm (2 đỉnh – RSI14)"
    elif div == "bullish":
        div_str = "• 15m: ✅ Phân kỳ tăng (2 đáy – RSI14)"
    else:
        div_str = "• 15m: Không phát hiện phân kỳ"

    # Giá 1h
    price_1h_str = f"{open_1h:.6f} → {price:.6f}" if open_1h else f"{price:.6f}"

    lines = [
        f"🚨 *${sym}* - Giá hiện tại: {price:.6f}",
        f"",
        f"📈 Biến động 1h: {emoji_1h}+{p1h:.2f}%",
        f"🇮🇹 Biến động 24h: +{p24h:.2f}%",
        f"",
        f"💰 Funding: {fund_str}",
        f"",
        f"⚡ Tín hiệu RSI & Funding (RSI:{rsi_score} / Div:{div_score} / Tổng:{total}/5):",
        stars,
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
        f"💲 Giá 1h: {price_1h_str}",
        f"📦 Volume 24h: {vol24h}",
        f"",
        f"⏰ {now}",
        f"📍 Alpha Pump Bot",
    ]

    return "\n".join(lines)


# ── MAIN SCAN ────────────────────────────────────────────────────────────────

def get_all_tickers():
    r = requests.get(f"{MEXC_SPOT}/api/v3/ticker/24hr", headers=HEADERS, timeout=15)
    r.raise_for_status()
    result = []
    for t in r.json():
        sym = t.get("symbol", "")
        if not sym.endswith("USDT") or sym in EXCLUDED:
            continue
        try:
            pct = float(t.get("priceChangePercent", 0))
            vol = float(t.get("quoteVolume", 0))
            if pct < MIN_PRICE_CHANGE or vol < MIN_QUOTE_VOLUME:
                continue
            result.append({
                "symbol":     sym,
                "change_24h": pct,
                "quoteVolume": vol,
                "price":      float(t.get("lastPrice", 0)),
            })
        except Exception:
            continue
    return result


def main():
    log.info("Bắt đầu quét MEXC...")
    tickers = get_all_tickers()
    log.info(f"{len(tickers)} candidates.")

    results = []
    for coin in tickers:
        sym = coin["symbol"]
        try:
            vol_ratio = get_volume_ratio(sym)
            if vol_ratio < MIN_VOL_RATIO:
                time.sleep(0.08)
                continue

            rsis    = get_rsi_all_tf(sym)
            p1h     = 0.0
            open_1h = get_price_1h_open(sym)
            if open_1h and open_1h > 0:
                p1h = round((coin["price"] - open_1h) / open_1h * 100, 2)

            funding = get_funding_rate(sym)
            div     = detect_divergence(sym)
            vol24h  = get_volume_24h(sym)
            score   = compute_score(vol_ratio, coin["change_24h"], p1h,
                                    rsis.get("1h"), funding)

            results.append({
                "symbol":     sym,
                "price":      coin["price"],
                "change_24h": coin["change_24h"],
                "change_1h":  p1h,
                "vol_ratio":  vol_ratio,
                "rsis":       rsis,
                "funding":    funding,
                "divergence": div,
                "vol24h":     vol24h,
                "open_1h":    open_1h,
                "score":      score,
            })
            log.info(f"✅ {sym} score={score} vol={vol_ratio}x 24h={coin['change_24h']:.1f}%")
        except Exception as e:
            log.warning(f"Lỗi {sym}: {e}")
        time.sleep(0.15)

    results.sort(key=lambda x: x["score"], reverse=True)
    top = results[:TOP_N]

    now = datetime.now(timezone.utc).strftime("%H:%M UTC %d/%m/%Y")
    if not top:
        send_telegram(f"🔇 *MEXC Alpha Scanner* — {now}\nKhông có coin đủ tiêu chuẩn lần quét này.")
        log.info("Không có coin đủ tiêu chuẩn.")
        return

    # Gửi header
    send_telegram(f"🔍 *MEXC Alpha Scanner* — {now}\nTop {len(top)} coin đáng chú ý:")
    time.sleep(0.5)

    # Gửi từng coin 1 tin riêng cho dễ đọc
    for c in top:
        msg = format_coin_message(c)
        send_telegram(msg)
        time.sleep(0.5)

    log.info(f"Đã gửi {len(top)} coin.")


if __name__ == "__main__":
    main()
