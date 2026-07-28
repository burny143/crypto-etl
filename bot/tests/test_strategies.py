"""Tests for strategy evaluation framework.

Covers RSI calculation semantics (matching ``strategy_research.py``),
signal classification, deterministic decision keys, and the registry.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bot.domain.exceptions import InsufficientDataError
from bot.domain.models import Candle, SignalAction, Symbol, Timeframe
from bot.strategies.registry import StrategyRegistry
from bot.strategies.rsi import RsiReversionStrategy, _decision_key, _rsi

# ===========================================================================
# Helpers
# ===========================================================================


def _candle(close: float, dt: datetime | None = None) -> Candle:
    if dt is None:
        dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    return Candle(
        symbol=Symbol("BTC-USDT"),
        timeframe=Timeframe.H1,
        datetime=dt,
        open=Decimal(str(close)),
        high=Decimal(str(close + 10)),
        low=Decimal(str(close - 10)),
        close=Decimal(str(close)),
        volume=Decimal("100"),
    )


# ===========================================================================
# RSI calculation
# ===========================================================================


class TestRsiCalculation:
    """Verify RSI matches ``strategy_research.py::_rsi`` semantics."""

    def test_rsi_with_known_input(self) -> None:
        """Known prices → known RSI (computed independently)."""
        # fmt: off
        closes = [
            44.34, 44.09, 44.15, 43.61, 44.33,
            44.83, 45.10, 45.42, 45.84, 46.08,
            45.89, 46.03, 45.61, 46.28, 46.28,
            46.00, 46.03, 46.41, 46.22, 46.21,
        ]
        # fmt: on
        # RSI(14) using SMA-based calculation (matching strategy_research.py)
        rsi = _rsi(closes, period=14)
        assert rsi is not None
        # Last 15 closes are mostly up → RSI above 50
        assert rsi > 50.0

    def test_rsi_oversold_uptick(self) -> None:
        """Sharp drop then mild recovery → RSI reflects the initial losses."""
        closes = [
            100.0,
            90.0,
            80.0,
            70.0,
            60.0,  # five consecutive drops (-10 each)
            61.0,
            62.0,
            63.0,
            64.0,
            65.0,  # five consecutive gains (+1 each)
            66.0,
            67.0,
            68.0,
            69.0,
            70.0,  # continued gains (+1 each)
        ]
        rsi = _rsi(closes, period=14)
        assert rsi is not None
        # Large early losses dominate SMA — RSI still below 30
        assert rsi < 30.0

    def test_rsi_all_gains(self) -> None:
        """Constantly increasing prices → RSI = 100."""
        closes = [float(i) for i in range(1, 20)]
        rsi = _rsi(closes, period=14)
        assert rsi is not None
        assert rsi == 100.0

    def test_rsi_all_losses(self) -> None:
        """Constantly decreasing prices → RSI = 0."""
        closes = [float(i) for i in range(20, 0, -1)]
        rsi = _rsi(closes, period=14)
        assert rsi is not None
        assert rsi == 0.0

    def test_rsi_insufficient_data(self) -> None:
        """Fewer than period+1 closes → None."""
        closes = [1.0, 2.0, 3.0]  # only 3, need 15 for period=14
        rsi = _rsi(closes, period=14)
        assert rsi is None


# ===========================================================================
# Signal classification
# ===========================================================================


class TestRsiSignalClassification:
    """Verify strategy generates correct actions for various RSI levels."""

    def test_enter_long_when_oversold(self) -> None:
        strat = RsiReversionStrategy(period=14, oversold=30, overbought=70)
        # RSI < 30 → ENTER_LONG
        candles = [
            _candle(50.0, datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc)) for i in range(16)
        ]
        # Make prices drop sharply so RSI < 30
        for i in range(1, 16):
            candles[i] = _candle(
                50.0 - (i * 2.0),
                datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc),
            )
        signal = strat.evaluate(candles)
        assert signal.action == SignalAction.ENTER_LONG
        assert signal.confidence > 0.0

    def test_enter_short_when_overbought(self) -> None:
        strat = RsiReversionStrategy(period=14, oversold=30, overbought=70)
        # RSI > 70 → ENTER_SHORT
        candles = [
            _candle(50.0, datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc)) for i in range(16)
        ]
        for i in range(1, 16):
            candles[i] = _candle(
                50.0 + (i * 2.0),
                datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc),
            )
        signal = strat.evaluate(candles)
        assert signal.action == SignalAction.ENTER_SHORT
        assert signal.confidence > 0.0

    def test_hold_in_neutral_zone(self) -> None:
        strat = RsiReversionStrategy(period=14, oversold=30, overbought=70)
        # RSI between 30 and 70 → HOLD
        candles = [
            _candle(50.0, datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc)) for i in range(16)
        ]
        # Keep prices roughly flat
        signal = strat.evaluate(candles)
        assert signal.action == SignalAction.HOLD
        assert signal.confidence == 0.0

    def test_insufficient_data_raises(self) -> None:
        strat = RsiReversionStrategy(period=14)
        candles = [_candle(50.0) for _ in range(5)]  # only 5, need 15
        with pytest.raises(InsufficientDataError, match="needs at least"):
            strat.evaluate(candles)

    def test_signal_has_all_fields(self) -> None:
        strat = RsiReversionStrategy(period=14)
        candles = [
            _candle(float(i), datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc)) for i in range(16)
        ]
        signal = strat.evaluate(candles)
        assert signal.symbol == "BTC-USDT"
        assert signal.timeframe == Timeframe.H1
        assert signal.strategy_id == "rsi_reversion"
        assert signal.candle_timestamp is not None
        assert len(signal.decision_key) == 64  # sha256 hex
        assert isinstance(signal.params, dict)
        assert signal.params["period"] == 14


# ===========================================================================
# Decision keys
# ===========================================================================


class TestDecisionKeys:
    """Deterministic, collision-resistant signal dedup keys."""

    def test_deterministic(self) -> None:
        """Same inputs → same key."""
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        k1 = _decision_key("rsi_reversion", Symbol("BTC-USDT"), Timeframe.H1, ts)
        k2 = _decision_key("rsi_reversion", Symbol("BTC-USDT"), Timeframe.H1, ts)
        assert k1 == k2

    def test_different_symbols(self) -> None:
        """Different symbols → different keys."""
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        k1 = _decision_key("rsi_reversion", Symbol("BTC-USDT"), Timeframe.H1, ts)
        k2 = _decision_key("rsi_reversion", Symbol("ETH-USDT"), Timeframe.H1, ts)
        assert k1 != k2

    def test_different_timestamps(self) -> None:
        """Different candle timestamps → different keys."""
        k1 = _decision_key(
            "rsi_reversion",
            Symbol("BTC-USDT"),
            Timeframe.H1,
            datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        )
        k2 = _decision_key(
            "rsi_reversion",
            Symbol("BTC-USDT"),
            Timeframe.H1,
            datetime(2026, 1, 1, 13, 0, 0, tzinfo=timezone.utc),
        )
        assert k1 != k2

    def test_sha256_format(self) -> None:
        """Decision key is a 64-char hex string."""
        ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        key = _decision_key("rsi_reversion", Symbol("BTC-USDT"), Timeframe.H1, ts)
        assert len(key) == 64
        int(key, 16)  # should not raise


# ===========================================================================
# Registry
# ===========================================================================


class TestStrategyRegistry:
    """Strategy registration and lookup."""

    def test_register_and_get(self) -> None:
        registry = StrategyRegistry()
        strat = RsiReversionStrategy(period=14)
        registry.register(strat)
        assert registry.get("rsi_reversion") is strat

    def test_duplicate_registration_raises(self) -> None:
        registry = StrategyRegistry()
        registry.register(RsiReversionStrategy())
        with pytest.raises(KeyError, match="already registered"):
            registry.register(RsiReversionStrategy())

    def test_unknown_strategy_raises(self) -> None:
        registry = StrategyRegistry()
        with pytest.raises(KeyError, match="Unknown strategy"):
            registry.get("nonexistent")

    def test_register_defaults(self) -> None:
        registry = StrategyRegistry()
        registry.register_defaults()
        assert "rsi_reversion" in registry
        assert "breakout_hunter" in registry
        assert len(registry.available) == 2

    def test_available_and_ids(self) -> None:
        registry = StrategyRegistry()
        registry.register(RsiReversionStrategy())
        assert registry.ids == ["rsi_reversion"]
        assert len(registry.available) == 1


# ===========================================================================
# Validation
# ===========================================================================


class TestRsiValidation:
    """Strategy parameter validation."""

    def test_invalid_period(self) -> None:
        with pytest.raises(ValueError, match="period"):
            RsiReversionStrategy(period=1)

    def test_invalid_thresholds(self) -> None:
        with pytest.raises(ValueError, match="oversold < overbought"):
            RsiReversionStrategy(oversold=70, overbought=30)
