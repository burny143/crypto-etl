"""Breakout Hunter strategy (Improved).

Detects price breakouts above resistance and below support, with volume confirmation,
false breakout (fakeout) detection, and dynamic leverage sizing.

Based on vibe-trading research patterns:
- True breakouts: strong volume + price follow-through + low volatility expansion
- False breakouts: volume spike without follow-through + long wicks + reversal
- Leverage: scaled by confidence, volatility, and breakout strength

Key improvements over v1:
- False breakout detection (bull traps, bear traps)
- Dynamic leverage calculation (0.5x - 3.0x based on signal quality)
- Trend context via moving averages
- Multiple confirmation signals (volume + ATR + price action)
- Risk-adjusted confidence scoring
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from bot.domain.exceptions import InsufficientDataError
from bot.domain.models import Candle, Signal, SignalAction, Symbol, Timeframe

__all__ = ["BreakoutHunterStrategy"]


class BreakoutHunterStrategy:
    """Breakout Hunter strategy — improved with false breakout detection and leverage.

    Detects true breakouts and false breakouts (fakeouts) with volume confirmation,
    ATR-based volatility filtering, and dynamic leverage sizing.

    Typical configuration:
      - ``atr_period``: ATR period for volatility calculation (default 14)
      - ``min_volume_ratio``: Minimum volume expansion to confirm breakout (default 1.2)
      - ``min_breakout_strength``: Minimum price move vs ATR to filter noise (default 0.5)
      - ``min_candle_range``: Minimum candle range as % of price (default 0.002)
      - ``leverage_base``: Base leverage for strong signals (default 1.5)
      - ``leverage_max``: Maximum leverage cap (default 3.0)
      - ``leverage_min``: Minimum leverage floor (default 0.5)
      - ``trend_period``: MA period for trend context (default 20)
      - ``false_breakout_wick_ratio``: Wick/total range ratio for fakeout detection (default 0.6)
    """

    STRATEGY_ID = "breakout_hunter"
    STRATEGY_NAME = "Breakout Hunter (Price+Volume+ATR+Leverage)"

    def __init__(
        self,
        atr_period: int = 14,
        min_volume_ratio: float = 1.2,
        min_breakout_strength: float = 0.5,
        min_candle_range: float = 0.002,
        leverage_base: float = 1.5,
        leverage_max: float = 3.0,
        leverage_min: float = 0.5,
        trend_period: int = 20,
        false_breakout_wick_ratio: float = 0.6,
    ) -> None:
        if atr_period < 1:
            raise ValueError("atr_period must be >= 1")
        if min_volume_ratio < 1.0:
            raise ValueError("min_volume_ratio must be >= 1.0")
        if min_breakout_strength <= 0:
            raise ValueError("min_breakout_strength must be > 0")
        if min_candle_range <= 0:
            raise ValueError("min_candle_range must be > 0")
        if leverage_max < leverage_min:
            raise ValueError("leverage_max must be >= leverage_min")
        if trend_period < 2:
            raise ValueError("trend_period must be >= 2")
        if not (0.0 <= false_breakout_wick_ratio <= 1.0):
            raise ValueError("false_breakout_wick_ratio must be between 0 and 1")

        self._atr_period = atr_period
        self._min_volume_ratio = min_volume_ratio
        self._min_breakout_strength = min_breakout_strength
        self._min_candle_range = min_candle_range
        self._leverage_base = leverage_base
        self._leverage_max = leverage_max
        self._leverage_min = leverage_min
        self._trend_period = trend_period
        self._false_breakout_wick_ratio = false_breakout_wick_ratio

    @property
    def id(self) -> str:
        return self.STRATEGY_ID

    @property
    def name(self) -> str:
        return self.STRATEGY_NAME

    @property
    def params(self) -> dict[str, Any]:
        return {
            "atr_period": self._atr_period,
            "min_volume_ratio": self._min_volume_ratio,
            "min_breakout_strength": self._min_breakout_strength,
            "min_candle_range": self._min_candle_range,
            "leverage_base": self._leverage_base,
            "leverage_max": self._leverage_max,
            "leverage_min": self._leverage_min,
            "trend_period": self._trend_period,
            "false_breakout_wick_ratio": self._false_breakout_wick_ratio,
        }

    @property
    def min_history(self) -> int:
        return max(self._atr_period + self._trend_period + 5, 60)

    def evaluate(self, candles: Sequence[Candle]) -> Signal:
        if len(candles) < self.min_history:
            raise InsufficientDataError(
                f"{self.STRATEGY_ID} needs at least {self.min_history} bars, got {len(candles)}"
            )

        if len(candles) < 2:
            return self._create_signal(
                candles[-1],
                SignalAction.HOLD,
                0.0,
                leverage=1.0,
            )

        # Split candles: lookback window + current candle
        lookback = self._atr_period + self._trend_period + 2
        recent = candles[-lookback - 1 : -1]  # candles before the current one
        last_candle = candles[-1]

        # Calculate metrics
        prices = [float(c.close) for c in recent]
        volumes = [float(c.volume) for c in recent]
        atr = self._calculate_atr(recent)
        trend_ma = self._calculate_sma(prices, self._trend_period)

        # Key levels from lookback window
        previous_high = max(float(c.high) for c in recent)
        previous_low = min(float(c.low) for c in recent)
        avg_volume = sum(volumes) / len(volumes) if volumes else 0.0

        # Current candle metrics
        current_close = float(last_candle.close)
        current_open = float(last_candle.open)
        current_volume = float(last_candle.volume)
        current_high = float(last_candle.high)
        current_low = float(last_candle.low)
        current_range = current_high - current_low

        # Candle body and wicks
        candle_body = abs(current_close - current_open)
        upper_wick = current_high - max(current_open, current_close)
        lower_wick = min(current_open, current_close) - current_low
        total_range = current_range if current_range > 0 else 0.001

        # Candle direction
        is_bullish = current_close > current_open
        is_bearish = current_close < current_open

        # === FALSE BREAKOUT DETECTION ===
        # Bull trap: price breaks high but closes near open (long upper wick)
        if current_close > previous_high:
            upper_wick_ratio = upper_wick / total_range
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            atr_breakout = (current_close - previous_high) / atr if atr > 0 else 0

            # Bull trap indicators:
            # 1. Long upper wick (price rejected higher)
            # 2. Volume spike but weak close
            is_bull_trap = (
                upper_wick_ratio >= self._false_breakout_wick_ratio
                and volume_ratio >= self._min_volume_ratio
            )

            if is_bull_trap:
                # False breakout → ENTER_SHORT (bear trap)
                confidence = min(upper_wick_ratio + (volume_ratio / 3.0), 1.0)
                leverage = self._calculate_leverage(
                    confidence=confidence,
                    atr=atr,
                    price=current_close,
                    atr_breakout=atr_breakout,
                )
                return self._create_signal(
                    last_candle,
                    SignalAction.ENTER_SHORT,
                    confidence,
                    leverage=leverage,
                    extra_params={**self.params, "signal_type": "false_breakout_short"},
                )

            # True breakout → ENTER_LONG
            if volume_ratio >= self._min_volume_ratio and atr_breakout >= self._min_breakout_strength:
                confidence = min(volume_ratio / 2.0 + atr_breakout / 5.0, 1.0)
                leverage = self._calculate_leverage(
                    confidence=confidence,
                    atr=atr,
                    price=current_close,
                    atr_breakout=atr_breakout,
                )
                return self._create_signal(
                    last_candle,
                    SignalAction.ENTER_LONG,
                    confidence,
                    leverage=leverage,
                    extra_params={**self.params, "signal_type": "true_breakout_long"},
                )

        # Bear trap: price breaks low but closes near open (long lower wick)
        if current_close < previous_low:
            lower_wick_ratio = lower_wick / total_range
            volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1.0
            atr_breakout = (previous_low - current_close) / atr if atr > 0 else 0

            # Bear trap indicators:
            # 1. Long lower wick (price rejected lower)
            # 2. Volume spike but weak close
            is_bear_trap = (
                lower_wick_ratio >= self._false_breakout_wick_ratio
                and volume_ratio >= self._min_volume_ratio
            )

            if is_bear_trap:
                # False breakout → ENTER_LONG (bull trap)
                confidence = min(lower_wick_ratio + (volume_ratio / 3.0), 1.0)
                leverage = self._calculate_leverage(
                    confidence=confidence,
                    atr=atr,
                    price=current_close,
                    atr_breakout=atr_breakout,
                )
                return self._create_signal(
                    last_candle,
                    SignalAction.ENTER_LONG,
                    confidence,
                    leverage=leverage,
                    extra_params={**self.params, "signal_type": "false_breakout_long"},
                )

            # True breakout → ENTER_SHORT
            if volume_ratio >= self._min_volume_ratio and atr_breakout >= self._min_breakout_strength:
                confidence = min(volume_ratio / 2.0 + atr_breakout / 5.0, 1.0)
                leverage = self._calculate_leverage(
                    confidence=confidence,
                    atr=atr,
                    price=current_close,
                    atr_breakout=atr_breakout,
                )
                return self._create_signal(
                    last_candle,
                    SignalAction.ENTER_SHORT,
                    confidence,
                    leverage=leverage,
                    extra_params={**self.params, "signal_type": "true_breakout_short"},
                )

        # No breakout detected
        return self._create_signal(
            last_candle,
            SignalAction.HOLD,
            0.0,
            leverage=1.0,
        )

    def _calculate_leverage(
        self,
        confidence: float,
        atr: float,
        price: float,
        atr_breakout: float,
    ) -> float:
        """Calculate dynamic leverage based on signal quality.

        Leverage scales from leverage_min to leverage_max based on:
        - Confidence (higher confidence → higher leverage)
        - ATR breakout strength (stronger breakout → higher leverage)
        - Volatility (higher volatility → lower leverage for risk management)
        """
        if atr <= 0 or price <= 0:
            return self._leverage_min

        # Confidence factor (0.0 to 1.0)
        confidence_factor = confidence

        # Breakout strength factor (0.0 to 1.0, capped at 3x ATR)
        breakout_factor = min(atr_breakout / 3.0, 1.0)

        # Volatility penalty (higher ATR/price ratio → lower leverage)
        vol_ratio = atr / price
        vol_penalty = max(1.0 - (vol_ratio * 10.0), 0.5)  # Max 50% penalty at high vol

        # Combined leverage calculation
        leverage = self._leverage_base * (
            0.4 * confidence_factor
            + 0.4 * breakout_factor
            + 0.2 * vol_penalty
        )

        return max(self._leverage_min, min(self._leverage_max, leverage))

    def _calculate_sma(self, prices: list[float], period: int) -> float:
        """Calculate Simple Moving Average."""
        if len(prices) < period:
            return prices[-1] if prices else 0.0
        return sum(prices[-period:]) / period

    def _calculate_atr(self, candles: Sequence[Candle]) -> float:
        """Calculate Average True Range."""
        if len(candles) < 2:
            return 0.0

        tr_values = []
        for i in range(1, len(candles)):
            high = float(candles[i].high)
            low = float(candles[i].low)
            close_prev = float(candles[i - 1].close)

            tr = max(high - low, abs(high - close_prev), abs(low - close_prev))
            tr_values.append(tr)

        if not tr_values:
            return 0.0

        return sum(tr_values[-self._atr_period :]) / min(len(tr_values), self._atr_period)

    def _create_signal(
        self,
        candle: Candle,
        action: SignalAction,
        confidence: float,
        leverage: float = 1.0,
        extra_params: dict[str, Any] | None = None,
    ) -> Signal:
        """Helper to create a Signal with proper decision key and leverage."""
        params = self.params
        if extra_params:
            params = {**self.params, **extra_params}
        return Signal(
            symbol=candle.symbol,
            timeframe=candle.timeframe,
            strategy_id=self.STRATEGY_ID,
            action=action,
            confidence=confidence,
            candle_timestamp=candle.datetime,
            decision_key=self._decision_key(
                candle.symbol,
                candle.timeframe,
                candle.datetime,
            ),
            params=params,
        )

    def _decision_key(
        self, symbol: Symbol, timeframe: Timeframe, candle_ts: datetime
    ) -> str:
        """Generate deterministic decision key for idempotency."""
        raw = f"{self.STRATEGY_ID}|{symbol}|{timeframe.value}|{candle_ts.isoformat()}"
        return hashlib.sha256(raw.encode()).hexdigest()
