"""Bar-by-bar backtesting engine.

Walks through historical OHLCV data, evaluates strategies at each bar,
simulates fills, and produces a structured ``BacktestResult`` with trades,
equity curve, and performance metrics.

Reuses the same ``RiskManager``, ``PaperExecutor``, and ``PortfolioService``
components as the forward ``BotEngine`` — so strategies are tested with
exactly the same code path that runs live.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from dataclasses import dataclass, field, asdict
from datetime import datetime
from decimal import ROUND_DOWN, Decimal
from enum import Enum
from typing import Any

from bot.backtesting.metrics import BacktestMetrics, compute_metrics
from bot.config import BotConfig
from bot.domain.models import (
    Candle,
    MarketQuote,
    OrderIntent,
    OrderStatus,
    PaperOrder,
    PaperPosition,
    PortfolioSnapshot,
    Side,
    Signal,
    SignalAction,
    Symbol,
    Timeframe,
)
from bot.domain.utc import utc_now
from bot.execution.executor import PaperExecutor
from bot.portfolio.service import PortfolioService
from bot.risk.manager import RiskManager
from bot.strategies.base import AbstractStrategy

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass
class BacktestTrade:
    """A complete round-trip trade (entry + exit)."""

    symbol: Symbol
    side: Side
    entry_time: datetime
    exit_time: datetime | None = None
    entry_price: Decimal = Decimal("0")
    exit_price: Decimal | None = None
    quantity: Decimal = Decimal("0")
    pnl: Decimal | None = None
    pnl_pct: float | None = None
    exit_reason: str = ""  # "signal", "close_at_end"
    entry_bar_index: int = 0
    exit_bar_index: int | None = None


@dataclass
class BacktestResult:
    """Complete output of a backtest run."""

    symbol: Symbol
    timeframe: Timeframe
    strategy_id: str
    strategy_params: dict[str, Any]
    starting_capital: Decimal
    final_equity: Decimal
    cash_remaining: Decimal
    total_return_pct: float
    trades: list[BacktestTrade]
    equity_curve: list[PortfolioSnapshot]
    metrics: BacktestMetrics
    bar_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (for CLI output)."""
        class _Encoder(json.JSONEncoder):
            def default(self, obj: Any) -> Any:
                if isinstance(obj, Decimal):
                    return float(obj)
                if isinstance(obj, datetime):
                    return obj.isoformat()
                if isinstance(obj, Enum):
                    return obj.value
                return super().default(obj)

        return json.loads(json.dumps(asdict(self), cls=_Encoder))


# ---------------------------------------------------------------------------
# BacktestEngine
# ---------------------------------------------------------------------------


class BacktestEngine:
    """Bar-by-bar backtesting engine.

    Usage::

        engine = BacktestEngine(strategy, risk_manager, executor, portfolio)
        result = engine.run(candles, symbol, timeframe)

    The engine walks through ``candles`` in chronological order, evaluating
    the strategy on each bar and simulating fills through the standard bot
    pipeline (risk → executor → portfolio).
    """

    # Default fraction of available cash per entry
    DEFAULT_TRADE_FRACTION = Decimal("0.1")

    def __init__(
        self,
        strategy: AbstractStrategy,
        risk_manager: RiskManager,
        executor: PaperExecutor,
        portfolio: PortfolioService,
        trade_fraction: Decimal | None = None,
    ) -> None:
        self._strategy = strategy
        self._risk = risk_manager
        self._executor = executor
        self._portfolio = portfolio
        self._trade_fraction = trade_fraction or self.DEFAULT_TRADE_FRACTION

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run(
        self,
        candles: Sequence[Candle],
        symbol: Symbol,
        timeframe: Timeframe,
    ) -> BacktestResult:
        """Run a full backtest.

        Args:
            candles: Complete OHLCV history in chronological order.
            symbol: The trading pair being backtested.
            timeframe: Bar interval.

        Returns:
            A ``BacktestResult`` with trades, equity curve, and metrics.
        """
        if len(candles) < self._strategy.min_history:
            logger.warning(
                "Not enough data: %d bars, need at least %d",
                len(candles),
                self._strategy.min_history,
            )
            return self._empty_result(symbol, timeframe)

        trades: list[BacktestTrade] = []
        equity_curve: list[PortfolioSnapshot] = []
        seen_keys: set[str] = set()
        open_trades: dict[tuple[Symbol, Side], BacktestTrade] = {}

        # Record initial state before any trading
        first_candle = candles[0]
        equity_curve.append(PortfolioSnapshot(
            timestamp=first_candle.datetime,
            cash=self._portfolio.cash,
            equity=self._portfolio.total_equity({symbol: first_candle.close}),
        ))

        for i in range(self._strategy.min_history - 1, len(candles)):
            window = candles[: i + 1]
            candle = candles[i]

            # Evaluate strategy on available history
            try:
                signal = self._strategy.evaluate(window)
            except Exception as exc:
                logger.debug("Strategy error at bar %d: %s", i, exc)
                signal = None

            # Process non-HOLD signals
            if signal is not None and signal.action != SignalAction.HOLD:
                self._process_signal(
                    signal=signal,
                    candle=candle,
                    i=i,
                    seen_keys=seen_keys,
                    trades=trades,
                    open_trades=open_trades,
                )

            # Record equity snapshot at this bar
            snapshot = PortfolioSnapshot(
                timestamp=candle.datetime,
                cash=self._portfolio.cash,
                equity=self._portfolio.total_equity({symbol: candle.close}),
            )
            equity_curve.append(snapshot)

        # Close any trades still open at the end of data
        for key in list(open_trades.keys()):
            trade = open_trades.pop(key)
            close_price = candles[-1].close
            pos = self._portfolio.get_position(*key)
            if pos is not None:
                close_order = self._portfolio.close_position(key[0], key[1], close_price)
                self._close_trade(trade, candles[-1], len(candles) - 1, close_order, "close_at_end")
                trades.append(trade)

        # Build final equity
        final_equity = (
            equity_curve[-1].equity if equity_curve else self._portfolio.cash
        )

        # Compute metrics
        trade_pnls = [Decimal(str(t.pnl)) for t in trades if t.pnl is not None]
        trade_holding_bars = [
            (t.exit_bar_index - t.entry_bar_index)
            for t in trades
            if t.exit_bar_index is not None
        ]
        avg_holding = (
            sum(trade_holding_bars) / len(trade_holding_bars)
            if trade_holding_bars
            else 0.0
        )
        equity_values = [s.equity for s in equity_curve]

        starting_capital = equity_curve[0].equity if equity_curve else self._portfolio.cash

        metrics = compute_metrics(
            trade_pnls=trade_pnls,
            equity_values=equity_values,
            total_trades=len(trades),
            avg_holding_bars=avg_holding,
            starting_capital=starting_capital,
        )

        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            strategy_id=self._strategy.id,
            strategy_params=dict(self._strategy.params),
            starting_capital=starting_capital,
            final_equity=final_equity,
            cash_remaining=self._portfolio.cash,
            total_return_pct=metrics.total_return_pct,
            trades=trades,
            equity_curve=equity_curve,
            metrics=metrics,
            bar_count=len(candles),
        )

    # ------------------------------------------------------------------
    # Signal processing
    # ------------------------------------------------------------------

    def _process_signal(
        self,
        signal: Signal,
        candle: Candle,
        i: int,
        seen_keys: set[str],
        trades: list[BacktestTrade],
        open_trades: dict[tuple[Symbol, Side], BacktestTrade],
    ) -> None:
        """Route entry/exit signals through the trading pipeline."""
        quote = MarketQuote(
            symbol=candle.symbol,
            price=candle.close,
            updated_at=candle.datetime,
            is_live=False,
        )

        if signal.action in (SignalAction.ENTER_LONG, SignalAction.ENTER_SHORT):
            self._process_entry(signal, quote, candle, i, seen_keys, trades, open_trades)
        elif signal.action in (SignalAction.EXIT_LONG, SignalAction.EXIT_SHORT):
            self._process_exit(signal, quote, candle, i, seen_keys, trades, open_trades)

    def _process_entry(
        self,
        signal: Signal,
        quote: MarketQuote,
        candle: Candle,
        i: int,
        seen_keys: set[str],
        trades: list[BacktestTrade],
        open_trades: dict[tuple[Symbol, Side], BacktestTrade],
    ) -> None:
        """Process an entry signal — risk check, fill, record trade."""
        side = Side.LONG if signal.action == SignalAction.ENTER_LONG else Side.SHORT

        # Check if we already have an open position for this symbol/side
        existing_pos = self._portfolio.get_position(signal.symbol, side)

        quantity = self._compute_quantity(side, quote.price)
        if quantity <= 0:
            return

        intent = OrderIntent(
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            signal=signal,
        )

        decision = self._risk.check_order(
            intent, self._portfolio, quote, existing_keys=seen_keys
        )
        if not decision.approved:
            logger.debug("Risk rejected entry at bar %d: %s", i, decision.reason)
            return

        order = self._executor.fill_order(intent, quote)
        self._portfolio.apply_fill(order)
        if order.decision_key:
            seen_keys.add(order.decision_key)

        # Track new trade if this opened a new position (not averaging in)
        key = (signal.symbol, side)
        if key not in open_trades and existing_pos is None:
            trade = BacktestTrade(
                symbol=signal.symbol,
                side=side,
                entry_time=candle.datetime,
                entry_price=order.price,
                quantity=order.quantity,
                entry_bar_index=i,
            )
            open_trades[key] = trade

    def _process_exit(
        self,
        signal: Signal,
        quote: MarketQuote,
        candle: Candle,
        i: int,
        seen_keys: set[str],
        trades: list[BacktestTrade],
        open_trades: dict[tuple[Symbol, Side], BacktestTrade],
    ) -> None:
        """Process an exit signal — close position, record trade completion."""
        exit_side = Side.LONG if signal.action == SignalAction.EXIT_LONG else Side.SHORT

        position = self._portfolio.get_position(signal.symbol, exit_side)
        if position is None:
            return

        close_order = self._portfolio.close_position(
            signal.symbol, exit_side, quote.price
        )
        close_order.decision_key = signal.decision_key
        if close_order.decision_key:
            seen_keys.add(close_order.decision_key)

        # Record trade completion
        key = (signal.symbol, exit_side)
        trade = open_trades.pop(key, None)
        if trade is not None:
            self._close_trade(trade, candle, i, close_order, "signal")
            trades.append(trade)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_quantity(self, side: Side, price: Decimal) -> Decimal:
        """Compute trade quantity based on available equity."""
        if side == Side.LONG:
            available = self._portfolio.cash
        else:
            available = self._portfolio.total_equity({})
        raw = available * self._trade_fraction / price
        return raw.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)

    def _close_trade(
        self,
        trade: BacktestTrade,
        candle: Candle,
        bar_index: int,
        close_order: PaperOrder,
        reason: str,
    ) -> None:
        """Fill exit details on a trade."""
        trade.exit_time = candle.datetime
        trade.exit_bar_index = bar_index
        trade.exit_price = close_order.price
        trade.pnl = close_order.pnl
        trade.exit_reason = reason
        if trade.entry_price > 0:
            raw_pct = float((close_order.price - trade.entry_price) / trade.entry_price)
            trade.pnl_pct = raw_pct if trade.side == Side.LONG else -raw_pct

    def _empty_result(self, symbol: Symbol, timeframe: Timeframe) -> BacktestResult:
        """Return a zero-result when there isn't enough data."""
        metrics = compute_metrics([], [], 0, 0.0, self._portfolio.cash)
        return BacktestResult(
            symbol=symbol,
            timeframe=timeframe,
            strategy_id=self._strategy.id,
            strategy_params=dict(self._strategy.params),
            starting_capital=self._portfolio.cash,
            final_equity=self._portfolio.cash,
            cash_remaining=self._portfolio.cash,
            total_return_pct=0.0,
            trades=[],
            equity_curve=[],
            metrics=metrics,
            bar_count=0,
        )
