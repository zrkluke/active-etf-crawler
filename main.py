from __future__ import annotations

import argparse
import sys
from pathlib import Path

from scripts.moneydj_etf_holdings import (
    DEFAULT_ETFS,
    resolve_etfs,
    run_all,
    build_combined_summary,
    write_summary,
    notify_results,
    send_telegram,
    DEFAULT_OUTPUT_DIR
)
from scripts.market_commodities import fetch_market_and_commodities_summary
from scripts.retail_ratio import fetch_latest_retail_ratio
from scripts.margin_balance import fetch_margin_balance_summary

def main() -> int:
    # Ensure stdout handles UTF-8 correctly for print statements on Windows console
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch ETF holdings and general market commodities indicators.")
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

    # 1. Run Active ETF Crawler
    try:
        etfs = resolve_etfs(args.etfs)
        results, failures = run_all(etfs, args.output_dir)
        summary = build_combined_summary(results, failures)
        summary_path = write_summary(args.output_dir / "latest_summary.txt", summary)
        print("=== Active ETF holdings summary ===")
        print(summary_path.read_text(encoding="utf-8"))

        if args.notify:
            if any(result.is_new_snapshot for result in results) or failures:
                sent = notify_results(results, failures)
                print(f"ETF notifications: {'; '.join(sent) if sent else 'skipped, no notification secrets configured'}")
            else:
                print("ETF notifications: skipped, snapshots already exist for these data dates")
        etf_failed = bool(failures and not results)
    except Exception as exc:
        print(f"ERROR running ETF crawler: {exc}", file=sys.stderr)
        etf_failed = True

    # 2. Run Market, Commodities, and Margin Balance Crawler
    print("\n=== Market and Commodities summary ===")
    try:
        is_trading_day = True
        rr_summary = ""
        mb_summary = ""
        header = ""
        
        # Determine if today is a trading day by checking the retail ratio
        try:
            date_str, ratio = fetch_latest_retail_ratio()
            # 📊 【今日大盤與商品數據】({date_str})
            header = f"\U0001F4CA \u3010\u4eca\u65e5\u5927\u76e4\u8207\u5546\u54c1\u6578\u64da\u3011({date_str})"
            # 👥 微台指散戶多空比: {ratio:+.2f}%
            rr_summary = f"\U0001F465 \u5fae\u53f0\u6307\u6563\u6236\u591a\u7a7a\u6bd4: {ratio:+.2f}%"
        except ValueError as ve:
            if "No trading data" in str(ve):
                # It is a non-trading day (weekend or holiday). Skip sending notification completely.
                print(f"Today is a non-trading day ({ve}). Skipping market/commodity Telegram notification.")
                is_trading_day = False
            else:
                # Other value errors are treated as errors
                rr_summary = f"\U0001F465 \u5fae\u53f0\u6307\u6563\u6236\u591a\u7a7a\u6bd4: \u6293\u53d6\u5931\u6557 ({ve})"
        except Exception as e:
            # Network or parsing errors: we still proceed but note the failure
            rr_summary = f"\U0001F465 \u5fae\u53f0\u6307\u6563\u6236\u591a\u7a7a\u6bd4: \u6293\u53d6\u5931\u6557 ({e})"

        if is_trading_day:
            mc_summary = fetch_market_and_commodities_summary()
            mb_summary = fetch_margin_balance_summary()
            
            # Combine all pieces
            parts = [header, mc_summary, rr_summary, mb_summary]
            # Filter out empty strings just in case
            combined_summary = "\n".join([p for p in parts if p])
            
            print(combined_summary)
            
            if args.notify:
                sent_tg = send_telegram(combined_summary)
                if sent_tg:
                    print("Market, commodities, and margin balance Telegram notification sent successfully.")
                else:
                    print("Market, commodities, and margin balance Telegram notification skipped (Telegram secrets not configured).")
        
        mc_failed = False
    except Exception as exc:
        print(f"ERROR running Market/Commodity crawler: {exc}", file=sys.stderr)
        mc_failed = True

    if etf_failed or mc_failed:
        return 1
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
