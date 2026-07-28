"""Domain models for the paper-trading bot.

All monetary values use Decimal. All timestamps are timezone-aware UTC.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import NewType


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

Symbol = NewType("Symbol", str)
"""Trading pair e.g. ``"BTC-USDT"``."""


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class Timeframe(str, enum.Enum):
    """Supported bar intervals."""

    H1 = "1h"
    H4 = "4h"
    D1 = "1d"

    @property
    def minutes(self) -> int:
        return {"1h": 60, "4h": 240, "1d": 1440}[self.value]

    @property
    def seconds(self) -> int:
        return self.minutes * 60


class Side(str, enum.Enum):
    """Trade direction."""

    LONG = "long"
    SHORT = "short"


class OrderStatus(str, enum.Enum):
    """Lifecycle states for a paper order."""

    PENDING = "pending"
    OPEN = "open"
    FILLED = "filled"
    CANCELLED = "cancelled"
    REJECTED = "rejected"


# ---------------------------------------------------------------------------
# Core data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Candle:
    """A single OHLCV bar.

    All price fields are Decimals. The ``datetime`` field represents the bar
    *open* time (matching the ``crypto_historical.datetime`` column).
    """

    symbol: Symbol
    timeframe: Timeframe
    datetime: datetime  # open time, UTC-aware
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    # Computed / enriched by the data provider
    source_timestamp: datetime | None = None  # when the data was fetched

    def __post_init__(self) -> None:
        """Validate OHLC consistency on construction."""
        _validate_ohlc(self.open, self.high, self.low, self.close)

    @property
    def close_time(self) -> datetime:
        """Bar close time = open time + interval."""
        from bot.domain.utc import candle_close_time
        return candle_close_time(self.datetime, self.timeframe.minutes)

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open


# Backward-compatible alias
OHLCVBar = Candle


@dataclass(frozen=True)
class MarketQuote:
    """A current (reference) price quote used for fill modelling.

    Unlike a ``Candle``, a quote is a point-in-time price observation that
    may come from a different table (``crypto_data``) or feed.
    """

    symbol: Symbol
    price: Decimal
    updated_at: datetime  # UTC-aware, when this price was observed
    is_live: bool = True  # False when derived from historical close fallback

    @property
    def age_seconds(self) -> float:
        """Seconds since this quote was recorded."""
        from bot.domain.utc import utc_now
        return (utc_now() - self.updated_at).total_seconds()


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

REQUIRED_CANDLE_FIELDS = ["symbol", "timeframe", "datetime",
                          "open", "high", "low", "close", "volume"]


def _validate_ohlc(open_: Decimal, high: Decimal,
                    low: Decimal, close: Decimal) -> None:
    """Raise ``OHLCInconsistencyError`` if OHLC pricing is impossible."""
    from bot.domain.exceptions import OHLCInconsistencyError
    if high < low:
        raise OHLCInconsistencyError(
            f"high ({high}) < low ({low})")
    if high < open_:
        raise OHLCInconsistencyError(
            f"high ({high}) < open ({open_})")
    if high < close:
        raise OHLCInconsistencyError(
            f"high ({high}) < close ({close})")
    if low > open_:
        raise OHLCInconsistencyError(
            f"low ({low}) > open ({open_})")
    if low > close:
        raise OHLCInconsistencyError(
            f"low ({low}) > close ({close})")
