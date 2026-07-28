"""Timezone-aware UTC utilities and Decimal conversion."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from bot.domain.exceptions import ValidationError

# Sentinel for tz-aware detection.
_UTC = timezone.utc


# ---------------------------------------------------------------------------
# Current time
# ---------------------------------------------------------------------------


def utc_now() -> datetime:
    """Return the current UTC time, timezone-aware."""
    return datetime.now(_UTC)


# ---------------------------------------------------------------------------
# UTC enforcement
# ---------------------------------------------------------------------------


def ensure_utc(dt: datetime | None) -> datetime | None:
    """Convert a naive or non-UTC datetime to UTC.

    - Naive datetimes are assumed to be UTC and are made aware.
    - Non-UTC aware datetimes are converted to UTC.
    - ``None`` passes through.
    """
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=_UTC)
    return dt.astimezone(_UTC)


def assert_utc(dt: datetime, field: str = "datetime") -> None:
    """Raise ``ValidationError`` if the datetime is not UTC-aware."""
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValidationError(f"{field} must be timezone-aware UTC, got {dt!r}")


# ---------------------------------------------------------------------------
# Decimal conversion
# ---------------------------------------------------------------------------

NumT = int | float | str | Decimal


def to_decimal(value: NumT | None, field: str = "value") -> Decimal | None:
    """Safely convert a numeric value to ``Decimal``.

    Returns ``None`` for ``None`` input.  Raises ``ValidationError`` on
    non-finite or unparseable values.
    """
    if value is None:
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValidationError(f"Cannot convert {field}={value!r} to Decimal: {exc}") from exc
    if not d.is_finite():
        raise ValidationError(f"{field}={value!r} is not a finite number")
    return d


# ---------------------------------------------------------------------------
# Candle time helpers
# ---------------------------------------------------------------------------


def candle_open_time(dt: datetime, interval_minutes: int) -> datetime:
    """Round *dt* down to the nearest bar open time.

    For hourly bars: truncates minutes/seconds/microseconds.
    For daily bars: truncates to the start of the day.
    """
    dt = ensure_utc(dt)
    mins = int(interval_minutes)
    if mins >= 1440:  # daily
        return dt.replace(hour=0, minute=0, second=0, microsecond=0)
    # Hourly / intraday
    total_seconds = mins * 60
    ts = dt.timestamp()
    truncated = int(ts // total_seconds) * total_seconds
    return datetime.fromtimestamp(truncated, tz=_UTC)


def candle_close_time(open_dt: datetime, interval_minutes: int) -> datetime:
    """Compute the close time for a candle that opened at *open_dt*."""
    return candle_open_time(open_dt, interval_minutes) + timedelta(minutes=interval_minutes)


def is_completed_candle(
    open_dt: datetime, interval_minutes: int, now: datetime | None = None, grace_seconds: int = 30
) -> bool:
    """Return ``True`` if a candle with the given *open_dt* is complete.

    A candle is complete when its close time + grace period has passed.
    """
    now = ensure_utc(now) or utc_now()
    close = candle_close_time(open_dt, interval_minutes)
    return now >= close + timedelta(seconds=grace_seconds)
