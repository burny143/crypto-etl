#!/usr/bin/env python3
"""Read-only CLI for the paper-trading bot.

Commands:
  validate-config   Load and validate the configuration file.
  market-data-check Verify data availability and quality for a symbol.
  show-latest       Print the latest OHLCV bar for a symbol/timeframe.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from supabase import create_client

from bot.config import BotConfig, load_config
from bot.data.supabase_adapter import SupabaseMarketData
from bot.domain.exceptions import BotError
from bot.domain.models import Symbol, Timeframe

# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> None:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        _run_command(args)
    except BotError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m bot.cli",
        description="Paper-trading bot — read-only commands.",
    )
    sub = parser.add_subparsers(dest="command")

    # validate-config
    p_conf = sub.add_parser("validate-config", help="Validate the YAML config file.")
    p_conf.add_argument(
        "--config",
        "-c",
        type=Path,
        default=None,
        help="Path to config.yaml (default: bot/config.yaml)",
    )

    # market-data-check
    p_data = sub.add_parser("market-data-check", help="Check data availability.")
    p_data.add_argument("symbol", type=str, help="Trading pair, e.g. BTC-USDT")
    p_data.add_argument(
        "--timeframe", "-tf", type=str, default="1h", help="Bar interval (default: 1h)"
    )
    p_data.add_argument("--config", "-c", type=Path, default=None, help="Path to config.yaml")

    # show-latest
    p_latest = sub.add_parser("show-latest", help="Show the latest OHLCV bar.")
    p_latest.add_argument("symbol", type=str, help="Trading pair, e.g. BTC-USDT")
    p_latest.add_argument(
        "--timeframe", "-tf", type=str, default="1h", help="Bar interval (default: 1h)"
    )
    p_latest.add_argument("--config", "-c", type=Path, default=None, help="Path to config.yaml")

    return parser


def _run_command(args: argparse.Namespace) -> None:
    if args.command == "validate-config":
        _cmd_validate_config(args)
    elif args.command == "market-data-check":
        _cmd_market_data_check(args)
    elif args.command == "show-latest":
        _cmd_show_latest(args)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_config(args: argparse.Namespace) -> BotConfig:
    return load_config(args.config)


def _build_data(args: argparse.Namespace) -> SupabaseMarketData:
    config = _load_config(args)
    client = create_client(config.supabase_url, config.supabase_service_role_key)
    return SupabaseMarketData(client, config)


# ---------------------------------------------------------------------------
# validate-config
# ---------------------------------------------------------------------------


def _cmd_validate_config(args: argparse.Namespace) -> None:
    config = _load_config(args)
    print(f"✅ Config OK — {config}")
    print(f"   Symbols:      {len(config.symbols)}")
    print(f"   Timeframes:   {[t.value for t in config.timeframes]}")
    print(f"   Lookback:     {config.lookback_bars} bars")
    print(f"   Poll every:   {config.poll_interval_seconds}s")
    print(f"   Price max age: {config.price_max_age_seconds}s")
    print(f"   Candle grace: {config.candle_grace_seconds}s")
    print(f"   Start balance: ${config.starting_balance:,.2f}")
    print(f"   Log level:    {config.logging_level}")

    # Verify env vars are reachable (not reading values, just checking set)
    url = config.supabase_url
    key_preview = config.supabase_service_role_key[:8] + "…"
    print(f"   Supabase URL: {url}")
    print(f"   Supabase key: {key_preview}")


# ---------------------------------------------------------------------------
# market-data-check
# ---------------------------------------------------------------------------


def _cmd_market_data_check(args: argparse.Namespace) -> None:
    symbol = Symbol(args.symbol.upper())
    try:
        timeframe = Timeframe(args.timeframe.lower())
    except ValueError:
        print(f"ERROR: invalid timeframe {args.timeframe!r} (use 1h, 4h, 1d)", file=sys.stderr)
        sys.exit(1)

    data = _build_data(args)

    print(f"🔍 Checking data for {symbol} [{timeframe.value}]")

    # OHLCV
    try:
        candles = data.fetch_ohlcv(symbol, timeframe, lookback=10)
        print(f"   ✅ OHLCV: {len(candles)} bars")
        if candles:
            first = candles[0]
            last = candles[-1]
            print(f"      Range: {first.datetime.date()} → {last.datetime.date()}")
            print(f"      Latest close: ${last.close:,.2f}")
    except Exception as exc:
        print(f"   ❌ OHLCV: {exc}")

    # Quote
    try:
        quote = data.fetch_quote(symbol)
        if quote is not None:
            print(f"   ✅ Quote: ${quote.price:,.2f} " f"(age: {quote.age_seconds:.0f}s)")
        else:
            print("   ⚠️  Quote: no data in crypto_data")
    except Exception as exc:
        print(f"   ❌ Quote: {exc}")


# ---------------------------------------------------------------------------
# show-latest
# ---------------------------------------------------------------------------


def _cmd_show_latest(args: argparse.Namespace) -> None:
    symbol = Symbol(args.symbol.upper())
    try:
        timeframe = Timeframe(args.timeframe.lower())
    except ValueError:
        print(f"ERROR: invalid timeframe {args.timeframe!r} (use 1h, 4h, 1d)", file=sys.stderr)
        sys.exit(1)

    data = _build_data(args)
    candles = data.fetch_ohlcv(symbol, timeframe, lookback=1)

    if not candles:
        print(f"No data for {symbol} {timeframe.value}")
        return

    c = candles[-1]
    print(f"Latest bar: {symbol} [{timeframe.value}]")
    print(f"  Time:      {c.datetime.isoformat()}")
    print(f"  O: {c.open:>10,.2f}   H: {c.high:>10,.2f}")
    print(f"  L: {c.low:>10,.2f}   C: {c.close:>10,.2f}")
    print(f"  Volume:    {c.volume:>14,.2f}")


# ---------------------------------------------------------------------------
# CLI entry
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    main()
