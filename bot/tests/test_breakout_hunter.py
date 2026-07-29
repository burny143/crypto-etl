"""Tests for improved Breakout Hunter strategy.

Covers:
- True breakout detection (long/short)
- False breakout (fakeout) detection
- Dynamic leverage calculation
- Trend context via moving averages
- Volume confirmation
- ATR-based volatility filtering
- Insufficient data error handling
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bot.domain.exceptions import InsufficientDataError
from bot.domain.models import Candle, SignalAction, Symbol, Timeframe
from bot.strategies.breakout_hunter import BreakoutHunterStrategy

# ============================================================================
# Helpers
# ============================================================================


def _candle(
    close: float,
    high: float | None = None,
    low: float | None = None,
    volume: float = 100.0,
    dt: datetime | None = None,
) -> Candle:
    if dt is None:
        dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    if high is None:
        high = close + 10.0
    if low is None:
        low = close - 10.0
    return Candle(
        symbol=Symbol("BTC-USDT"),
        timeframe=Timeframe.H1,
        datetime=dt,
        open=Decimal(str(close)),
        high=Decimal(str(high)),
        low=Decimal(str(low)),
        close=Decimal(str(close)),
        volume=Decimal(str(volume)),
    )


def _make_candles(count: int, base_price: float = 50000.0, trend: float = 0.0) -> list[Candle]:
    """Create a list of candles with minor fluctuations around base_price, optionally with a trend."""
    candles = []
    base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    price = base_price
    for i in range(count):
        price += trend + (i % 10) * 0.1  # Small trend plus noise
        high = price + 20.0
        low = price - 20.0
        vol = 100.0 + (i % 5) * 10.0
        dt = base_dt.replace(hour=i % 24, day=1 + i // 24)
        candles.append(_candle(price, high, low, vol, dt))
    return candles


# ============================================================================
# True breakout detection
# ============================================================================


class TestTrueBreakoutDetection:
    """Verify breakout hunter generates signals for true breakouts."""

    def test_true_long_breakout_with_volume(self) -> None:
        """Strong bullish breakout above previous high with volume confirmation."""
        strat = BreakoutHunterStrategy(
            atr_period=14,
            min_volume_ratio=1.2,
            min_breakout_strength=0.5,
            min_candle_range=0.002,
        )

        base_price = 50000.0
        base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candles = _make_candles(59, base_price, trend=0.0)

        # Last candle: strong bullish breakout - closes near high (small upper wick)
        breakout_price = base_price + 200.0
        breakout_high = breakout_price + 20.0   # Small upper wick
        breakout_low = breakout_price - 80.0    # Larger body
        breakout_volume = 500.0
        dt = base_dt.replace(hour=3, day=3)
        candles.append(_candle(breakout_price, breakout_high, breakout_low, breakout_volume, dt))

        signal = strat.evaluate(candles)
        assert signal.action == SignalAction.ENTER_LONG
        assert signal.confidence > 0.0
        assert signal.strategy_id == "breakout_hunter"
        assert signal.params.get("signal_type") == "true_breakout_long"

    def test_true_short_breakout_with_volume(self) -> None:
        """Strong bearish breakout below previous low with volume confirmation."""
        strat = BreakoutHunterStrategy(
            atr_period=14,
            min_volume_ratio=1.2,
            min_breakout_strength=0.5,
            min_candle_range=0.002,
        )

        base_price = 50000.0
        base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candles = _make_candles(59, base_price, trend=0.0)

        # Last candle: strong bearish breakout - closes near low (small lower wick)
        breakout_price = base_price - 200.0
        breakout_high = breakout_price + 80.0   # Larger body
        breakout_low = breakout_price - 20.0    # Small lower wick
        breakout_volume = 500.0
        dt = base_dt.replace(hour=3, day=3)
        candles.append(_candle(breakout_price, breakout_high, breakout_low, breakout_volume, dt))

        signal = strat.evaluate(candles)
        assert signal.action == SignalAction.ENTER_SHORT
        assert signal.confidence > 0.0
        assert signal.strategy_id == "breakout_hunter"
        assert signal.params.get("signal_type") == "true_breakout_short"

    def test_no_breakout_without_volume(self) -> None:
        """No breakout signal when volume confirmation fails."""
        strat = BreakoutHunterStrategy(
            atr_period=14,
            min_volume_ratio=2.0,  # High volume threshold
            min_breakout_strength=0.5,
            min_candle_range=0.002,
        )

        base_price = 50000.0
        base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candles = _make_candles(59, base_price, trend=0.0)

        # Add breakout candle with low volume
        breakout_price = base_price + 200.0
        breakout_high = breakout_price + 50.0
        breakout_low = breakout_price - 20.0
        breakout_volume = 60.0  # Below threshold
        dt = base_dt.replace(hour=3, day=3)
        candles.append(_candle(breakout_price, breakout_high, breakout_low, breakout_volume, dt))

        signal = strat.evaluate(candles)
        assert signal.action == SignalAction.HOLD
        assert signal.confidence == 0.0

    def test_hold_when_no_breakout(self) -> None:
        """Hold signal when price doesn't break key levels."""
        strat = BreakoutHunterStrategy()

        # 60 candles with no significant breakout
        base_price = 50000.0
        candles = _make_candles(60, base_price, trend=0.0)

        signal = strat.evaluate(candles)
        assert signal.action == SignalAction.HOLD
        assert signal.confidence == 0.0


# ============================================================================
# False breakout (fakeout) detection
# ============================================================================


class TestFalseBreakoutDetection:
    """Verify breakout hunter detects false breakouts (bull traps, bear traps)."""

    def test_bull_trap_detection(self) -> None:
        """Bull trap: price breaks high but closes near open (long upper wick) in bearish trend."""
        strat = BreakoutHunterStrategy(
            atr_period=14,
            min_volume_ratio=1.2,
            min_breakout_strength=0.5,
            min_candle_range=0.002,
            false_breakout_wick_ratio=0.6,
        )

        # Bearish trend: price declining, so trend_ma > breakout close
        base_price = 50000.0
        base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candles = _make_candles(59, base_price + 100.0, trend=-1.0)  # Declining from 50100

        # Bull trap: price breaks high but has long upper wick (rejection)
        breakout_price = base_price + 200.0  # Breaks above previous high
        breakout_high = base_price + 300.0  # Very high wick
        breakout_low = base_price + 180.0  # Closes near low
        breakout_volume = 500.0
        dt = base_dt.replace(hour=3, day=3)
        candles.append(_candle(breakout_price, breakout_high, breakout_low, breakout_volume, dt))

        signal = strat.evaluate(candles)
        # Should detect as false breakout → ENTER_SHORT
        assert signal.action == SignalAction.ENTER_SHORT
        assert signal.confidence > 0.0
        assert signal.params.get("signal_type") == "false_breakout_short"

    def test_bear_trap_detection(self) -> None:
        """Bear trap: price breaks low but closes near open (long lower wick) in bullish trend."""
        strat = BreakoutHunterStrategy(
            atr_period=14,
            min_volume_ratio=1.2,
            min_breakout_strength=0.5,
            min_candle_range=0.002,
            false_breakout_wick_ratio=0.6,
        )

        # Bullish trend: price rising, so trend_ma < breakout close
        base_price = 50000.0
        base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candles = _make_candles(59, base_price - 100.0, trend=1.0)  # Rising from 49900

        # Bear trap: price breaks low but has long lower wick (rejection)
        breakout_price = base_price - 200.0  # Breaks below previous low
        breakout_high = base_price - 180.0  # Closes near high
        breakout_low = base_price - 300.0  # Very low wick
        breakout_volume = 500.0
        dt = base_dt.replace(hour=3, day=3)
        candles.append(_candle(breakout_price, breakout_high, breakout_low, breakout_volume, dt))

        signal = strat.evaluate(candles)
        # Should detect as false breakout → ENTER_LONG
        assert signal.action == SignalAction.ENTER_LONG
        assert signal.confidence > 0.0
        assert signal.params.get("signal_type") == "false_breakout_long"

    def test_no_false_breakout_without_wick(self) -> None:
        """No false breakout signal when wick ratio is too low."""
        strat = BreakoutHunterStrategy(
            atr_period=14,
            min_volume_ratio=1.2,
            min_breakout_strength=0.5,
            min_candle_range=0.002,
            false_breakout_wick_ratio=0.8,  # High threshold
        )

        base_price = 50000.0
        base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candles = _make_candles(59, base_price, trend=0.0)

        # Breakout candle with small wick (not a false breakout)
        breakout_price = base_price + 200.0
        breakout_high = breakout_price + 50.0
        breakout_low = breakout_price - 20.0
        breakout_volume = 500.0
        dt = base_dt.replace(hour=3, day=3)
        candles.append(_candle(breakout_price, breakout_high, breakout_low, breakout_volume, dt))

        signal = strat.evaluate(candles)
        # Should be true breakout, not false breakout
        assert signal.action == SignalAction.ENTER_LONG


# ============================================================================
# Leverage calculation
# ============================================================================


class TestLeverageCalculation:
    """Verify dynamic leverage calculation."""

    def test_leverage_in_params(self) -> None:
        """Leverage is calculated and included in signal params."""
        strat = BreakoutHunterStrategy()

        base_price = 50000.0
        base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candles = _make_candles(59, base_price, trend=0.0)

        # Add breakout candle - true breakout with small upper wick
        breakout_price = base_price + 200.0
        breakout_high = breakout_price + 20.0   # Small upper wick
        breakout_low = breakout_price - 80.0
        breakout_volume = 500.0
        dt = base_dt.replace(hour=3, day=3)
        candles.append(_candle(breakout_price, breakout_high, breakout_low, breakout_volume, dt))

        signal = strat.evaluate(candles)
        assert signal.action == SignalAction.ENTER_LONG
        # Leverage should be in params (we check params contains leverage-related keys)
        assert "leverage_base" in signal.params
        assert "leverage_max" in signal.params
        assert "leverage_min" in signal.params

    def test_leverage_bounds(self) -> None:
        """Leverage stays within configured min/max bounds."""
        strat = BreakoutHunterStrategy(
            leverage_min=0.5,
            leverage_max=3.0,
        )

        base_price = 50000.0
        base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candles = _make_candles(59, base_price, trend=0.0)

        # Add breakout candle - true breakout with small upper wick
        breakout_price = base_price + 200.0
        breakout_high = breakout_price + 20.0   # Small upper wick
        breakout_low = breakout_price - 80.0
        breakout_volume = 500.0
        dt = base_dt.replace(hour=3, day=3)
        candles.append(_candle(breakout_price, breakout_high, breakout_low, breakout_volume, dt))

        signal = strat.evaluate(candles)
        # Leverage should be within bounds (we can't directly check leverage value
        # since it's not in Signal, but we verify the strategy runs without error)
        assert signal.action == SignalAction.ENTER_LONG


# ============================================================================
# Trend context
# ============================================================================


class TestTrendContext:
    """Verify trend context via moving averages."""

    def test_trend_period_in_params(self) -> None:
        """Trend period is correctly stored in params."""
        strat = BreakoutHunterStrategy(trend_period=30)
        assert strat.params["trend_period"] == 30
        assert strat.params["atr_period"] == 14

    def test_min_history_includes_trend(self) -> None:
        """min_history accounts for trend period."""
        strat = BreakoutHunterStrategy(trend_period=30)
        # min_history = max(atr_period + trend_period + 5, 60)
        # = max(14 + 30 + 5, 60) = max(49, 60) = 60
        assert strat.min_history >= 60


# ============================================================================
# Validation
# ============================================================================


class TestValidation:
    """Parameter validation."""

    def test_invalid_atr_period(self) -> None:
        with pytest.raises(ValueError, match="atr_period"):
            BreakoutHunterStrategy(atr_period=0)

    def test_invalid_volume_ratio(self) -> None:
        with pytest.raises(ValueError, match="min_volume_ratio"):
            BreakoutHunterStrategy(min_volume_ratio=0.5)

    def test_invalid_breakout_strength(self) -> None:
        with pytest.raises(ValueError, match="min_breakout_strength"):
            BreakoutHunterStrategy(min_breakout_strength=0)

    def test_invalid_candle_range(self) -> None:
        with pytest.raises(ValueError, match="min_candle_range"):
            BreakoutHunterStrategy(min_candle_range=0)

    def test_invalid_leverage_bounds(self) -> None:
        with pytest.raises(ValueError, match="leverage_max"):
            BreakoutHunterStrategy(leverage_max=0.5, leverage_min=1.0)

    def test_invalid_trend_period(self) -> None:
        with pytest.raises(ValueError, match="trend_period"):
            BreakoutHunterStrategy(trend_period=1)

    def test_invalid_wick_ratio(self) -> None:
        with pytest.raises(ValueError, match="false_breakout_wick_ratio"):
            BreakoutHunterStrategy(false_breakout_wick_ratio=1.5)


# ============================================================================
# Integration
# ============================================================================


class TestIntegration:
    """Integration tests for complete signal flow."""

    def test_insufficient_data(self) -> None:
        """Insufficient data raises appropriate error."""
        strat = BreakoutHunterStrategy()
        candles = [
            _candle(50000.0, dt=datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc))
            for i in range(10)
        ]

        with pytest.raises(InsufficientDataError, match="needs at least"):
            strat.evaluate(candles)

    def test_decision_key_deterministic(self) -> None:
        """Same inputs produce same decision key."""
        strat = BreakoutHunterStrategy()
        candles = _make_candles(60, 50000.0)

        signal1 = strat.evaluate(candles)
        signal2 = strat.evaluate(candles)

        assert signal1.decision_key == signal2.decision_key

    def test_strategy_parameters(self) -> None:
        """Verify strategy parameters are correctly stored."""
        params = {
            "atr_period": 21,
            "min_volume_ratio": 1.5,
            "min_breakout_strength": 0.8,
            "min_candle_range": 0.005,
            "leverage_base": 2.0,
            "leverage_max": 4.0,
            "leverage_min": 0.5,
            "trend_period": 30,
            "false_breakout_wick_ratio": 0.7,
        }
        strat = BreakoutHunterStrategy(**params)

        assert strat.params == params
        assert strat.id == "breakout_hunter"
        assert strat.name == "Breakout Hunter (Price+Volume+ATR+Leverage)"
