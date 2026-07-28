"""OHLCV validation and normalization utilities."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from decimal import Decimal
from typing import Any

from bot.domain.exceptions import (
    DuplicateTimestampError,
    FutureTimestampError,
    InsufficientDataError,
    MissingFieldError,
    OHLCInconsistencyError,
    StaleDataError,
    ValidationError,
)
from bot.domain.models import (
    Candle,
    MarketQuote,
    Symbol,
    Timeframe,
)
from bot.domain.utc import ensure_utc, to_decimal, utc_now

# ---------------------------------------------------------------------------
# Individual candle validation
# ---------------------------------------------------------------------------


def validate_candle(raw: dict[str, Any]) -> Candle:
    """Parse and validate a raw dictionary as a ``Candle``.

    Performs: required-field check, non-null numerics, positive prices,
    OHLC consistency, UTC normalisation, and Decimal conversion.
    """
    # Required fields
    for field in ("symbol", "timeframe", "datetime", "open", "high", "low", "close", "volume"):
        if field not in raw or raw[field] is None:
            raise MissingFieldError(f"Candle missing required field: {field!r}")

    symbol = Symbol(str(raw["symbol"]).upper())

    tf_raw = str(raw["timeframe"]).lower()
    try:
        timeframe = Timeframe(tf_raw)
    except ValueError:
        raise ValidationError(f"Unsupported timeframe {tf_raw!r} (must be 1h, 4h, or 1d)") from None

    dt_raw = raw["datetime"]
    dt: datetime | None = None
    if isinstance(dt_raw, datetime):
        dt = ensure_utc(dt_raw)
    elif isinstance(dt_raw, str):
        dt = ensure_utc(datetime.fromisoformat(dt_raw.replace("Z", "+00:00")))
    else:
        raise ValidationError(f"datetime must be a string or datetime, got {type(dt_raw).__name__}")
    if dt is None:
        raise ValidationError("datetime could not be parsed")

    # Future check
    now = utc_now()
    if dt > now:
        raise FutureTimestampError(
            f"Candle datetime {dt.isoformat()} is in the future (now={now.isoformat()})"
        )

    # Convert to Decimal, catching non-finite
    def _dec(val: Any, field_name: str) -> Decimal:
        d = to_decimal(val, field_name)
        if d is None:
            raise MissingFieldError(f"Candle field '{field_name}' is null")
        return d

    open_ = _dec(raw["open"], "open")
    high = _dec(raw["high"], "high")
    low = _dec(raw["low"], "low")
    close = _dec(raw["close"], "close")
    volume = _dec(raw["volume"], "volume")

    # Positive price check
    for name, val in [("open", open_), ("high", high), ("low", low), ("close", close)]:
        if val <= 0:
            raise ValidationError(f"Price {name}={val} must be positive")

    # Volume can be 0 but not negative
    if volume < 0:
        raise ValidationError(f"volume={volume} cannot be negative")

    # OHLC consistency
    if high < low:
        raise OHLCInconsistencyError(f"high ({high}) < low ({low})")
    if high < open_:
        raise OHLCInconsistencyError(f"high ({high}) < open ({open_})")
    if high < close:
        raise OHLCInconsistencyError(f"high ({high}) < close ({close})")
    if low > open_:
        raise OHLCInconsistencyError(f"low ({low}) > open ({open_})")
    if low > close:
        raise OHLCInconsistencyError(f"low ({low}) > close ({close})")

    return Candle(
        symbol=symbol,
        timeframe=timeframe,
        datetime=dt,
        open=open_,
        high=high,
        low=low,
        close=close,
        volume=volume,
        source_timestamp=now,
    )


# ---------------------------------------------------------------------------
# Batch validation
# ---------------------------------------------------------------------------


def validate_candles(
    raw_rows: Sequence[dict[str, Any]],
    symbol: Symbol | None = None,
    timeframe: Timeframe | None = None,
    lookback: int | None = None,
) -> list[Candle]:
    """Parse, validate, and normalise a sequence of raw OHLCV rows.

    Checks:
      - Sufficient data (lookback)
      - Chronological order
      - No duplicate timestamps
      - Individual candle validation

    Returns a ``list[Candle]`` sorted ascending by datetime.
    """
    if not raw_rows:
        if lookback and lookback > 0:
            raise InsufficientDataError(f"Expected at least {lookback} bars, got 0")
        return []

    candles: list[Candle] = []
    for i, row in enumerate(raw_rows):
        try:
            candle = validate_candle(row)
        except Exception as exc:
            raise ValidationError(
                f"Row {i} ({row.get('symbol', '?')}, {row.get('datetime', '?')}): {exc}"
            ) from exc
        candles.append(candle)

    # Filter to matching symbol/timeframe if specified
    if symbol:
        candles = [c for c in candles if c.symbol == symbol]
    if timeframe:
        candles = [c for c in candles if c.timeframe == timeframe]

    # Sort chronological (defensive)
    candles.sort(key=lambda c: c.datetime)

    # Duplicate timestamp check
    seen: set[tuple[str, str, datetime]] = set()
    for c in candles:
        key = (c.symbol, c.timeframe.value, c.datetime)
        if key in seen:
            raise DuplicateTimestampError(
                f"Duplicate bar: {c.symbol} {c.timeframe.value} {c.datetime.isoformat()}"
            )
        seen.add(key)

    # Warm-up / lookback
    if lookback is not None and len(candles) < lookback:
        raise InsufficientDataError(
            f"Expected at least {lookback} bars for warm-up, got {len(candles)}"
        )

    return candles


# ---------------------------------------------------------------------------
# Normalization (converts raw DB rows to validated Candle list)
# ---------------------------------------------------------------------------


def normalize_candles(
    rows: Sequence[dict[str, Any]],
    symbol: Symbol | None = None,
    timeframe: Timeframe | None = None,
    lookback: int | None = None,
) -> list[Candle]:
    """Convenience: validate and normalise raw DB rows in one call."""
    return validate_candles(rows, symbol, timeframe, lookback)


# ---------------------------------------------------------------------------
# Freshness checks
# ---------------------------------------------------------------------------


def check_freshness(quote: MarketQuote, max_age_seconds: int) -> None:
    """Raise ``StaleDataError`` if the quote is older than *max_age_seconds*."""
    age = quote.age_seconds
    if age > max_age_seconds:
        raise StaleDataError(f"Quote for {quote.symbol} is {age:.0f}s old (max {max_age_seconds}s)")


# ---------------------------------------------------------------------------
# Warm-up check
# ---------------------------------------------------------------------------


def check_warmup(candles: Sequence[Candle], lookback_bars: int) -> None:
    """Raise ``InsufficientDataError`` if there aren't enough bars."""
    if len(candles) < lookback_bars:
        raise InsufficientDataError(f"Need {lookback_bars} bars for warm-up, have {len(candles)}")
