from __future__ import annotations

import argparse
import csv
import html
import json
import os
import re
import smtplib
import sys
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ETF_ID = "00981A.TW"
DEFAULT_URL = "https://www.moneydj.com/ETF/X/Basic/Basic0007B.xdjhtm?etfid=00981A.TW"
DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "data"


@dataclass(frozen=True)
class Holding:
    name: str
    symbol: str
    weight_percent: float
    shares: int


@dataclass(frozen=True)
class RunResult:
    data_date: str
    holdings_count: int
    snapshot_path: Path
    comparison_path: Path | None
    summary_path: Path
    is_new_snapshot: bool


def fetch_html(url: str) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0 Safari/537.36"
            ),
            "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
        },
    )

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read()
            charset = response.headers.get_content_charset() or "utf-8"
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Failed to fetch MoneyDJ page: {exc}") from exc

    return raw.decode(charset, errors="replace")


def strip_tags(value: str) -> str:
    text = re.sub(r"<[^>]+>", "", value)
    return html.unescape(text).strip()


def parse_holdings(page_html: str) -> tuple[str, list[Holding]]:
    date_match = re.search(r"\u8cc7\u6599\u65e5\u671f\s*[:\uff1a]\s*(\d{4}/\d{2}/\d{2})", page_html)
    if not date_match:
        raise ValueError("Could not find data date. MoneyDJ page format may have changed.")

    data_date = datetime.strptime(date_match.group(1), "%Y/%m/%d").date().isoformat()

    row_pattern = re.compile(
        r"<tr[^>]*>\s*"
        r"<td[^>]*>\s*<a[^>]*>(?P<name>.*?)\((?P<symbol>\d{4}\.TW)\)</a>\s*</td>\s*"
        r"<td[^>]*>\s*(?P<weight>[\d.]+)\s*</td>\s*"
        r"<td[^>]*>\s*(?P<shares>[\d,]+)\s*</td>\s*"
        r"\s*</tr>",
        re.IGNORECASE | re.DOTALL,
    )

    holdings = [
        Holding(
            name=strip_tags(match.group("name")),
            symbol=match.group("symbol"),
            weight_percent=float(match.group("weight")),
            shares=int(match.group("shares").replace(",", "")),
        )
        for match in row_pattern.finditer(page_html)
    ]

    if not holdings:
        raise ValueError("Could not find holdings rows. MoneyDJ page format may have changed.")

    return data_date, holdings


def write_holdings_snapshot(output_dir: Path, data_date: str, holdings: Iterable[Holding]) -> Path:
    snapshot_dir = output_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{ETF_ID}_{data_date}.csv"

    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=["date", "symbol", "name", "weight_percent", "shares"],
        )
        writer.writeheader()
        for holding in holdings:
            writer.writerow(
                {
                    "date": data_date,
                    "symbol": holding.symbol,
                    "name": holding.name,
                    "weight_percent": holding.weight_percent,
                    "shares": holding.shares,
                }
            )

    return path


def read_snapshot(path: Path) -> dict[str, dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return {row["symbol"]: row for row in csv.DictReader(file)}


def find_previous_snapshot(output_dir: Path, data_date: str) -> Path | None:
    snapshot_dir = output_dir / "snapshots"
    if not snapshot_dir.exists():
        return None

    candidates = sorted(snapshot_dir.glob(f"{ETF_ID}_*.csv"))
    previous = [path for path in candidates if path.stem < f"{ETF_ID}_{data_date}"]
    return previous[-1] if previous else None


def write_comparison(output_dir: Path, data_date: str, current_path: Path, previous_path: Path) -> Path:
    comparison_dir = output_dir / "comparisons"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    output_path = comparison_dir / f"{ETF_ID}_{data_date}_diff.csv"

    previous = read_snapshot(previous_path)
    current = read_snapshot(current_path)
    symbols = sorted(set(previous) | set(current))

    with output_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.DictWriter(
            file,
            fieldnames=[
                "date",
                "symbol",
                "name",
                "previous_shares",
                "current_shares",
                "change_shares",
                "previous_weight_percent",
                "current_weight_percent",
                "status",
            ],
        )
        writer.writeheader()

        for symbol in symbols:
            old = previous.get(symbol)
            new = current.get(symbol)
            previous_shares = int(old["shares"]) if old else 0
            current_shares = int(new["shares"]) if new else 0

            if old and new:
                if current_shares > previous_shares:
                    status = "increased"
                elif current_shares < previous_shares:
                    status = "decreased"
                else:
                    status = "unchanged"
            elif new:
                status = "added"
            else:
                status = "removed"

            writer.writerow(
                {
                    "date": data_date,
                    "symbol": symbol,
                    "name": (new or old or {}).get("name", ""),
                    "previous_shares": previous_shares,
                    "current_shares": current_shares,
                    "change_shares": current_shares - previous_shares,
                    "previous_weight_percent": old["weight_percent"] if old else "",
                    "current_weight_percent": new["weight_percent"] if new else "",
                    "status": status,
                }
            )

    return output_path


def read_comparison_rows(path: Path) -> list[dict[str, str]]:
    with path.open("r", newline="", encoding="utf-8-sig") as file:
        return list(csv.DictReader(file))


def format_signed(value: int) -> str:
    return f"+{value:,}" if value > 0 else f"{value:,}"


def format_row(row: dict[str, str]) -> str:
    change = int(row["change_shares"])
    return (
        f"- {row['symbol']} {row['name']}: {format_signed(change)} "
        f"({int(row['previous_shares']):,} -> {int(row['current_shares']):,})"
    )


def build_summary(result: RunResult) -> str:
    lines = [
        f"00981A holdings update: {result.data_date}",
        f"Holdings count: {result.holdings_count}",
        f"Snapshot: {result.snapshot_path}",
    ]

    if not result.comparison_path:
        lines.append("Comparison: skipped because no previous snapshot exists.")
        return "\n".join(lines)

    rows = read_comparison_rows(result.comparison_path)
    changed = [row for row in rows if row["status"] != "unchanged"]
    increased = [row for row in changed if int(row["change_shares"]) > 0]
    decreased = [row for row in changed if int(row["change_shares"]) < 0]
    added = [row for row in changed if row["status"] == "added"]
    removed = [row for row in changed if row["status"] == "removed"]

    lines.extend(
        [
            f"Comparison: {result.comparison_path}",
            (
                "Changes: "
                f"{len(increased)} increased, "
                f"{len(decreased)} decreased, "
                f"{len(added)} added, "
                f"{len(removed)} removed"
            ),
        ]
    )

    top_increases = sorted(increased, key=lambda row: int(row["change_shares"]), reverse=True)[:10]
    top_decreases = sorted(decreased, key=lambda row: int(row["change_shares"]))[:10]

    if top_increases:
        lines.append("")
        lines.append("Top increases:")
        lines.extend(format_row(row) for row in top_increases)

    if top_decreases:
        lines.append("")
        lines.append("Top decreases:")
        lines.extend(format_row(row) for row in top_decreases)

    if not changed:
        lines.append("No share-count changes versus the previous snapshot.")

    return "\n".join(lines)


def write_summary(output_dir: Path, summary: str) -> Path:
    path = output_dir / "latest_summary.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(summary + "\n", encoding="utf-8")
    return path


def send_telegram(summary: str) -> bool:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({"chat_id": chat_id, "text": summary[:3900]}).encode("utf-8")
    request = Request(url, data=payload, headers={"Content-Type": "application/json"}, method="POST")

    with urlopen(request, timeout=30) as response:
        response.read()
    return True


def send_email(summary: str) -> bool:
    host = os.getenv("SMTP_HOST")
    username = os.getenv("SMTP_USERNAME")
    password = os.getenv("SMTP_PASSWORD")
    mail_from = os.getenv("MAIL_FROM") or username
    mail_to = os.getenv("MAIL_TO")
    port = int(os.getenv("SMTP_PORT", "587"))
    use_tls = os.getenv("SMTP_USE_TLS", "true").lower() != "false"

    if not host or not username or not password or not mail_from or not mail_to:
        return False

    message = EmailMessage()
    message["Subject"] = "00981A daily holdings update"
    message["From"] = mail_from
    message["To"] = mail_to
    message.set_content(summary)

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)

    return True


def notify(summary: str) -> list[str]:
    sent: list[str] = []
    if send_telegram(summary):
        sent.append("telegram")
    if send_email(summary):
        sent.append("email")
    return sent


def run(url: str, output_dir: Path) -> RunResult:
    page_html = fetch_html(url)
    data_date, holdings = parse_holdings(page_html)

    previous_path = find_previous_snapshot(output_dir, data_date)
    expected_snapshot_path = output_dir / "snapshots" / f"{ETF_ID}_{data_date}.csv"
    is_new_snapshot = not expected_snapshot_path.exists()
    current_path = write_holdings_snapshot(output_dir, data_date, holdings)
    comparison_path = (
        write_comparison(output_dir, data_date, current_path, previous_path)
        if previous_path
        else None
    )
    result = RunResult(
        data_date=data_date,
        holdings_count=len(holdings),
        snapshot_path=current_path,
        comparison_path=comparison_path,
        summary_path=output_dir / "latest_summary.txt",
        is_new_snapshot=is_new_snapshot,
    )
    summary_path = write_summary(output_dir, build_summary(result))

    return RunResult(
        data_date=result.data_date,
        holdings_count=result.holdings_count,
        snapshot_path=result.snapshot_path,
        comparison_path=result.comparison_path,
        summary_path=summary_path,
        is_new_snapshot=result.is_new_snapshot,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch 00981A MoneyDJ holdings and compare snapshots.")
    parser.add_argument("--url", default=DEFAULT_URL, help="MoneyDJ ETF holdings URL.")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory.")
    parser.add_argument("--notify", action="store_true", help="Send Telegram/email notification when secrets are configured.")
    args = parser.parse_args()

    try:
        result = run(args.url, args.output_dir)
        summary = result.summary_path.read_text(encoding="utf-8")
        print(summary)
        if args.notify:
            if result.is_new_snapshot:
                sent = notify(summary)
                print(f"notifications: {', '.join(sent) if sent else 'skipped, no notification secrets configured'}")
            else:
                print("notifications: skipped, snapshot already exists for this data date")
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
