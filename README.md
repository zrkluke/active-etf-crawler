# ActiveETF 00981A holdings tracker

This project fetches the MoneyDJ 00981A holdings page, writes a daily CSV snapshot,
compares it with the previous snapshot, and can send a Telegram or email summary.

## Run locally

```powershell
python .\moneydj_00981a_holdings.py
```

Outputs:

- `data/snapshots/00981A.TW_YYYY-MM-DD.csv`
- `data/comparisons/00981A.TW_YYYY-MM-DD_diff.csv`
- `data/latest_summary.txt`

The first run only creates a snapshot. A comparison file is created once a previous
snapshot exists.

## GitHub Actions schedule

The workflow is in `.github/workflows/daily-00981a.yml`.

It runs every day at `18:37`, `19:13`, `20:47`, `21:23`, and `22:11 Asia/Taipei`. GitHub Actions
scheduled jobs can be delayed or occasionally dropped, so the later entries are
fallback windows. The script only sends a notification when the MoneyDJ data date
creates a new snapshot, so fallback runs do not send duplicate messages.

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
scheduled run can compare against the previous snapshot.

## Telegram notification

Create a Telegram bot with BotFather, send any message to the bot, then get your
chat id.

Add these repository secrets in GitHub:

- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

If both secrets are set, the workflow sends a Telegram summary.

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

If all required SMTP secrets are set, the workflow sends an email summary.

## Disable the old Windows scheduled task

If you already installed the local Windows scheduled task and want GitHub Actions
to be the only scheduler, run:

```powershell
Unregister-ScheduledTask -TaskName "ActiveETF 00981A MoneyDJ Daily Holdings" -Confirm:$false
```
