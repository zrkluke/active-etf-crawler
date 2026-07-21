from __future__ import annotations

import csv
import datetime
import io
import re
import sys
import urllib.parse
import urllib.request

def get_taipei_today() -> datetime.date:
    """
    Returns current date in Taipei timezone (UTC+8).
    """
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    taipei_now = utc_now + datetime.timedelta(hours=8)
    return taipei_now.date()

def fetch_latest_retail_ratio() -> tuple[str, float]:
    """
    Fetches TMF retail long-short ratio strictly for TODAY (Taipei timezone).
    Does not fall back to previous dates.
    Returns (date_str_yyyy_mm_dd, ratio_percentage).
    """
    today = get_taipei_today()
    # Format as YYYY/MM/DD which is expected by TAIFEX forms
    date_str = today.strftime("%Y/%m/%d")
    
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    
    # 1. Query Daily Market Report (HTML) to get TMF Total Open Interest
    url_market = "https://www.taifex.com.tw/cht/3/futDailyMarketReport"
    payload_market = urllib.parse.urlencode({
        "queryDate": date_str,
        "MarketCode": "0",  # Day session
        "commodity_id": "TMF"
    }).encode("utf-8")
    
    req_market = urllib.request.Request(url_market, data=payload_market, headers=headers, method="POST")
    with urllib.request.urlopen(req_market, timeout=15) as resp:
        html = resp.read().decode("utf-8", errors="ignore")
        
        rows = re.findall(r'<tr[^>]*>.*?</tr>', html, re.DOTALL)
        tmf_rows = [r for r in rows if "TMF" in r]
        
        total_oi = 0
        for row in tmf_rows:
            cols = re.findall(r'<td[^>]*>(.*?)</td>', row, re.DOTALL)
            cols_clean = [re.sub(r'<[^>]+>', '', c).strip().replace(",", "") for c in cols]
            
            # OpenInterest is at Index 9 in the parsed columns
            if len(cols_clean) >= 10:
                oi_val = cols_clean[9]
                if oi_val.isdigit():
                    total_oi += int(oi_val)
                    
        # If total open interest is 0, today is a holiday, weekend, or data is not published yet
        if total_oi == 0:
            raise ValueError(f"\u7576\u65e5\u7121\u4ea4\u6613\u8cc7\u6599 (No trading data for {date_str})")
            
        # 2. Query Major Traders (CSV) for Institutional Positions
        url_traders = "https://www.taifex.com.tw/cht/3/futContractsDateDown"
        payload_traders = urllib.parse.urlencode({
            "queryStartDate": date_str,
            "queryEndDate": date_str,
            "commodityId": ""
        }).encode("utf-8")
        
        req_traders = urllib.request.Request(url_traders, data=payload_traders, headers=headers, method="POST")
        with urllib.request.urlopen(req_traders, timeout=15) as resp_traders:
            content = resp_traders.read().decode("cp950", errors="ignore")
            
            # If TAIFEX returns an alert script, it means no data or query error
            if "alert(" in content:
                raise ValueError(f"\u7576\u65e5\u7121\u6cd5\u53d6\u5f97\u4e09\u5927\u6cd5\u4eba\u8cc7\u6599 (Cannot get institutional data for {date_str})")
                
            reader = csv.reader(io.StringIO(content))
            csv_rows = list(reader)
            
            inst_long = 0
            inst_short = 0
            
            # Institutional names in TAIFEX: 自營商, 投信, 外資及陸資
            inst_types = {
                "\u81ea\u71df\u5546",       # 自營商
                "\u6295\u4fe1",             # 投信
                "\u5916\u8cc7\u53ca\u9678\u8cc7" # 外資及陸資
            }
            
            for r in csv_rows:
                if len(r) > 12:
                    contract = r[1].strip()
                    trader_type = r[2].strip()
                    
                    if "\u5fae\u578b" in contract:
                        long_oi_str = r[9].strip().replace(",", "")
                        short_oi_str = r[11].strip().replace(",", "")
                        
                        if trader_type in inst_types:
                            if long_oi_str.isdigit():
                                inst_long += int(long_oi_str)
                            if short_oi_str.isdigit():
                                inst_short += int(short_oi_str)
                                
        retail_long = total_oi - inst_long
        retail_short = total_oi - inst_short
        ratio = ((retail_long - retail_short) / total_oi) * 100
        
        return date_str, ratio

def fetch_retail_ratio_summary() -> str:
    """
    Fetches TMF retail ratio and formats it as a single line string.
    """
    try:
        date_str, ratio = fetch_latest_retail_ratio()
        # 微台指散戶多空比
        return f"\u5fae\u53f0\u6307\u6563\u6236\u591a\u7a7a\u6bd4 ({date_str}): {ratio:+.2f}%"
    except Exception as e:
        # 微台指散戶多空比: 抓取失敗
        err_msg = str(e)
        if "No trading data" in err_msg:
            reason = "\u7576\u65e5\u7121\u4ea4\u6613\u8cc7\u6599" # 當日無交易資料
        else:
            reason = err_msg
        return f"\u5fae\u53f0\u6307\u6563\u6236\u591a\u7a7a\u6bd4: \u6293\u53d6\u5931\u6557 ({reason})"

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(fetch_retail_ratio_summary())
