from __future__ import annotations

import datetime
import json
import sys
import urllib.request

def get_taipei_today() -> datetime.date:
    """
    Returns current date in Taipei timezone (UTC+8).
    """
    utc_now = datetime.datetime.now(datetime.timezone.utc)
    taipei_now = utc_now + datetime.timedelta(hours=8)
    return taipei_now.date()

def fetch_twse_margin(date_str_yyyymmdd: str) -> tuple[float, float]:
    """
    Fetches Listed (TWSE) margin balance for the given date.
    Returns (today_balance_in_billion, change_in_billion)
    """
    url = f"https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date={date_str_yyyymmdd}&selectType=MS"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        
    if data.get("stat") != "OK" or "tables" not in data:
        raise ValueError(f"\u7576\u65e5\u7121\u4ea4\u6613\u8cc7\u6599 (TWSE stat: {data.get('stat')})")
        
    tables = data["tables"]
    target_row = None
    for table in tables:
        title = table.get("title", "")
        if title and "\u4fe1\u7528\u4ea4\u6613\u7d71\u8a08" in title:
            rows = table.get("data", [])
            for r in rows:
                if r and len(r) > 5 and "\u878d\u8cc7\u91d1\u984d" in r[0]:
                    target_row = r
                    break
            if target_row:
                break
                
    if not target_row:
        raise ValueError("Could not find margin amount row in TWSE response")
        
    yesterday = float(target_row[4].replace(",", ""))
    today = float(target_row[5].replace(",", ""))
    change = today - yesterday
    
    return today / 100000, change / 100000

def fetch_tpex_margin(date_str_yyyymmdd: str) -> tuple[float, float]:
    """
    Fetches OTC (TPEx) margin balance for the given date.
    Returns (today_balance_in_billion, change_in_billion)
    """
    parts = date_str_yyyymmdd.split("/")
    if len(parts) == 3:
        g_year = int(parts[0])
        m_year = g_year - 1911
        date_str_minguo = f"{m_year}/{parts[1]}/{parts[2]}"
    else:
        date_str_minguo = date_str_yyyymmdd

    url = f"https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php?l=zh-tw&d={date_str_minguo}"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0 Safari/537.36"
        )
    }
    
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        
    if "tables" not in data or len(data["tables"]) == 0:
         raise ValueError("\u7576\u65e5\u7121\u4ea4\u6613\u8cc7\u6599 (No trading data in TPEx tables)")
         
    table = data["tables"][0]
    summary = table.get("summary", [])
    
    target_row = None
    for r in summary:
        if r and len(r) > 6 and "\u878d\u8cc7\u91d1" in r[1]:
            target_row = r
            break
            
    if not target_row:
        raise ValueError("Could not find margin amount row in TPEx summary")
        
    yesterday = float(target_row[2].replace(",", ""))
    today = float(target_row[6].replace(",", ""))
    change = today - yesterday
    
    return today / 100000, change / 100000

def fetch_margin_balance_summary(raise_on_error: bool = True) -> str:
    """
    Fetches listed & OTC margin balances and returns formatted lines (Style A).
    If raise_on_error is True, raises ValueError if either TWSE or TPEx data is not available yet.
    """
    today = get_taipei_today()
    date_str_twse = today.strftime("%Y%m%d")
    date_str_tpex = today.strftime("%Y/%m/%d")
    
    lines = []
    
    # 1. TWSE (Listed) - 💰 上市融資餘額
    try:
        twse_val, twse_change = fetch_twse_margin(date_str_twse)
        lines.append(f"\U0001F4B0 \u4e0a\u5e02\u878d\u8cc7\u9918\u984d: {twse_val:,.2f} \u5104 (\u589e\u6e1b: {twse_change:+,.2f} \u5104)")
    except Exception as e:
        if raise_on_error:
            raise ValueError(f"\u4e0a\u5e02\u878d\u8cc7\u9918\u984d\u5c1a\u672a\u516c\u4f48 ({e})")
        lines.append(f"\U0001F4B0 \u4e0a\u5e02\u878d\u8cc7\u9918\u984d: \u6293\u53d6\u5931\u6557 ({e})")
        
    # 2. TPEx (OTC) - 💰 上櫃融資餘額
    try:
        tpex_val, tpex_change = fetch_tpex_margin(date_str_tpex)
        lines.append(f"\U0001F4B0 \u4e0a\u6ac3\u878d\u8cc7\u9918\u984d: {tpex_val:,.2f} \u5104 (\u589e\u6e1b: {tpex_change:+,.2f} \u5104)")
    except Exception as e:
        if raise_on_error:
            raise ValueError(f"\u4e0a\u6ac3\u878d\u8cc7\u9918\u984d\u5c1a\u672a\u516c\u4f48 ({e})")
        lines.append(f"\U0001F4B0 \u4e0a\u6ac3\u878d\u8cc7\u9918\u984d: \u6293\u53d6\u5931\u6557 ({e})")
        
    return "\n".join(lines)

if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    print(fetch_margin_balance_summary(raise_on_error=False))
