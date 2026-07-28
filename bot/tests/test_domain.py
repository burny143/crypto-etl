"""Tests for domain models and utilities."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bot.domain.exceptions import (
    OHLCInconsistencyError,
    ValidationError,
)
from bot.domain.models import (
    Candle,
    MarketQuote,
    OrderStatus,
    Side,
    Symbol,
    Timeframe,
)
from bot.domain.utc import (
    assert_utc,
    candle_close_time,
    candle_open_time,
    ensure_utc,
    is_completed_candle,
    to_decimal,
    utc_now,
)

# ===========================================================================
# Timeframe
# ===========================================================================


class TestTimeframe:
    def test_minutes(self) -> None:
        assert Timeframe.H1.minutes == 60
        assert Timeframe.H4.minutes == 240
        assert Timeframe.D1.minutes == 1440

    def test_seconds(self) -> None:
        assert Timeframe.H1.seconds == 3600
        assert Timeframe.D1.seconds == 86400

    def test_values(self) -> None:
        assert Timeframe.H1.value == "1h"
        assert Timeframe.H4.value == "4h"
        assert Timeframe.D1.value == "1d"


# ===========================================================================
# Candle
# ===========================================================================


class TestCandle:
    def test_valid_candle(self) -> None:
        dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        c = Candle(
            symbol=Symbol("BTC-USDT"),
            timeframe=Timeframe.H1,
            datetime=dt,
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100"),
        )
        assert c.symbol == "BTC-USDT"
        assert c.is_bullish is True

    def test_bearish_candle(self) -> None:
        dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        c = Candle(
            symbol=Symbol("BTC-USDT"),
            timeframe=Timeframe.H1,
            datetime=dt,
            open=Decimal("50100"),
            high=Decimal("50150"),
            low=Decimal("49800"),
            close=Decimal("49900"),
            volume=Decimal("100"),
        )
        assert c.is_bullish is False

    def test_ohlc_inconsistency_high_lt_low(self) -> None:
        dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        with pytest.raises(OHLCInconsistencyError, match="high.*low"):
            Candle(
                symbol=Symbol("BTC-USDT"),
                timeframe=Timeframe.H1,
                datetime=dt,
                open=Decimal("50000"),
                high=Decimal("49800"),  # < low
                low=Decimal("49900"),
                close=Decimal("50050"),
                volume=Decimal("100"),
            )

    def test_close_time(self) -> None:
        dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        c = Candle(
            symbol=Symbol("BTC-USDT"),
            timeframe=Timeframe.H1,
            datetime=dt,
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100"),
        )
        assert c.close_time == datetime(2026, 1, 1, 1, 0, 0, tzinfo=timezone.utc)

    def test_repr(self) -> None:
        dt = datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        c = Candle(
            symbol=Symbol("BTC-USDT"),
            timeframe=Timeframe.H1,
            datetime=dt,
            open=Decimal("50000"),
            high=Decimal("50100"),
            low=Decimal("49900"),
            close=Decimal("50050"),
            volume=Decimal("100"),
        )
        # Frozen dataclass repr
        assert "Candle" in repr(c)


# ===========================================================================
# MarketQuote
# ===========================================================================


class TestMarketQuote:
    def test_age_seconds_zero(self) -> None:
        now = utc_now()
        q = MarketQuote(
            symbol=Symbol("BTC-USDT"),
            price=Decimal("50000"),
            updated_at=now,
        )
        assert q.age_seconds < 1.0

    def test_age_seconds_positive(self) -> None:
        from datetime import timedelta

        old = utc_now() - timedelta(seconds=60)
        q = MarketQuote(
            symbol=Symbol("ETH-USDT"),
            price=Decimal("3000"),
            updated_at=old,
        )
        assert q.age_seconds >= 59.0

    def test_not_live(self) -> None:
        now = utc_now()
        q = MarketQuote(
            symbol=Symbol("BTC-USDT"),
            price=Decimal("50000"),
            updated_at=now,
            is_live=False,
        )
        assert q.is_live is False


# ===========================================================================
# Side
# ===========================================================================


class TestSide:
    def test_values(self) -> None:
        assert Side.LONG.value == "long"
        assert Side.SHORT.value == "short"


# ===========================================================================
# OrderStatus
# ===========================================================================


class TestOrderStatus:
    def test_values(self) -> None:
        assert OrderStatus.PENDING.value == "pending"
        assert OrderStatus.FILLED.value == "filled"
        assert OrderStatus.REJECTED.value == "rejected"


# ===========================================================================
# UTC utilities
# ===========================================================================


class TestEnsureUTC:
    def test_naive_dt(self) -> None:
        naive = datetime(2026, 1, 1, 12, 0, 0)
        aware = ensure_utc(naive)
        assert aware.tzinfo is not None
        assert aware.utcoffset() == timezone.utc.utcoffset(naive)
        assert aware.hour == 12  # no shift

    def test_aware_utc(self) -> None:
        dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert ensure_utc(dt) is dt  # same object

    def test_aware_non_utc(self) -> None:
        from datetime import timedelta

        est = timezone(timedelta(hours=-5))
        dt = datetime(2026, 1, 1, 7, 0, 0, tzinfo=est)
        converted = ensure_utc(dt)
        assert converted.hour == 12
        assert converted.tzinfo == timezone.utc

    def test_none(self) -> None:
        assert ensure_utc(None) is None


class TestAssertUTC:
    def test_passes_utc(self) -> None:
        assert_utc(datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc))

    def test_fails_naive(self) -> None:
        with pytest.raises(ValidationError, match="timezone-aware"):
            assert_utc(datetime(2026, 1, 1, 0, 0, 0))


class TestToDecimal:
    def test_int(self) -> None:
        assert to_decimal(42) == Decimal("42")

    def test_float(self) -> None:
        assert to_decimal(3.14) == Decimal("3.14")

    def test_str(self) -> None:
        assert to_decimal("123.45") == Decimal("123.45")

    def test_none(self) -> None:
        assert to_decimal(None) is None

    def test_infinity(self) -> None:
        with pytest.raises(ValidationError, match="not a finite"):
            to_decimal(float("inf"))

    def test_nan(self) -> None:
        with pytest.raises(ValidationError, match="not a finite"):
            to_decimal(float("nan"))

    def test_unparseable(self) -> None:
        with pytest.raises(ValidationError, match="Cannot convert"):
            to_decimal("not_a_number")


class TestCandleTimeHelpers:
    def test_candle_open_time_hourly(self) -> None:
        dt = datetime(2026, 1, 1, 12, 34, 56, tzinfo=timezone.utc)
        opened = candle_open_time(dt, 60)
        assert opened.hour == 12
        assert opened.minute == 0
        assert opened.second == 0

    def test_candle_open_time_daily(self) -> None:
        dt = datetime(2026, 1, 5, 12, 34, 56, tzinfo=timezone.utc)
        opened = candle_open_time(dt, 1440)
        assert opened.day == 5
        assert opened.hour == 0
        assert opened.minute == 0

    def test_candle_close_time(self) -> None:
        dt = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        close = candle_close_time(dt, 60)
        assert close.hour == 13
        assert close.minute == 0

    def test_is_completed_candle_past(self) -> None:
        dt = datetime(2020, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        assert is_completed_candle(dt, 60) is True

    def test_is_completed_candle_recent(self) -> None:
        now = utc_now()
        # A candle that just closed (within grace)
        recent_open = now.replace(second=0, microsecond=0)
        from datetime import timedelta

        recent_open = recent_open - timedelta(hours=1, seconds=15)
        assert is_completed_candle(recent_open, 60, now=now, grace_seconds=30) is True

    def test_is_not_completed(self) -> None:
        now = utc_now()
        # Current candle still forming
        forming = now.replace(second=0, microsecond=0)
        assert is_completed_candle(forming, 60, now=now, grace_seconds=30) is False
