from __future__ import annotations

import argparse
import csv
import html
import json
import os
import random
import re
import smtplib
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from typing import Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


DEFAULT_OUTPUT_DIR = Path(__file__).resolve().parent / "data"
MONEYDJ_HOLDINGS_URL = "https://www.moneydj.com/ETF/X/Basic/Basic0007B.xdjhtm?etfid={symbol}"


@dataclass(frozen=True)
class EtfConfig:
    symbol: str
    url: str


@dataclass(frozen=True)
class Holding:
    name: str
    symbol: str
    weight_percent: float
    shares: int


@dataclass(frozen=True)
class RunResult:
    etf_symbol: str
    data_date: str
    holdings_count: int
    snapshot_path: Path
    comparison_path: Path | None
    summary_path: Path
    is_new_snapshot: bool


@dataclass(frozen=True)
class RunFailure:
    etf_symbol: str
    error: str
    summary_path: Path


DEFAULT_ETFS = tuple(
    EtfConfig(symbol, MONEYDJ_HOLDINGS_URL.format(symbol=symbol))
    for symbol in ("00981A.TW", "00991A.TW", "00992A.TW", "00403A.TW")
)


def fetch_html(url: str, max_retries: int = 3, retry_delay: float = 10.0) -> str:
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

    last_exc = None
    for attempt in range(1, max_retries + 1):
        try:
            with urlopen(request, timeout=30) as response:
                raw = response.read()
                charset = response.headers.get_content_charset() or "utf-8"
            return raw.decode(charset, errors="replace")
        except (HTTPError, URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt < max_retries:
                backoff = retry_delay * (2 ** (attempt - 1)) + random.uniform(0.0, 3.0)
                print(f"WARNING: Fetch failed (attempt {attempt}/{max_retries}): {exc}. Retrying in {backoff:.2f}s...")
                time.sleep(backoff)

    raise RuntimeError(f"Failed to fetch MoneyDJ page after {max_retries} attempts: {last_exc}") from last_exc


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


def get_etf_output_dir(output_dir: Path, etf_symbol: str) -> Path:
    return output_dir / etf_symbol


def write_holdings_snapshot(
    output_dir: Path,
    etf_symbol: str,
    data_date: str,
    holdings: Iterable[Holding],
) -> Path:
    snapshot_dir = get_etf_output_dir(output_dir, etf_symbol) / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{etf_symbol}_{data_date}.csv"

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


def find_previous_snapshot(output_dir: Path, etf_symbol: str, data_date: str) -> Path | None:
    snapshot_dir = get_etf_output_dir(output_dir, etf_symbol) / "snapshots"
    if not snapshot_dir.exists():
        return None

    candidates = sorted(snapshot_dir.glob(f"{etf_symbol}_*.csv"))
    previous = [path for path in candidates if path.stem < f"{etf_symbol}_{data_date}"]
    return previous[-1] if previous else None


def write_comparison(
    output_dir: Path,
    etf_symbol: str,
    data_date: str,
    current_path: Path,
    previous_path: Path,
) -> Path:
    comparison_dir = get_etf_output_dir(output_dir, etf_symbol) / "comparisons"
    comparison_dir.mkdir(parents=True, exist_ok=True)
    output_path = comparison_dir / f"{etf_symbol}_{data_date}_diff.csv"

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
        f"{result.etf_symbol} holdings update: {result.data_date}",
        f"Holdings count: {result.holdings_count}",
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

    lines.append(
        "Changes: "
        f"{len(increased)} increased, "
        f"{len(decreased)} decreased, "
        f"{len(added)} added, "
        f"{len(removed)} removed"
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


def build_failure_summary(failure: RunFailure) -> str:
    return "\n".join(
        [
            f"{failure.etf_symbol} holdings update failed",
            f"Error: {failure.error}",
        ]
    )


def build_combined_summary(results: list[RunResult], failures: list[RunFailure]) -> str:
    if len(results) == 1 and not failures:
        return build_summary(results[0])
    if len(failures) == 1 and not results:
        return build_failure_summary(failures[0])

    lines = ["Active ETF holdings update"]
    for result in results:
        lines.append("")
        lines.append(build_summary(result))
    for failure in failures:
        lines.append("")
        lines.append(build_failure_summary(failure))
    return "\n".join(lines)


def write_summary(path: Path, summary: str) -> Path:
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


def send_email(subject: str, summary: str) -> bool:
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
    message["Subject"] = subject
    message["From"] = mail_from
    message["To"] = mail_to
    message.set_content(summary)

    with smtplib.SMTP(host, port, timeout=30) as smtp:
        if use_tls:
            smtp.starttls()
        smtp.login(username, password)
        smtp.send_message(message)

    return True


def notify(subject: str, summary: str) -> list[str]:
    sent: list[str] = []
    if send_telegram(summary):
        sent.append("telegram")
    if send_email(subject, summary):
        sent.append("email")
    return sent


def resolve_etfs(selected_symbols: list[str] | None) -> list[EtfConfig]:
    if not selected_symbols:
        return list(DEFAULT_ETFS)

    by_symbol = {etf.symbol: etf for etf in DEFAULT_ETFS}
    unknown = sorted(set(selected_symbols) - set(by_symbol))
    if unknown:
        raise ValueError(f"Unknown ETF symbol(s): {', '.join(unknown)}")

    return [by_symbol[symbol] for symbol in selected_symbols]


def run_etf(etf: EtfConfig, output_dir: Path) -> RunResult:
    page_html = fetch_html(etf.url)
    data_date, holdings = parse_holdings(page_html)

    previous_path = find_previous_snapshot(output_dir, etf.symbol, data_date)
    expected_snapshot_path = (
        get_etf_output_dir(output_dir, etf.symbol) / "snapshots" / f"{etf.symbol}_{data_date}.csv"
    )
    is_new_snapshot = not expected_snapshot_path.exists()
    current_path = write_holdings_snapshot(output_dir, etf.symbol, data_date, holdings)
    comparison_path = (
        write_comparison(output_dir, etf.symbol, data_date, current_path, previous_path)
        if previous_path
        else None
    )
    summary_path = get_etf_output_dir(output_dir, etf.symbol) / "latest_summary.txt"

    result = RunResult(
        etf_symbol=etf.symbol,
        data_date=data_date,
        holdings_count=len(holdings),
        snapshot_path=current_path,
        comparison_path=comparison_path,
        summary_path=summary_path,
        is_new_snapshot=is_new_snapshot,
    )
    write_summary(summary_path, build_summary(result))
    return result


def run_all(etfs: list[EtfConfig], output_dir: Path) -> tuple[list[RunResult], list[RunFailure]]:
    results: list[RunResult] = []
    failures: list[RunFailure] = []

    for i, etf in enumerate(etfs):
        if i > 0:
            delay = random.uniform(3.0, 7.0)
            print(f"Waiting {delay:.2f} seconds before fetching {etf.symbol}...")
            time.sleep(delay)

        try:
            results.append(run_etf(etf, output_dir))
        except Exception as exc:
            failure = RunFailure(
                etf_symbol=etf.symbol,
                error=str(exc),
                summary_path=get_etf_output_dir(output_dir, etf.symbol) / "latest_summary.txt",
            )
            write_summary(failure.summary_path, build_failure_summary(failure))
            failures.append(failure)

    return results, failures


def notify_results(results: list[RunResult], failures: list[RunFailure]) -> list[str]:
    notifications: list[str] = []

    for result in results:
        if not result.is_new_snapshot:
            continue
        summary = result.summary_path.read_text(encoding="utf-8")
        sent = notify(f"{result.etf_symbol} daily holdings update", summary)
        notifications.append(f"{result.etf_symbol}: {', '.join(sent) if sent else 'skipped'}")

    for failure in failures:
        summary = failure.summary_path.read_text(encoding="utf-8")
        sent = notify(f"{failure.etf_symbol} holdings update failed", summary)
        notifications.append(f"{failure.etf_symbol}: {', '.join(sent) if sent else 'skipped'}")

    return notifications


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch MoneyDJ ETF holdings and compare snapshots.")
    parser.add_argument(
        "--etf",
        action="append",
        dest="etfs",
        choices=[etf.symbol for etf in DEFAULT_ETFS],
        help="ETF symbol to fetch. Repeat to fetch multiple ETFs. Defaults to all tracked ETFs.",
    )
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR, help="Output directory.")
    parser.add_argument("--notify", action="store_true", help="Send Telegram/email notification when secrets are configured.")
    args = parser.parse_args()

    try:
        etfs = resolve_etfs(args.etfs)
        results, failures = run_all(etfs, args.output_dir)
        summary = build_combined_summary(results, failures)
        summary_path = write_summary(args.output_dir / "latest_summary.txt", summary)
        print(summary_path.read_text(encoding="utf-8"))

        if args.notify:
            if any(result.is_new_snapshot for result in results) or failures:
                sent = notify_results(results, failures)
                print(f"notifications: {'; '.join(sent) if sent else 'skipped, no notification secrets configured'}")
            else:
                print("notifications: skipped, snapshots already exist for these data dates")
        if failures and not results:
            return 1
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
