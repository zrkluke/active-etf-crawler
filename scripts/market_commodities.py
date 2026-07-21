from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request
from typing import TypedDict

class CommodityData(TypedDict):
    price: float
    change: float
    change_rate: float

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

def fetch_taiex_data() -> tuple[float, float, float]:
    """
    Fetches TAIEX (^TWII) data and returns (latest_close, ma60, bias_ratio)
    """
    url = "https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII?range=120d&interval=1d"
    data = fetch_yahoo_json(url)
    
    result_list = data.get("chart", {}).get("result", [])
    if not result_list:
        raise ValueError("No result data found in Yahoo Finance response")
    result = result_list[0]
    
    indicators = result.get("indicators", {}).get("quote", [{}])[0]
    close_prices = indicators.get("close", [])
    
    # Filter out None values (e.g. non-trading days)
    valid_closes = [c for c in close_prices if c is not None]
    
    if len(valid_closes) < 60:
        raise ValueError(f"Not enough valid close prices to calculate MA60. Found: {len(valid_closes)}")
    
    latest_close = valid_closes[-1]
    ma60_closes = valid_closes[-60:]
    ma60 = sum(ma60_closes) / 60
    bias_ratio = (latest_close - ma60) / ma60 * 100
    
    return latest_close, ma60, bias_ratio

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
        taiex_close, taiex_ma60, taiex_bias = fetch_taiex_data()
        # 📈 加權指數: 44,232.87
        lines.append(f"\U0001F4C8 \u52a0\u6b0a\u6307\u6578: {taiex_close:,.2f}")
        #    └─ 季線 (MA60): 43,709.96 (乖離率: +1.20%)
        lines.append(f"   \u2514\u2500 \u5b63\u7dda (MA60): {taiex_ma60:,.2f} (\u4e56\u96e2\u7387: {taiex_bias:+.2f}%)")
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

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(fetch_market_and_commodities_summary())
