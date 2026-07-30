"""Tests for the backtesting engine and metrics."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bot.backtesting.backtester import BacktestEngine, BacktestResult, BacktestTrade
from bot.backtesting.metrics import BacktestMetrics, compute_metrics
from bot.config import BotConfig
from bot.domain.models import (
    Candle,
    OrderIntent,
    OrderStatus,
    PaperOrder,
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


# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def btc() -> Symbol:
    return Symbol("BTC-USDT")


@pytest.fixture
def cfg() -> BotConfig:
    return BotConfig(
        {
            "symbols": ["BTC-USDT"],
            "timeframes": ["1h"],
            "poll_interval_seconds": 60,
            "price_max_age_seconds": 120,
            "candle_grace_seconds": 30,
            "lookback_bars": 200,
            "starting_balance": 10000.0,
            "logging_level": "ERROR",
        }
    )


def _make_candle(
    symbol: Symbol,
    ts: datetime,
    close: int,
    open_: int | None = None,
    high: int | None = None,
    low: int | None = None,
    volume: int = 1000,
) -> Candle:
    d = Decimal(str(close))
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.H1,
        datetime=ts,
        open=Decimal(str(open_ if open_ is not None else close)),
        high=Decimal(str(high if high is not None else close)),
        low=Decimal(str(low if low is not None else close)),
        close=d,
        volume=Decimal(str(volume)),
    )


def _candle_series(
    symbol: Symbol,
    closes: list[int],
    start: datetime | None = None,
) -> list[Candle]:
    """Build a candle list from close values."""
    if start is None:
        start = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return [
        _make_candle(symbol, start.replace(hour=h % 24), close)
        for h, close in enumerate(closes)
    ]


# ===========================================================================
# Fixed-signal strategy for test determinism
# ===========================================================================


class FixedSequenceStrategy:
    """Strategy that yields predetermined signals in order."""

    def __init__(
        self,
        signals: list[Signal],
        strategy_id: str = "test_backtest",
        min_history: int = 1,
    ) -> None:
        self._signals = signals
        self._idx = 0
        self._strategy_id = strategy_id
        self._min_history = min_history

    @property
    def id(self) -> str:
        return self._strategy_id

    @property
    def name(self) -> str:
        return "Test Backtest Strategy"

    @property
    def params(self) -> dict:
        return {}

    @property
    def min_history(self) -> int:
        return self._min_history

    def evaluate(self, candles: list[Candle]) -> Signal:
        if self._idx >= len(self._signals):
            return Signal(
                symbol=candles[-1].symbol if candles else Symbol("BTC-USDT"),
                timeframe=Timeframe.H1,
                strategy_id=self._strategy_id,
                action=SignalAction.HOLD,
                confidence=0.0,
                candle_timestamp=utc_now(),
                decision_key="end-of-sequence",
            )
        sig = self._signals[self._idx]
        self._idx += 1
        return sig


# ===========================================================================
# Test: compute_metrics
# ===========================================================================


class TestComputeMetrics:
    """Unit tests for the metrics computation."""

    def test_empty(self) -> None:
        """Empty inputs should return zero metrics."""
        m = compute_metrics([], [], 0, 0.0, Decimal("10000"))
        assert m.total_trades == 0
        assert m.total_return_pct == 0.0
        assert m.sharpe_ratio == 0.0

    def test_all_winners(self) -> None:
        """All trades profitable."""
        m = compute_metrics(
            trade_pnls=[Decimal("100"), Decimal("200"), Decimal("50")],
            equity_values=[Decimal("10000"), Decimal("10100"), Decimal("10300"), Decimal("10350")],
            total_trades=3,
            avg_holding_bars=5.0,
            starting_capital=Decimal("10000"),
        )
        assert m.total_trades == 3
        assert m.win_rate == 1.0
        assert m.profit_factor == float("inf")
        assert m.total_return_pct > 0

    def test_mixed_pnl(self) -> None:
        """Mix of winners and losers."""
        m = compute_metrics(
            trade_pnls=[Decimal("100"), Decimal("-50"), Decimal("200"), Decimal("-30")],
            equity_values=[Decimal("10000"), Decimal("10100"), Decimal("10050"),
                          Decimal("10250"), Decimal("10220")],
            total_trades=4,
            avg_holding_bars=3.0,
            starting_capital=Decimal("10000"),
        )
        assert m.total_trades == 4
        assert 0 < m.win_rate < 1.0
        assert m.profit_factor > 0

    def test_negative_return(self) -> None:
        """All trades losing."""
        m = compute_metrics(
            trade_pnls=[Decimal("-100"), Decimal("-200")],
            equity_values=[Decimal("10000"), Decimal("9900"), Decimal("9700")],
            total_trades=2,
            avg_holding_bars=2.0,
            starting_capital=Decimal("10000"),
        )
        assert m.total_return_pct < 0
        assert m.win_rate == 0.0

    def test_max_drawdown(self) -> None:
        """Drawdown measured correctly."""
        m = compute_metrics(
            trade_pnls=[Decimal("0")],
            equity_values=[Decimal("10000"), Decimal("11000"), Decimal("9000"),
                          Decimal("9500"), Decimal("10500")],
            total_trades=1,
            avg_holding_bars=1.0,
            starting_capital=Decimal("10000"),
        )
        # Peak 11000, trough 9000 → (11000-9000)/11000 = 18.18%
        assert m.max_drawdown_pct == pytest.approx(0.1818, abs=0.01)


# ===========================================================================
# Test: BacktestEngine
# ===========================================================================


class TestBacktestEngine:
    """Integration tests for the backtesting engine."""

    def _make_engine(
        self,
        cfg: BotConfig,
        strategy: AbstractStrategy,
        starting_balance: Decimal | None = None,
    ) -> BacktestEngine:
        portfolio = PortfolioService(
            starting_balance if starting_balance is not None else Decimal(str(cfg.starting_balance))
        )
        risk = RiskManager(cfg)
        executor = PaperExecutor(slippage_bps=0, fee_bps=0)
        return BacktestEngine(strategy, risk, executor, portfolio, trade_fraction=Decimal("1.0"))

    def test_insufficient_data(self, cfg, btc) -> None:
        """Should return empty result when not enough bars."""
        strategy = FixedSequenceStrategy([], min_history=100)
        engine = self._make_engine(cfg, strategy)
        candles = _candle_series(btc, [50000] * 10)

        result = engine.run(candles, btc, Timeframe.H1)
        assert result.bar_count == 0
        assert len(result.trades) == 0
        assert len(result.equity_curve) == 0

    def test_entry_long(self, cfg, btc) -> None:
        """Single long entry should create a trade, auto-closed at end."""
        signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.ENTER_LONG, confidence=0.8,
            candle_timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            decision_key="btc-long-1",
        )
        strategy = FixedSequenceStrategy([signal])
        engine = self._make_engine(cfg, strategy)
        candles = _candle_series(btc, [50000, 51000, 52000, 53000, 54000])

        result = engine.run(candles, btc, Timeframe.H1)
        # Position should be auto-closed at end of data
        assert len(result.trades) == 1
        assert result.trades[0].exit_reason == "close_at_end"
        assert len(result.equity_curve) > 0

    def test_entry_then_exit(self, cfg, btc) -> None:
        """Full round-trip: entry then exit."""
        ts1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        hold_ts = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        entry_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.ENTER_LONG, confidence=0.8,
            candle_timestamp=ts1, decision_key="entry-1",
        )
        hold_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.HOLD, confidence=0.0,
            candle_timestamp=hold_ts, decision_key="hold",
        )
        exit_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.EXIT_LONG, confidence=0.7,
            candle_timestamp=ts2, decision_key="exit-1",
        )
        strategy = FixedSequenceStrategy([entry_signal, hold_signal, exit_signal])
        engine = self._make_engine(cfg, strategy)
        candles = _candle_series(btc, [50000, 50000, 52000, 53000, 54000])

        result = engine.run(candles, btc, Timeframe.H1)
        assert len(result.trades) >= 1
        trade = result.trades[0]
        assert trade.side == Side.LONG
        assert trade.pnl is not None
        assert trade.exit_reason == "signal"

    def test_entry_then_exit_with_profit(self, cfg, btc) -> None:
        """Long at 50000, exit at 52000 should have positive PnL."""
        ts1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        hold_ts = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        entry_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.ENTER_LONG, confidence=0.8,
            candle_timestamp=ts1, decision_key="entry-1",
        )
        hold_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.HOLD, confidence=0.0,
            candle_timestamp=hold_ts, decision_key="hold",
        )
        exit_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.EXIT_LONG, confidence=0.7,
            candle_timestamp=ts2, decision_key="exit-1",
        )
        strategy = FixedSequenceStrategy([entry_signal, hold_signal, exit_signal])
        engine = self._make_engine(cfg, strategy)
        # Price rises: entry at 50000 (bar 0), exit at 52000 (bar 2)
        candles = _candle_series(btc, [50000, 50000, 52000, 53000, 54000])

        result = engine.run(candles, btc, Timeframe.H1)
        assert len(result.trades) >= 1
        trade = result.trades[0]
        assert trade.pnl is not None and trade.pnl > 0

    def test_entry_then_exit_with_loss(self, cfg, btc) -> None:
        """Long at 50000, exit at 48000 should have negative PnL."""
        ts1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        hold_ts = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        entry_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.ENTER_LONG, confidence=0.8,
            candle_timestamp=ts1, decision_key="entry-1",
        )
        hold_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.HOLD, confidence=0.0,
            candle_timestamp=hold_ts, decision_key="hold",
        )
        exit_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.EXIT_LONG, confidence=0.7,
            candle_timestamp=ts2, decision_key="exit-1",
        )
        strategy = FixedSequenceStrategy([entry_signal, hold_signal, exit_signal])
        engine = self._make_engine(cfg, strategy)
        # Price drops: entry at 50000 (bar 0), exit at 48000 (bar 2)
        candles = _candle_series(btc, [50000, 50000, 48000, 48000, 47000])

        result = engine.run(candles, btc, Timeframe.H1)
        assert len(result.trades) >= 1
        trade = result.trades[0]
        assert trade.pnl is not None and trade.pnl < 0

    def test_short_entry_then_exit(self, cfg, btc) -> None:
        """Short entry then exit."""
        ts1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        hold_ts = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        entry_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.ENTER_SHORT, confidence=0.8,
            candle_timestamp=ts1, decision_key="short-1",
        )
        hold_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.HOLD, confidence=0.0,
            candle_timestamp=hold_ts, decision_key="hold",
        )
        exit_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.EXIT_SHORT, confidence=0.7,
            candle_timestamp=ts2, decision_key="exit-short-1",
        )
        strategy = FixedSequenceStrategy([entry_signal, hold_signal, exit_signal])
        engine = self._make_engine(cfg, strategy)
        candles = _candle_series(btc, [50000, 50000, 48000, 49000, 50000])

        result = engine.run(candles, btc, Timeframe.H1)
        assert len(result.trades) >= 1
        trade = result.trades[0]
        assert trade.side == Side.SHORT

    def test_auto_close_at_end(self, cfg, btc) -> None:
        """Position still open at end of data should be force-closed."""
        signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.ENTER_LONG, confidence=0.8,
            candle_timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            decision_key="entry-1",
        )
        strategy = FixedSequenceStrategy([signal])
        engine = self._make_engine(cfg, strategy)
        candles = _candle_series(btc, [50000, 51000, 52000])

        result = engine.run(candles, btc, Timeframe.H1)
        assert len(result.trades) == 1
        assert result.trades[0].exit_reason == "close_at_end"

    def test_risk_rejects_entry(self, cfg, btc) -> None:
        """Risk should reject if decision key is duplicated (idempotency)."""
        signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.ENTER_LONG, confidence=0.8,
            candle_timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            decision_key="dup-key",
        )
        # Strategy emits the same signal twice
        strategy = FixedSequenceStrategy([signal, signal])
        engine = self._make_engine(cfg, strategy)
        candles = _candle_series(btc, [50000, 51000, 52000, 53000, 54000])

        result = engine.run(candles, btc, Timeframe.H1)
        # Only one trade should be created (second one rejected as duplicate)
        assert len(result.trades) <= 1

    def test_equity_curve_length(self, cfg, btc) -> None:
        """Equity curve should have one entry per bar after min_history."""
        signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.ENTER_LONG, confidence=0.8,
            candle_timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            decision_key="entry",
        )
        strategy = FixedSequenceStrategy([signal], min_history=2)
        engine = self._make_engine(cfg, strategy)
        candles = _candle_series(btc, [50000, 51000, 52000, 53000, 54000])

        result = engine.run(candles, btc, Timeframe.H1)
        # Initial snapshot + one per bar after min_history-1: 1 + (5 - 2 + 1) = 5
        assert len(result.equity_curve) == len(candles) - strategy.min_history + 2

    def test_metrics_in_result(self, cfg, btc) -> None:
        """Complete backtest result should have computed metrics."""
        ts1 = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        hold_ts = datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 1, 1, 14, 0, 0, tzinfo=timezone.utc)
        entry_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.ENTER_LONG, confidence=0.8,
            candle_timestamp=ts1, decision_key="entry-m",
        )
        hold_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.HOLD, confidence=0.0,
            candle_timestamp=hold_ts, decision_key="hold-m",
        )
        exit_signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.EXIT_LONG, confidence=0.7,
            candle_timestamp=ts2, decision_key="exit-m",
        )
        strategy = FixedSequenceStrategy([entry_signal, hold_signal, exit_signal])
        engine = self._make_engine(cfg, strategy)
        candles = _candle_series(btc, [50000, 50000, 54000, 53000, 55000])

        result = engine.run(candles, btc, Timeframe.H1)
        m = result.metrics
        assert m.total_trades >= 1
        assert m.total_return_pct != 0.0
        assert m.sharpe_ratio != 0.0

    def test_different_starting_balance(self, cfg, btc) -> None:
        """Custom starting balance should be reflected in metrics."""
        signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.ENTER_LONG, confidence=0.8,
            candle_timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            decision_key="entry-b",
        )
        strategy = FixedSequenceStrategy([signal])
        engine = self._make_engine(cfg, strategy, starting_balance=Decimal("50000"))
        candles = _candle_series(btc, [50000, 51000, 52000])

        result = engine.run(candles, btc, Timeframe.H1)
        assert result.starting_capital == Decimal("50000")

    def test_to_dict_serializable(self, cfg, btc) -> None:
        """to_dict() should produce a JSON-serializable dict."""
        signal = Signal(
            symbol=btc, timeframe=Timeframe.H1, strategy_id="test",
            action=SignalAction.ENTER_LONG, confidence=0.8,
            candle_timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            decision_key="entry-json",
        )
        strategy = FixedSequenceStrategy([signal])
        engine = self._make_engine(cfg, strategy)
        candles = _candle_series(btc, [50000, 51000, 52000])

        result = engine.run(candles, btc, Timeframe.H1)
        d = result.to_dict()
        assert isinstance(d, dict)
        assert "symbol" in d
        assert "metrics" in d
        assert "trades" in d
        assert "equity_curve" in d


# ===========================================================================
# Test: BacktestTrade
# ===========================================================================


class TestBacktestTrade:
    """BacktestTrade dataclass."""

    def test_defaults(self) -> None:
        trade = BacktestTrade(
            symbol=Symbol("BTC-USDT"),
            side=Side.LONG,
            entry_time=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        assert trade.exit_time is None
        assert trade.pnl is None
        assert trade.exit_reason == ""
