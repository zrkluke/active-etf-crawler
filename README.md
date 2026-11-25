# Active ETF holdings tracker

This project fetches MoneyDJ holdings pages for tracked active ETFs, writes daily
CSV snapshots, compares each ETF with its previous snapshot, and can send a
Telegram or email summary.

Tracked ETFs:

- `00981A.TW`
- `00991A.TW`
- `00992A.TW`
- `00403A.TW`

## Run locally

```powershell
python .\main.py
```

Fetch one ETF:

```powershell
python .\main.py --etf 00981A.TW
```

Outputs:

- `data/<ETF_SYMBOL>/snapshots/<ETF_SYMBOL>_YYYY-MM-DD.csv`
- `data/<ETF_SYMBOL>/comparisons/<ETF_SYMBOL>_YYYY-MM-DD_diff.csv`
- `data/<ETF_SYMBOL>/latest_summary.txt`
- `data/latest_summary.txt`

The first run only creates a snapshot. A comparison file is created once a previous
snapshot exists for that ETF.

## GitHub Actions schedule

The workflow is in `.github/workflows/daily-active-etf.yml`.

Because GitHub Actions `on: schedule` frequently experiences multi-hour delays (often 6–12 hours), the workflow uses external cron as the primary trigger and keeps a minimal overnight fallback schedule:

1. **Primary — External Cron via `workflow_dispatch` (`cron-job.org`)**:
   Triggers `POST https://api.github.com/repos/zrkluke/active-etf-crawler/actions/workflows/daily-active-etf.yml/dispatches` with `{"ref":"main"}` at `21:05, 21:35, 22:05, 22:35, 23:05, 23:35` (`Asia/Taipei`, Mon–Fri). `workflow_dispatch` runs within seconds without schedule backlog.
2. **Fallback — Minimal GitHub Actions `schedule`**:
   Runs twice overnight (`00:37` and `02:37 Asia/Taipei`, Tue–Sat morning for Mon–Fri trading days) as a safety net if external cron fails or TWSE/TPEx publish late. A `concurrency` group + `data/market_sent.txt` marker skips already-sent dates without duplicate messages.

```yaml
schedule:
  - cron: "37 16,18 * * 1-5"
```

It also supports manual runs from the GitHub Actions page with `workflow_dispatch`.

The workflow commits updated `data/` files back into the `data` branch so subsequent runs skip already-sent dates.

## Telegram notification

Create a Telegram bot with BotFather, send any message to the bot, then get your
chat id.

Add these repository secrets in GitHub:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

If both secrets are set, the workflow sends Telegram summaries per ETF.

## Email notification

Add these repository secrets in GitHub:

- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`
- `MAIL_FROM`
- `MAIL_TO`
- `SMTP_USE_TLS`

For Gmail, use:

- `SMTP_HOST`: `smtp.gmail.com`
- `SMTP_PORT`: `587`
- `SMTP_USE_TLS`: `true`
- `SMTP_PASSWORD`: a Google App Password, not your normal Google password

If all required SMTP secrets are set, the workflow sends email summaries per ETF.

## Disable the old Windows scheduled task

If you already installed the local Windows scheduled task and want GitHub Actions
to be the only scheduler, run:

```powershell
Unregister-ScheduledTask -TaskName "ActiveETF 00981A MoneyDJ Daily Holdings" -Confirm:$false
```

## 故障診斷與反爬蟲技術筆記

關於本專案的防阻擋決策與爬蟲規格技術細節，請參閱以下文件：
- [docs/2026-07-19_anti_scraping_troubleshooting.md](docs/2026-07-19_anti_scraping_troubleshooting.md) (MoneyDJ 防火牆排查記錄)
- [docs/market_data_crawler_specs.md](docs/market_data_crawler_specs.md) (每日大盤與商品數據爬蟲技術規格)

