"""Bot orchestration engine — the main loop.

Flow (per iteration):

  1. For each configured (symbol, timeframe), fetch candles and evaluate all
     registered strategies.
  2. For each non-HOLD signal, create an ``OrderIntent``.
  3. Entries: run risk checks → execute fill → update portfolio → persist.
  4. Exits: find open position → execute close → update portfolio → persist.
  5. Update current prices on all open positions.
  6. Report results.

Error isolation: a failure in one symbol does not block the rest.
"""

from __future__ import annotations

import logging
import signal as os_signal
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from decimal import ROUND_DOWN, Decimal

from bot.config import BotConfig
from bot.data.provider import MarketDataProvider
from bot.domain.models import (
    MarketQuote,
    OrderIntent,
    PortfolioSnapshot,
    Side,
    Signal,
    SignalAction,
    Symbol,
)
from bot.domain.utc import utc_now
from bot.execution.executor import PaperExecutor
from bot.portfolio.service import PortfolioService
from bot.repositories.memory import InMemoryOrderRepository, InMemoryPositionRepository
from bot.repositories.signal import InMemorySignalRepository, SignalRepository
from bot.risk.manager import RiskManager
from bot.strategies.registry import StrategyRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Result
# ---------------------------------------------------------------------------


@dataclass
class EngineResult:
    """Structured outcome of a single ``run_once()`` iteration."""

    timestamp: datetime
    symbols_evaluated: int = 0
    signals_generated: int = 0
    orders_created: int = 0
    orders_rejected: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------


class BotEngine:
    """Orchestration engine for the paper-trading bot.

    Accepts all dependencies via constructor for testability.  Call
    ``run_once()`` for a single iteration or ``run_forever()`` for the
    continuous loop.
    """

    # Default fraction of available cash to risk per entry trade
    DEFAULT_TRADE_FRACTION = Decimal("0.1")

    def __init__(
        self,
        config: BotConfig,
        data_provider: MarketDataProvider,
        registry: StrategyRegistry,
        portfolio: PortfolioService,
        risk_manager: RiskManager,
        executor: PaperExecutor,
        order_repo: InMemoryOrderRepository | None = None,
        position_repo: InMemoryPositionRepository | None = None,
        signal_repo: SignalRepository | None = None,
        trade_fraction: Decimal | None = None,
    ) -> None:
        self._config = config
        self._data = data_provider
        self._registry = registry
        self._portfolio = portfolio
        self._risk = risk_manager
        self._executor = executor
        self._order_repo = order_repo if order_repo is not None else InMemoryOrderRepository()
        self._position_repo = (
            position_repo if position_repo is not None else InMemoryPositionRepository()
        )
        self._signal_repo = signal_repo if signal_repo is not None else InMemorySignalRepository()
        self._trade_fraction = (
            trade_fraction if trade_fraction is not None else self.DEFAULT_TRADE_FRACTION
        )
        self._running = False
        # Cache of seen decision keys for O(1) duplicate detection.
        # Lazily hydrated from the order repo on first use.
        self._seen_keys: set[str] = set()
        # In-memory equity curve trail.
        self._equity_curve: list[PortfolioSnapshot] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def run_once(self) -> EngineResult:
        """Execute one full evaluation-persist cycle."""
        result = EngineResult(timestamp=utc_now())

        for symbol in self._config.symbols:
            try:
                self._evaluate_symbol(symbol, result)
            except Exception as exc:
                msg = f"{symbol}: {exc}"
                logger.warning(msg)
                result.errors.append(msg)

        self._update_position_prices(result)
        self._equity_curve.append(self._portfolio.snapshot(self._current_prices()))
        return result

    def run_forever(self) -> None:
        """Continuous loop with configurable poll interval.

        Handles SIGINT/SIGTERM for graceful shutdown.
        """
        self._running = True

        def _stop(_signum: int, _frame: object) -> None:
            logger.info("Shutdown signal received — stopping engine.")
            self._running = False

        # Trap termination signals
        if sys.platform != "win32":
            os_signal.signal(os_signal.SIGTERM, _stop)
        os_signal.signal(os_signal.SIGINT, _stop)

        logger.info(
            "Bot engine started — polling every %ds",
            self._config.poll_interval_seconds,
        )

        while self._running:
            result = self.run_once()
            if result.orders_created > 0 or result.errors:
                logger.info(
                    "Cycle done — %d signals, %d orders, %d rejected, %d errors",
                    result.signals_generated,
                    result.orders_created,
                    result.orders_rejected,
                    len(result.errors),
                )
            time.sleep(self._config.poll_interval_seconds)

        logger.info("Bot engine stopped.")

    # ------------------------------------------------------------------
    # Per-symbol evaluation
    # ------------------------------------------------------------------

    def _evaluate_symbol(self, symbol: Symbol, result: EngineResult) -> None:
        """Run all timeframes and strategies for *symbol*."""
        result.symbols_evaluated += 1

        for timeframe in self._config.timeframes:
            candles = self._data.fetch_ohlcv(symbol, timeframe, self._config.lookback_bars)

            for strategy in self._registry.available:
                signal = strategy.evaluate(candles)
                if signal.action == SignalAction.HOLD:
                    continue

                result.signals_generated += 1

                quote = self._data.fetch_quote(symbol)
                if quote is None:
                    continue

                self._process_signal(signal, quote, result)

    # ------------------------------------------------------------------
    # Signal processing
    # ------------------------------------------------------------------

    def _process_signal(self, signal: Signal, quote: MarketQuote, result: EngineResult) -> None:
        """Route entry/exit signals to the appropriate handler."""
        if signal.action in (SignalAction.ENTER_LONG, SignalAction.ENTER_SHORT):
            self._process_entry(signal, quote, result)
        elif signal.action in (SignalAction.EXIT_LONG, SignalAction.EXIT_SHORT):
            self._process_exit(signal, quote, result)

    def _process_entry(self, signal: Signal, quote: MarketQuote, result: EngineResult) -> None:
        """Evaluate risk, execute fill, update portfolio, and persist."""
        side = Side.LONG if signal.action == SignalAction.ENTER_LONG else Side.SHORT
        quantity = self._compute_quantity(side, quote.price)
        if quantity <= 0:
            return

        intent = OrderIntent(symbol=signal.symbol, side=side, quantity=quantity, signal=signal)

        # Lazily hydrate seen-keys cache from existing orders
        if not self._seen_keys:
            self._seen_keys = {o.decision_key for o in self._order_repo}

        decision = self._risk.check_order(
            intent, self._portfolio, quote, existing_keys=self._seen_keys
        )
        if not decision.approved:
            logger.debug(
                "Risk rejected %s %s %s: %s",
                signal.symbol,
                side,
                quantity,
                decision.reason,
            )
            result.orders_rejected += 1
            return

        order = self._executor.fill_order(intent, quote)
        self._portfolio.apply_fill(order)
        self._order_repo.save(order)
        if order.decision_key:
            self._seen_keys.add(order.decision_key)

        # Persist signal only after risk-approved entry
        self._signal_repo.save(signal)

        # Persist position if it's now open
        pos = self._portfolio.get_position(signal.symbol, side)
        if pos is not None:
            self._position_repo.save(pos)

        result.orders_created += 1

    def _process_exit(self, signal: Signal, quote: MarketQuote, result: EngineResult) -> None:
        """Close an existing position triggered by an exit signal."""
        # The side of the position to close
        exit_side = Side.LONG if signal.action == SignalAction.EXIT_LONG else Side.SHORT

        position = self._portfolio.get_position(signal.symbol, exit_side)
        if position is None:
            return

        close_order = self._portfolio.close_position(signal.symbol, exit_side, quote.price)
        close_order.decision_key = signal.decision_key  # propagate for traceability
        self._order_repo.save(close_order)
        self._position_repo.delete(signal.symbol, exit_side)
        if close_order.decision_key:
            self._seen_keys.add(close_order.decision_key)

        # Persist signal only after confirmed close
        self._signal_repo.save(signal)

        result.orders_created += 1

    # ------------------------------------------------------------------
    # Position price updates
    # ------------------------------------------------------------------

    def _update_position_prices(self, result: EngineResult) -> None:
        """Refresh current_price on all open positions."""
        for pos in self._portfolio.positions:
            try:
                quote = self._data.fetch_quote(pos.symbol)
                if quote is None:
                    continue
                pos.current_price = quote.price
                # Compute unrealized PnL
                if pos.side == Side.LONG:
                    pos.unrealized_pnl = (quote.price - pos.entry_price) * pos.quantity
                else:
                    pos.unrealized_pnl = (pos.entry_price - quote.price) * pos.quantity
                self._position_repo.save(pos)
            except Exception as exc:
                result.errors.append(f"price-update-{pos.symbol}: {exc}")

    # ------------------------------------------------------------------
    # Quantity helpers
    # ------------------------------------------------------------------

    def _compute_quantity(self, side: Side, price: Decimal) -> Decimal:
        """Compute trade quantity based on available equity and trade fraction.

        Longs use available cash; shorts use total equity as collateral.
        """
        if side == Side.LONG:
            available = self._portfolio.cash
        else:
            available = self._portfolio.total_equity(self._current_prices())

        raw = available * self._trade_fraction / price
        return raw.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)

    def _current_prices(self) -> dict[Symbol, Decimal]:
        """Fetch current prices for all symbols with open positions."""
        prices: dict[Symbol, Decimal] = {}
        for pos in self._portfolio.positions:
            try:
                quote = self._data.fetch_quote(pos.symbol)
                if quote is not None:
                    prices[pos.symbol] = quote.price
            except Exception as exc:
                logger.warning("Failed to fetch price for %s: %s", pos.symbol, exc)
        return prices
