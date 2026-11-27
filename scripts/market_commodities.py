from __future__ import annotations

import datetime
import html
import json
import sys
import urllib.parse
import urllib.request
from typing import Literal, TypedDict

class CommodityData(TypedDict):
    price: float
    change: float
    change_rate: float

class TaiexData(TypedDict):
    close: float
    ma20: float
    ma20_bias: float
    ma60: float
    ma60_bias: float
    prev_close: float | None
    prev_ma20: float | None
    prev_ma60: float | None

class PositionAdvice(TypedDict):
    text: str
    is_crossover: bool
    signal: Literal["break_down", "reclaim", "hold"]

def fetch_yahoo_json(url: str) -> dict:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            )
        }
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))

def fetch_taiex_data() -> TaiexData:
    """
    Fetches TAIEX (^TWII) data and returns latest close, MA20/MA60, and their bias ratios.
    """
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?range=120d&interval=1d"
    data = fetch_yahoo_json(url)
    
    result_list = data.get("chart", {}).get("result", [])
    if not result_list:
        raise ValueError("No result data found in Yahoo Finance response")
    result = result_list[0]
    meta = result.get("meta", {})
    timestamps = result.get("timestamp", [])
    
    indicators = result.get("indicators", {}).get("quote", [{}])[0]
    close_prices = indicators.get("close", [])
    
    tz_taipei = datetime.timezone(datetime.timedelta(hours=8))
    regular_price = meta.get("regularMarketPrice")
    regular_time = meta.get("regularMarketTime")
    
    if timestamps and len(timestamps) == len(close_prices):
        # Pair timestamps with non-None close prices to track trading dates accurately
        dated_closes: list[tuple[datetime.date, float]] = []
        for ts, close in zip(timestamps, close_prices):
            if close is not None:
                bar_date = datetime.datetime.fromtimestamp(ts, tz_taipei).date()
                dated_closes.append((bar_date, float(close)))
        
        # Yahoo Finance often leaves the latest trading day's close as None in indicators.quote[0].close
        # even after market close, while meta.regularMarketPrice already holds the latest close.
        if regular_price is not None and regular_time is not None:
            market_date = datetime.datetime.fromtimestamp(regular_time, tz_taipei).date()
            if not dated_closes or market_date > dated_closes[-1][0]:
                dated_closes.append((market_date, float(regular_price)))
            elif market_date == dated_closes[-1][0]:
                dated_closes[-1] = (market_date, float(regular_price))
        
        valid_closes = [c for _, c in dated_closes]
    else:
        # Fallback if timestamps are unavailable
        valid_closes = [float(c) for c in close_prices if c is not None]
        if close_prices and close_prices[-1] is None and regular_price is not None:
            valid_closes.append(float(regular_price))
    
    if len(valid_closes) < 60:
        raise ValueError(f"Not enough valid close prices to calculate MA60. Found: {len(valid_closes)}")
    
    latest_close = valid_closes[-1]
    ma20_closes = valid_closes[-20:]
    ma20 = sum(ma20_closes) / 20
    ma20_bias = (latest_close - ma20) / ma20 * 100

    ma60_closes = valid_closes[-60:]
    ma60 = sum(ma60_closes) / 60
    ma60_bias = (latest_close - ma60) / ma60 * 100

    prev_close: float | None = None
    prev_ma20: float | None = None
    prev_ma60: float | None = None
    if len(valid_closes) >= 61:
        prev_close = valid_closes[-2]
        prev_ma20 = sum(valid_closes[-21:-1]) / 20
        prev_ma60 = sum(valid_closes[-61:-1]) / 60
    
    return {
        "close": latest_close,
        "ma20": ma20,
        "ma20_bias": ma20_bias,
        "ma60": ma60,
        "ma60_bias": ma60_bias,
        "prev_close": prev_close,
        "prev_ma20": prev_ma20,
        "prev_ma60": prev_ma60,
    }

def evaluate_position_advice(taiex: TaiexData) -> PositionAdvice:
    """
    Evaluates position sizing advice based on TAIEX close relative to MA20 and MA60:
    - Above both MA20 and MA60: maintain >= 70% position
    - Below MA20 (and above MA60): reduce to 50% position
    - Below MA60: reduce further to 20%-50% position
    Also detects daily crossover events (break below / reclaim above MA20 or MA60).
    """
    close = taiex["close"]
    ma20 = taiex["ma20"]
    ma60 = taiex["ma60"]
    prev_close = taiex["prev_close"]
    prev_ma20 = taiex["prev_ma20"]
    prev_ma60 = taiex["prev_ma60"]

    has_break_down = False
    has_reclaim = False
    events: list[str] = []
    if prev_close is not None and prev_ma20 is not None and prev_ma60 is not None:
        if prev_close >= prev_ma20 and close < ma20:
            # 跌破月線
            events.append("\u8dcc\u7834\u6708\u7dda")
            has_break_down = True
        elif prev_close < prev_ma20 and close >= ma20:
            # 站上月線
            events.append("\u7ad9\u4e0a\u6708\u7dda")
            has_reclaim = True

        if prev_close >= prev_ma60 and close < ma60:
            # 跌破季線
            events.append("\u8dcc\u7834\u5b63\u7dda")
            has_break_down = True
        elif prev_close < prev_ma60 and close >= ma60:
            # 站上季線
            events.append("\u7ad9\u4e0a\u5b63\u7dda")
            has_reclaim = True

    is_crossover = bool(events)
    if has_break_down:
        signal: Literal["break_down", "reclaim", "hold"] = "break_down"
    elif has_reclaim:
        signal = "reclaim"
    else:
        signal = "hold"
    # 【事件1、事件2】
    joined_events = "\u3001".join(events)
    event_tag = f"\u3010{joined_events}\u3011" if events else ""

    if close >= ma20 and close >= ma60:
        if is_crossover:
            # 【...】建議拉高至 7 成以上高水位
            text = f"{event_tag}\u5efa\u8b70\u62c9\u9ad8\u81f3 7 \u6210\u4ee5\u4e0a\u9ad8\u6c34\u4f4d"
        else:
            # 在月、季線之上，維持 7 成以上高水位
            text = "\u5728\u6708\u3001\u5b63\u7dda\u4e4b\u4e0a\uff0c\u7dad\u6301 7 \u6210\u4ee5\u4e0a\u9ad8\u6c34\u4f4d"
    elif close < ma60:
        if is_crossover:
            # 跌破季線 -> 建議減碼至 2~5 成水位
            if "\u8dcc\u7834\u5b63\u7dda" in events:
                text = f"{event_tag}\u5efa\u8b70\u6e1b\u78bc\u81f3 2~5 \u6210\u6c34\u4f4d"
            elif close >= ma20:
                # 仍在季線之下，建議維持 2~5 成水位
                text = f"{event_tag}\u4ecd\u5728\u5b63\u7dda\u4e4b\u4e0b\uff0c\u5efa\u8b70\u7dad\u6301 2~5 \u6210\u6c34\u4f4d"
            else:
                # 在季線之下，建議減碼至 2~5 成水位
                text = f"{event_tag}\u5728\u5b63\u7dda\u4e4b\u4e0b\uff0c\u5efa\u8b70\u6e1b\u78bc\u81f3 2~5 \u6210\u6c34\u4f4d"
        else:
            if close >= ma20:
                # 在月線之上、季線之下，建議維持 2~5 成水位
                text = "\u5728\u6708\u7dda\u4e4b\u4e0a\u3001\u5b63\u7dda\u4e4b\u4e0b\uff0c\u5efa\u8b70\u7dad\u6301 2~5 \u6210\u6c34\u4f4d"
            else:
                # 在月、季線之下，建議維持 2~5 成水位
                text = "\u5728\u6708\u3001\u5b63\u7dda\u4e4b\u4e0b\uff0c\u5efa\u8b70\u7dad\u6301 2~5 \u6210\u6c34\u4f4d"
    else:
        # close < ma20 and close >= ma60
        if is_crossover:
            if "\u8dcc\u7834\u6708\u7dda" in events:
                # 建議減碼至 5 成水位
                text = f"{event_tag}\u5efa\u8b70\u6e1b\u78bc\u81f3 5 \u6210\u6c34\u4f4d"
            else:
                # 仍在月線之下，建議調整至 5 成水位
                text = f"{event_tag}\u4ecd\u5728\u6708\u7dda\u4e4b\u4e0b\uff0c\u5efa\u8b70\u8abf\u6574\u81f3 5 \u6210\u6c34\u4f4d"
        else:
            # 在月線之下、季線之上，建議維持 5 成水位
            text = "\u5728\u6708\u7dda\u4e4b\u4e0b\u3001\u5b63\u7dda\u4e4b\u4e0a\uff0c\u5efa\u8b70\u7dad\u6301 5 \u6210\u6c34\u4f4d"

    return {
        "text": text,
        "is_crossover": is_crossover,
        "signal": signal,
    }

def fetch_commodity_data(symbol: str) -> CommodityData:
    """
    Fetches regular price and change statistics for a commodity (e.g., GC=F or BZ=F)
    """
    escaped_sym = urllib.parse.quote(symbol)
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{escaped_sym}?range=2d&interval=1d"
    data = fetch_yahoo_json(url)
    
    result_list = data.get("chart", {}).get("result", [])
    if not result_list:
        raise ValueError(f"No result data found in Yahoo Finance response for {symbol}")
    result = result_list[0]
    meta = result.get("meta", {})
    
    price = meta.get("regularMarketPrice")
    prev_close = meta.get("chartPreviousClose")
    
    if price is None or prev_close is None:
        indicators = result["indicators"]["quote"][0]
        close_prices = [c for c in indicators["close"] if c is not None]
        if len(close_prices) >= 2:
            price = close_prices[-1]
            prev_close = close_prices[-2]
        elif len(close_prices) == 1:
            price = close_prices[0]
            prev_close = meta.get("previousClose") or price
        else:
            raise ValueError(f"No valid price data found for {symbol}")
            
    change = price - prev_close
    change_rate = (change / prev_close) * 100 if prev_close else 0.0
    
    return {
        "price": price,
        "change": change,
        "change_rate": change_rate
    }

def fetch_market_and_commodities_summary() -> str:
    """
    Fetches stock and commodity data and returns formatted text lines (Style A).
    Using Unicode escapes for all Chinese and Emojis to guarantee compatibility.
    """
    lines = []
    
    # 1. TAIEX (📈 加權指數)
    try:
        taiex = fetch_taiex_data()
        advice = evaluate_position_advice(taiex)
        # 📈 加權指數: 44,232.87
        lines.append(f"\U0001F4C8 \u52a0\u6b0a\u6307\u6578: {taiex['close']:,.2f}")
        #    ├─ 月線 (MA20): 44,012.34 (乖離率: +0.50%)
        lines.append(f"   \u251c\u2500 \u6708\u7dda (MA20): {taiex['ma20']:,.2f} (\u4e56\u96e2\u7387: {taiex['ma20_bias']:+.2f}%)")
        #    ├─ 季線 (MA60): 43,709.96 (乖離率: +1.20%)
        lines.append(f"   \u251c\u2500 \u5b63\u7dda (MA60): {taiex['ma60']:,.2f} (\u4e56\u96e2\u7387: {taiex['ma60_bias']:+.2f}%)")
        #    └─ 💰/🔥/🚨 資金水位: ...
        if advice["signal"] == "break_down":
            advice_icon = "\U0001f6a8"  # 🚨
        elif advice["signal"] == "reclaim":
            advice_icon = "\U0001f525"  # 🔥
        else:
            advice_icon = "\U0001f4b0"  # 💰
        lines.append(f"   \u2514\u2500 {advice_icon} \u8cc7\u91d1\u6c34\u4f4d: {advice['text']}")
    except Exception as e:
        # 📈 加權指數: 抓取失敗
        lines.append(f"\U0001F4C8 \u52a0\u6b0a\u6307\u6578: \u6293\u53d6\u5931\u6557 ({e})")
        
    # 2. Gold (🪙 國際金價)
    try:
        gold = fetch_commodity_data("GC=F")
        # 🪙 國際金價: 4,062.30 (漲跌幅: +1.30%)
        lines.append(f"\U0001FA99 \u570b\u969b\u91d1\u50f9: {gold['price']:,.2f} (\u6f32\u8dcc\u5e45: {gold['change_rate']:+.2f}%)")
    except Exception as e:
        # 🪙 國際金價: 抓取失敗
        lines.append(f"\U0001FA99 \u570b\u969b\u91d1\u50f9: \u6293\u53d6\u5931\u6557 ({e})")
        
    # 3. Brent Oil (🛢️ 布蘭特原油)
    try:
        brent = fetch_commodity_data("BZ=F")
        # 🛢️ 布蘭特原油: 91.15 (漲跌幅: +2.16%)
        lines.append(f"\U0001F6E2\uFE0F \u5e03\u862d\u7279\u539f\u6cb9: {brent['price']:,.2f} (\u6f32\u8dcc\u5e45: {brent['change_rate']:+.2f}%)")
    except Exception as e:
        # 🛢️ 布蘭特原油: 抓取失敗
        lines.append(f"\U0001F6E2\uFE0F \u5e03\u862d\u7279\u539f\u6cb9: \u6293\u53d6\u5931\u6557 ({e})")
        
    return "\n".join(lines)

def format_market_summary_telegram_html(summary: str) -> str:
    """
    Escapes text for Telegram HTML parse_mode and bolds crossover alert lines
    marked with siren/fire emojis (since Telegram does not support colored fonts).
    """
    formatted_lines = []
    for line in summary.splitlines():
        escaped = html.escape(line)
        if "\U0001f6a8" in line or "\U0001f525" in line:
            formatted_lines.append(f"<b>{escaped}</b>")
        else:
            formatted_lines.append(escaped)
    return "\n".join(formatted_lines)

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    summary = fetch_market_and_commodities_summary()
    if sys.stdout.isatty():
        colored_lines = [
            f"\033[31m{line}\033[0m" if ("\U0001f6a8" in line or "\U0001f525" in line) else line
            for line in summary.splitlines()
        ]
        print("\n".join(colored_lines))
    else:
        print(summary)
