# MoneyDJ 反爬蟲 503 阻擋故障排查記錄

* **日期**：2026-07-19
* **現象**：GitHub Actions 每日排程自 2026-07-18 起，連續兩天抓取 MoneyDJ 持股資料皆失敗，錯誤日誌顯示 `The read operation timed out`（讀取超時）。在此之前皆能正常運行。
* **目標網址**：`https://www.moneydj.com/ETF/X/Basic/Basic0007B.xdjhtm?etfid={symbol}`

---

## 診斷與排查過程

### 階段一：全球連線測試（排除 IP 大範圍封鎖）
* **假設**：MoneyDJ 的防火牆對海外所有 IP 或者是公有雲 IP 進行了 Silent Drop（悄悄丟棄連線），導致超時。
* **驗證方式**：在本地執行 API 腳本，透過 `check-host.net` 全球 59 個分佈式節點對目標網址發起 HTTP 請求。
* **測試結果**：
  * **59 個節點中，有 58 個成功連線**（HTTP 200）。
  * 成功節點包含：日本東京（0.117s）、新加坡（0.193s）、美國洛杉磯（0.468s）等。
* **結論**：MoneyDJ **並未全面封鎖海外 IP**，Actions 伺服器到 MoneyDJ 網路連線的路由本身是通暢的。

### 階段二：GitHub Actions 環境實測（抓出鐵證）
* **驗證方式**：在 GitHub Actions 的工作流中暫時加入 `Network Diagnostics` 步驟，利用無偽裝 Headers 的 Python `urllib` 與系統層級 `curl` 對比測試。
* **實測數據**（工作流 Run ID: [29692075743](https://github.com/zrkluke/active-etf-crawler/actions/runs/29692075743)）：
  1. **`curl` 測試**：連線成功並順利取得 **HTTP 200**。
     ```text
     HTTP/2 200
     server: Microsoft-IIS/10.0
     ```
  2. **`urllib` 測試**：連線直接遭到 MoneyDJ 伺服器拒絕，回傳 **HTTP Error 503: Service Unavailable**。
  3. **爬蟲本體執行**：依序爬取 4 檔 ETF，前三檔（`00981A.TW`、`00991A.TW`、`00403A.TW`）**皆成功抓取**，但到了最後一檔 `00992A.TW` 時，突發拋出 `HTTP Error 503: Service Unavailable` 錯誤。

* **分析與最終結論**：
  1. **特徵阻擋**：MoneyDJ 防火牆會識別預設 `Python-urllib` 的連線特徵，一旦發現無偽裝的 python 連線，便直接以 503 阻擋。
  2. **頻率阻擋 (Rate Limit)**：我們的爬蟲主程式雖然偽裝了 User-Agent（所以前三檔得以成功），但因為在迴圈抓取多檔 ETF 時**完全沒有間隔時間**（毫秒級的連續連線），導致在第四次請求時被防火牆判定為惡意頻率，進而回傳 503 阻擋。
  3. 為什麼前幾天都正常，最近兩天突然出錯？因為 MoneyDJ 近期調緊了防火牆的防禦/速率限制規則。

---

## 解決方案決策

我們評估了兩種解決方案：

1. **方案 A：Google Apps Script Proxy 轉發**
   * *優點*：透過 Google 的 IP 轉發，防火牆極難封鎖。
   * *缺點*：結構複雜、需要使用者手動部署 Web App、增加維護成本。
2. **方案 B：隨機延遲 + 隨機指數退避重試（最終採納）**
   * *優點*：最簡化設計，100% 在 Python 腳本內解決，無任何外部依賴與配置難度。
   * *實作細節*：
     * **抓取延遲**：每次抓取不同 ETF 之間，隨機 sleep 3 到 7 秒（`random.uniform(3.0, 7.0)`），完美模擬真人瀏覽。
     * **指數退避重試**：若請求不幸遇到 503 或網路抖動，自動重試最多 3 次，每次重試前的等待時間隨次數呈指數遞增（並加上隨機抖動），例如第一次等待約 10s，第二次等待約 20s：
       `backoff = retry_delay * (2 ** (attempt - 1)) + random.uniform(0.0, 3.0)`
