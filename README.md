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

It runs every day at `18:37`, `19:13`, `20:47`, `21:23`, and `22:11 Asia/Taipei`. GitHub Actions
scheduled jobs can be delayed or occasionally dropped, so the later entries are
fallback windows. The script only sends a notification when at least one tracked
ETF creates a new MoneyDJ data-date snapshot, so fallback runs do not send
duplicate messages.

Notifications are sent per ETF. If multiple ETFs have new snapshots, Telegram and
email receive one message per ETF instead of one combined message.

ETF fetch errors are isolated. If one ETF fails, the script still writes snapshots
and summaries for the other ETFs, records the failed ETF in `data/latest_summary.txt`,
and sends a separate failure notification when notification secrets are configured.

```yaml
schedule:
  - cron: "37 10 * * *"
  - cron: "13 11 * * *"
  - cron: "47 12 * * *"
  - cron: "23 13 * * *"
  - cron: "11 14 * * *"
```

It also supports manual runs from the GitHub Actions page with `workflow_dispatch`.

The workflow commits updated `data/` files back into the repository, so the next
scheduled run can compare each ETF against its previous snapshot.

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

