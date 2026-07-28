"""Tests for Breakout Hunter strategy.

Covers:
- Breakout detection (long/short)
- Volume confirmation
- False breakout filtering
- ATR-based stop level validation
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


def _make_candles(count: int, base_price: float = 50000.0) -> list[Candle]:
    """Create a list of candles with minor fluctuations around base_price."""
    candles = []
    base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    for i in range(count):
        price = base_price + (i % 10) * 0.1  # Small fluctuations
        high = price + 20.0
        low = price - 20.0
        vol = 100.0 + (i % 5) * 10.0
        dt = base_dt.replace(hour=i % 24, day=1 + i // 24)
        candles.append(_candle(price, high, low, vol, dt))
    return candles


# ============================================================================
# Long breakout detection
# ============================================================================


class TestLongBreakoutDetection:
    """Verify breakout hunter generates ENTER_LONG signals."""

    def test_long_breakout_with_volume(self) -> None:
        """Strong bullish breakout above previous high with volume confirmation."""
        strat = BreakoutHunterStrategy(
            min_price_volume=1.2,
            atr_period=14,
            volatility_filter=0.5,
            min_breakout_strength=0.002,
        )

        # Build 52 candles (need 50+ for min_history)
        base_price = 50000.0
        base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candles = _make_candles(51, base_price)

        # Last candle: strong breakout with high volume
        breakout_price = base_price + 200.0
        breakout_high = breakout_price + 150.0  # Larger range to pass min_breakout_strength
        breakout_low = breakout_price - 50.0
        breakout_volume = 500.0
        dt = base_dt.replace(hour=3, day=3)  # 51 hours = 2 days 3 hours
        candles.append(_candle(breakout_price, breakout_high, breakout_low, breakout_volume, dt))

        signal = strat.evaluate(candles)
        assert signal.action == SignalAction.ENTER_LONG
        assert signal.confidence > 0.0
        assert signal.strategy_id == "breakout_hunter"

    def test_long_breakout_no_volume(self) -> None:
        """No breakout signal when volume confirmation fails."""
        strat = BreakoutHunterStrategy(min_price_volume=2.0)  # High volume threshold

        base_price = 50000.0
        base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candles = _make_candles(51, base_price)

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

    def test_short_breakout_with_volume(self) -> None:
        """Strong bearish breakout below previous low with volume confirmation."""
        strat = BreakoutHunterStrategy(min_price_volume=1.2)

        base_price = 50000.0
        base_dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        candles = _make_candles(51, base_price)

        # Last candle: strong bearish breakout with high volume
        breakout_price = base_price - 200.0
        breakout_high = breakout_price + 20.0
        breakout_low = breakout_price - 100.0
        breakout_volume = 500.0
        dt = base_dt.replace(hour=3, day=3)
        candles.append(_candle(breakout_price, breakout_high, breakout_low, breakout_volume, dt))

        signal = strat.evaluate(candles)
        assert signal.action == SignalAction.ENTER_SHORT
        assert signal.confidence > 0.0
        assert signal.strategy_id == "breakout_hunter"

    def test_hold_when_no_breakout(self) -> None:
        """Hold signal when price doesn't break key levels."""
        strat = BreakoutHunterStrategy()

        # 52 candles with no significant breakout
        base_price = 50000.0
        candles = _make_candles(52, base_price)

        signal = strat.evaluate(candles)
        assert signal.action == SignalAction.HOLD
        assert signal.confidence == 0.0

    def test_insufficient_data(self) -> None:
        """Insufficient data raises appropriate error."""
        strat = BreakoutHunterStrategy()
        candles = [_candle(50000.0, dt=datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc)) for i in range(10)]

        with pytest.raises(InsufficientDataError, match="needs at least"):
            strat.evaluate(candles)

    def test_decision_key_deterministic(self) -> None:
        """Same inputs produce same decision key."""
        strat = BreakoutHunterStrategy()
        candles = _make_candles(52, 50000.0)

        signal1 = strat.evaluate(candles)
        signal2 = strat.evaluate(candles)

        assert signal1.decision_key == signal2.decision_key

    def test_strategy_parameters(self) -> None:
        """Verify strategy parameters are correctly stored."""
        params = {
            "min_price_volume": 1.5,
            "atr_period": 21,
            "volatility_filter": 0.8,
            "min_breakout_strength": 0.005,
        }
        strat = BreakoutHunterStrategy(**params)

        assert strat.params == params
        assert strat.id == "breakout_hunter"
        assert strat.name == "Breakout Hunter (Price+Volume+ATR)"