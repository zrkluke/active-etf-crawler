# 每日大盤與商品數據爬蟲技術規格說明書 (Market Data Crawler Specs)

本文件詳細記錄本專案中針對「今日加權指數與商品數據」(位於 [scripts/market_commodities.py](file:///c:/PythonSideProjects/主動ETF爬蟲/scripts/market_commodities.py))、「微台指散戶多空比」(位於 [scripts/retail_ratio.py](file:///c:/PythonSideProjects/主動ETF爬蟲/scripts/retail_ratio.py)) 以及「上市/上櫃融資餘額與增減量」(位於 [scripts/margin_balance.py](file:///c:/PythonSideProjects/主動ETF爬蟲/scripts/margin_balance.py)) 的實作技術細節、介面規範、請求格式與計算邏輯。

---

## 1. Yahoo Finance API 規格說明 (大盤與商品價格)

為了避免第三方財經網站（如玩股網）強大的 Cloudflare 機器人防禦阻擋，本專案採用 **Yahoo Finance 公開 JSON API** 做為穩定且免費的數據源。

### 1.1 查詢加權指數 (TAIEX, `^TWII`)
*   **API 網址**：`https://query1.finance.yahoo.com/v8/finance/chart/%5ETWII`
*   **請求方法**：`GET`
*   **查詢參數**：
    *   `range=120d`：取得過去 120 天的歷史數據（用以確保扣除假日後仍有足夠的 60 天交易日）。
    *   `interval=1d`：以「日」為間隔。
*   **計算季線 (MA60) 與乖離率**：
    *   由於遇假日或休市時，Yahoo Finance 的收盤價陣列可能包含 `None` 缺失值，程式會先進行過濾：`valid_closes = [c for c in close_prices if c is not None]`。
    *   取最後 60 筆有效收盤價計算平均值：`MA60 = sum(valid_closes[-60:]) / 60`。
    *   乖離率計算公式：`乖離率 = (今日收盤價 - MA60) / MA60 * 100%`。

### 1.2 查詢商品期貨價格 (黃金 `GC=F`、布蘭特原油 `BZ=F`)
*   **API 網址**：`https://query1.finance.yahoo.com/v8/finance/chart/{SYMBOL}`
*   **請求方法**：`GET`
*   **查詢參數**：
    *   `range=2d`：取得最近 2 個交易日的數據。
    *   `interval=1d`：以「日」為間隔。
*   **漲跌幅計算**：
    *   優先自 JSON 回傳的 `meta` 欄位中提取今日最新價格 `regularMarketPrice` 與前一日收盤價 `chartPreviousClose`。
    *   如果欄位缺失，則降級解析價格數值陣列：`Price = closes[-1]`，`PrevClose = closes[-2]`。
    *   漲跌幅計算公式：`漲跌幅 = (今日價格 - 昨日收盤價) / 昨日收盤價 * 100%`。

---

## 2. 臺灣期貨交易所官網爬蟲規格說明 (微台指散戶多空比)

期交所雖然有 OpenAPI 服務，但資料同步有高達 1 天的延遲。為了能在交易日晚上 9 點前即時取得今日最新數據，本專案直接模擬瀏覽器發送 `POST` 表單請求給期交所官網查詢系統。

### 2.1 查詢「全市場未平倉總量」
*   **目標網址**：`https://www.taifex.com.tw/cht/3/futDailyMarketReport` (期貨每日交易行情)
*   **請求方法**：`POST` (Content-Type: `application/x-www-form-urlencoded`)
*   **表單參數 (Payload)**：
    *   `queryDate`：查詢日期，格式為 `YYYY/MM/DD` (例如 `2026/07/21`)。
    *   `MarketCode`：`0` (代表一般交易時段，避開盤後/夜盤重複計算)。
    *   `commodity_id`：`TMF` (微型臺指期貨契約代碼)。
*   **解析與提取邏輯**：
    *   伺服器會回傳完整的 HTML 網頁。
    *   使用正則表達式 `re.findall(r'<tr[^>]*>.*?</tr>', html)` 提取所有表格行，並篩選包含 `TMF` 的行。
    *   將每一行解析為欄位陣列，提取 **Index 9** 欄位（對應網頁中的「未平倉量」）。
    *   加總 TMF 旗下所有不同到期月份（如 202608、202609 等）的未平倉量，得到全市場未平倉量總和。

### 2.2 查詢「三大法人未平倉部位」
*   **目標網址**：`https://www.taifex.com.tw/cht/3/futContractsDateDown` (三大法人期貨交易部位下載)
*   **請求方法**：`POST` (Content-Type: `application/x-www-form-urlencoded`)
*   **表單參數 (Payload)**：
    *   `queryStartDate`：查詢起始日，格式 `YYYY/MM/DD`。
    *   `queryEndDate`：查詢結束日，格式 `YYYY/MM/DD`。
    *   `commodityId`：空字串 (下載全部商品)。
*   **解析與提取邏輯**：
    *   伺服器會回傳 `Big5 (CP950)` 編碼的 CSV 數據。
    *   使用 Python 內建 `csv` 模組讀取。
    *   過濾商品名稱包含「微型」的行，並檢查身分別（身份別必須匹配 `自營商`、`投信`、`外資及陸資`）。
    *   加總這三類法人的「多方未平倉口數」與「空方未平倉口數」。

### 2.3 散戶多空比計算
*   **計算公式**：
    *   `散戶多單 = 全市場未平倉總量 - 三大法人多方未平倉總量`
    *   `散戶空單 = 全市場未平倉總量 - 三大法人空方未平倉總量`
    *   `散戶多空比 = (散戶多單 - 散戶空單) / 全市場未平倉總量 * 100%`
*   **非交易日處置**：
    *   期交所網頁在假日或尚未公佈數據時，其 HTML 返回的未平倉口數會是 0。
    *   程式一旦偵測到總未平倉量為 0，會立即拋出 `ValueError("No trading data")`。
    *   `main.py` 會捕捉此異常，輸出 `Today is a non-trading day. Skipping...` 並**完全跳過 Telegram 訊息的發送**，防止發送過期資料。

---

## 3. 上市與上櫃融資餘額規格說明 (TWSE & TPEx)

我們直接讀取證交所與櫃買中心官方前端所調用的 AJAX API。這些介面在交易日收盤後均會產出 pre-calculated（預先算好）的前日與今日餘額，這讓我們**在單次連線內就能直接算得今日增減**，不需要發送多次歷史查詢。

### 3.1 上市融資餘額 (TWSE)
*   **API 網址**：`https://www.twse.com.tw/exchangeReport/MI_MARGN?response=json&date={YYYYMMDD}&selectType=MS`
*   **請求方法**：`GET`
*   **解析邏輯**：
    *   在回傳的 `tables` 陣列中，尋找標題 Title 包含「信用交易統計」的表格。
    *   遍歷 `data` 陣列，找到 `row[0]` 匹配為 `融資金額(仟元)` 的行。
    *   欄位對應：
        *   `row[4]`：前日餘額 (仟元)
        *   `row[5]`：今日餘額 (仟元)
    *   換算公式（億元）：
        *   `今日餘額 (億) = float(row[5]) / 100,000`
        *   `增減金額 (億) = (float(row[5]) - float(row[4])) / 100,000`

### 3.2 上櫃融資餘額 (TPEx)
*   **API 網址**：`https://www.tpex.org.tw/web/stock/margin_trading/margin_balance/margin_bal_result.php?l=zh-tw&d={MINGUO_YEAR}/MM/DD`
    *   *註：櫃買中心日期格式需使用「中華民國曆」格式（如 2026/07/21 需轉換為 115/07/21）。*
*   **請求方法**：`GET`
*   **解析邏輯**：
    *   讀取回傳的 `tables[0]` 下的 `summary`（表尾統計）欄位。
    *   遍歷 `summary` 陣列，找到 `row[1]` 匹配為 `融資金(仟元)` 的行。
    *   欄位對應：
        *   `row[2]`：前資餘額 (仟元)
        *   `row[6]`：今日資餘額 (仟元)
    *   換算公式（億元）：
        *   `今日餘額 (億) = float(row[6]) / 100,000`
        *   `增減金額 (億) = (float(row[6]) - float(row[2])) / 100,000`

---

## 4. 字元與平台相容性設計 (Unicode Escapes)

由於 Windows 本地執行環境預設會使用作業系統語言解讀原始碼檔案（中文系統預設解讀為 `CP950`），為了保證程式碼在 GitHub Actions (Linux UTF-8) 與 Windows 本地端均能正確解譯，不產生亂碼，**程式中所有寫入字串的中文均採用 Unicode 避開序列定義**：

*   `"【今日大盤與商品數據】"` &rarr; `"\u3010\u4eca\u65e5\u5927\u76e4\u8207\u5546\u54c1\u6578\u64da\u3011"`
*   `"加權指數"` &rarr; `"\u52a0\u6b0a\u6307\u6578"`
*   `"微台指散戶多空比"` &rarr; `"\u5fae\u53f0\u6307\u6563\u6236\u591a\u7a7a\u6bd4"`
*   `"自營商"` &rarr; `"\u81ea\u71df\u5546"`
*   `"投信"` &rarr; `"\u6295\u4fe1"`
*   `"外資及陸資"` &rarr; `"\u5916\u8cc7\u53ca\u9678\u8cc7"`
*   `"上市融資餘額"` &rarr; `"\u4e0a\u5e02\u878d\u8cc7\u9918\u984d"`
*   `"上櫃融資餘額"` &rarr; `"\u4e0a\u6ac3\u878d\u8cc7\u9918\u984d"`
*   `"億"` &rarr; `"\u5104"`
*   `"增減"` &rarr; `"\u589e\u6e1b"`
