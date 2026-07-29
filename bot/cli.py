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
from typing import TYPE_CHECKING

from supabase import create_client

from bot.config import BotConfig, load_config
from bot.data.supabase_adapter import SupabaseMarketData
from bot.domain.exceptions import BotError
from bot.domain.models import Symbol, Timeframe

if TYPE_CHECKING:
    from bot.engine import BotEngine

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
        print("\nShutdown by user.")
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

    # run (continuous)
    p_run = sub.add_parser("run", help="Run the bot in continuous mode.")
    p_run.add_argument("--config", "-c", type=Path, default=None, help="Path to config.yaml")
    p_run.add_argument(
        "--in-memory",
        action="store_true",
        help="Use in-memory storage instead of Supabase",
    )

    # run-once (single iteration)
    p_once = sub.add_parser("run-once", help="Run a single evaluation cycle and exit.")
    p_once.add_argument("--config", "-c", type=Path, default=None, help="Path to config.yaml")
    p_once.add_argument(
        "--in-memory",
        action="store_true",
        help="Use in-memory storage instead of Supabase",
    )

    return parser


def _run_command(args: argparse.Namespace) -> None:
    if args.command == "validate-config":
        _cmd_validate_config(args)
    elif args.command == "market-data-check":
        _cmd_market_data_check(args)
    elif args.command == "show-latest":
        _cmd_show_latest(args)
    elif args.command in ("run", "run-once"):
        _cmd_run(args)


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
            print(f"   ✅ Quote: ${quote.price:,.2f} (age: {quote.age_seconds:.0f}s)")
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

# ---------------------------------------------------------------------------
# Bot factory
# ---------------------------------------------------------------------------


def build_bot(config: BotConfig, use_supabase: bool = True) -> BotEngine:
    """Wire all dependencies and return a ready-to-run ``BotEngine``.

    Args:
        config: Validated bot configuration.
        use_supabase: When ``True`` (default) uses Supabase-backed repositories
            and market data.  When ``False`` uses in-memory storage.

    Returns:
        A fully-wired ``BotEngine`` instance.
    """
    from decimal import Decimal

    from bot.data.supabase_adapter import SupabaseMarketData
    from bot.engine import BotEngine
    from bot.execution.executor import PaperExecutor
    from bot.portfolio.service import PortfolioService
    from bot.risk.manager import RiskManager
    from bot.strategies.registry import StrategyRegistry

    registry = StrategyRegistry()
    registry.register_defaults()

    portfolio = PortfolioService(Decimal(str(config.starting_balance)))
    risk = RiskManager(config)
    executor = PaperExecutor()

    if use_supabase:
        from bot.repositories.signal import SupabaseSignalRepository
        from bot.repositories.supabase_repos import (
            SupabaseEquityCurveRepository,
            SupabaseOrderRepository,
            SupabasePositionRepository,
        )

        client = create_client(config.supabase_url, config.supabase_service_role_key)
        data = SupabaseMarketData(client, config)
        order_repo = SupabaseOrderRepository(client)
        position_repo = SupabasePositionRepository(client)
        signal_repo = SupabaseSignalRepository(client)
        equity_curve_repo = SupabaseEquityCurveRepository(client)
    else:
        from bot.repositories.memory import (
            InMemoryOrderRepository,
            InMemoryPositionRepository,
        )

        # In-memory mode: use an in-memory data provider.
        # Does NOT require Supabase credentials — fully offline-safe.
        from bot.data.memory import InMemoryMarketData

        data = InMemoryMarketData()
        order_repo = InMemoryOrderRepository()
        position_repo = InMemoryPositionRepository()
        signal_repo = None  # engine defaults to in-memory
        equity_curve_repo = None

    engine = BotEngine(
        config=config,
        data_provider=data,
        registry=registry,
        portfolio=portfolio,
        risk_manager=risk,
        executor=executor,
        order_repo=order_repo,
        position_repo=position_repo,
        equity_curve_repo=equity_curve_repo,
        signal_repo=signal_repo,
    )

    # Hydrate state from Supabase on startup
    if use_supabase:
        engine.load_state_on_startup()

    return engine


# ---------------------------------------------------------------------------
# run / run-once
# ---------------------------------------------------------------------------


def _cmd_run(args: argparse.Namespace) -> None:
    """Execute the bot in single-cycle or continuous mode."""
    import logging

    config = _load_config(args)
    logging.basicConfig(
        level=getattr(logging, config.logging_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    engine = build_bot(config, use_supabase=not args.in_memory)

    if args.command == "run-once":
        result = engine.run_once()
        print(
            f"Cycle complete — "
            f"{result.symbols_evaluated} symbols, "
            f"{result.signals_generated} signals, "
            f"{result.orders_created} orders, "
            f"{result.orders_rejected} rejected, "
            f"{len(result.errors)} errors"
        )
        if result.errors:
            for err in result.errors:
                print(f"  ⚠ {err}", file=sys.stderr)
    else:
        engine.run_forever()


if __name__ == "__main__":
    main()
