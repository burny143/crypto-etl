"""Tests for OHLCV validation and data quality checks."""

from __future__ import annotations

from decimal import Decimal

import pytest

from bot.data.validation import (
    check_freshness,
    check_warmup,
    normalize_candles,
    validate_candle,
    validate_candles,
)
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
)
from bot.domain.utc import utc_now

# ===========================================================================
# validate_candle
# ===========================================================================


class TestValidateCandle:
    def test_valid_candle(self) -> None:
        row = {
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "datetime": "2026-01-01T00:00:00Z",
            "open": 50000.0,
            "high": 50100.0,
            "low": 49900.0,
            "close": 50050.0,
            "volume": 100.0,
        }
        c = validate_candle(row)
        assert isinstance(c, Candle)
        assert c.symbol == "BTC-USDT"
        assert c.close == Decimal("50050")

    def test_descending_response_normalization(self) -> None:
        """Rows coming in descending order should still produce valid candles."""
        rows = [
            {
                "symbol": "BTC-USDT",
                "timeframe": "1h",
                "datetime": "2026-01-01T02:00:00Z",
                "open": 50100.0,
                "high": 50150.0,
                "low": 50080.0,
                "close": 50120.0,
                "volume": 100.0,
            },
            {
                "symbol": "BTC-USDT",
                "timeframe": "1h",
                "datetime": "2026-01-01T01:00:00Z",
                "open": 50050.0,
                "high": 50100.0,
                "low": 50030.0,
                "close": 50090.0,
                "volume": 100.0,
            },
            {
                "symbol": "BTC-USDT",
                "timeframe": "1h",
                "datetime": "2026-01-01T00:00:00Z",
                "open": 50000.0,
                "high": 50050.0,
                "low": 49950.0,
                "close": 50040.0,
                "volume": 100.0,
            },
        ]
        candles = validate_candles(rows, lookback=None)
        # Should be in chronological order after normalization
        for i in range(1, len(candles)):
            assert candles[i].datetime > candles[i - 1].datetime

    def test_missing_close_field(self) -> None:
        row = {
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "datetime": "2026-01-01T00:00:00Z",
            "open": 50000.0,
            "high": 50050.0,
            "low": 49950.0,
            # close missing
            "volume": 100.0,
        }
        with pytest.raises(MissingFieldError, match="close"):
            validate_candle(row)

    def test_null_close(self) -> None:
        row = {
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "datetime": "2026-01-01T00:00:00Z",
            "open": 50000.0,
            "high": 50050.0,
            "low": 49950.0,
            "close": None,
            "volume": 100.0,
        }
        with pytest.raises(MissingFieldError, match="close"):
            validate_candle(row)

    def test_malformed_numeric(self) -> None:
        row = {
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "datetime": "2026-01-01T00:00:00Z",
            "open": "not_a_number",
            "high": 50050.0,
            "low": 49950.0,
            "close": 50000.0,
            "volume": 100.0,
        }
        with pytest.raises(ValidationError, match="Cannot convert"):
            validate_candle(row)

    def test_infinity_price(self) -> None:
        row = {
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "datetime": "2026-01-01T00:00:00Z",
            "open": float("inf"),
            "high": 50050.0,
            "low": 49950.0,
            "close": 50000.0,
            "volume": 100.0,
        }
        with pytest.raises(ValidationError, match="not a finite"):
            validate_candle(row)

    def test_ohlc_inconsistency(self) -> None:
        row = {
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "datetime": "2026-01-01T00:00:00Z",
            "open": 50000.0,
            "high": 49800.0,  # lower than low
            "low": 49900.0,
            "close": 50050.0,
            "volume": 100.0,
        }
        with pytest.raises(OHLCInconsistencyError):
            validate_candle(row)

    def test_negative_price(self) -> None:
        row = {
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "datetime": "2026-01-01T00:00:00Z",
            "open": -50000.0,
            "high": 50050.0,
            "low": -50100.0,
            "close": 50000.0,
            "volume": 100.0,
        }
        with pytest.raises(ValidationError, match="positive"):
            validate_candle(row)

    def test_future_timestamp(self) -> None:
        from datetime import timedelta

        future = utc_now() + timedelta(days=365)
        row = {
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "datetime": future.isoformat(),
            "open": 50000.0,
            "high": 50050.0,
            "low": 49950.0,
            "close": 50000.0,
            "volume": 100.0,
        }
        with pytest.raises(FutureTimestampError):
            validate_candle(row)

    def test_unsupported_timeframe(self) -> None:
        row = {
            "symbol": "BTC-USDT",
            "timeframe": "15m",
            "datetime": "2026-01-01T00:00:00Z",
            "open": 50000.0,
            "high": 50050.0,
            "low": 49950.0,
            "close": 50000.0,
            "volume": 100.0,
        }
        with pytest.raises(ValidationError, match="Unsupported timeframe"):
            validate_candle(row)


# ===========================================================================
# validate_candles (batch)
# ===========================================================================


class TestValidateCandles:
    def test_valid_batch(self, sample_ohlcv) -> None:
        candles = validate_candles(sample_ohlcv, lookback=5)
        assert len(candles) == 10
        assert all(isinstance(c, Candle) for c in candles)

    def test_duplicate_timestamps(self) -> None:
        rows = [
            {
                "symbol": "BTC-USDT",
                "timeframe": "1h",
                "datetime": "2026-01-01T00:00:00Z",
                "open": 50000.0,
                "high": 50050.0,
                "low": 49950.0,
                "close": 50000.0,
                "volume": 100.0,
            },
            {
                "symbol": "BTC-USDT",
                "timeframe": "1h",
                "datetime": "2026-01-01T00:00:00Z",
                "open": 50100.0,
                "high": 50150.0,
                "low": 50050.0,
                "close": 50100.0,
                "volume": 110.0,
            },
        ]
        with pytest.raises(DuplicateTimestampError):
            validate_candles(rows, lookback=None)

    def test_insufficient_lookback(self, sample_ohlcv) -> None:
        with pytest.raises(InsufficientDataError, match="warm-up"):
            validate_candles(sample_ohlcv, lookback=999)

    def test_empty_with_lookback(self) -> None:
        with pytest.raises(InsufficientDataError):
            validate_candles([], lookback=1)

    def test_empty_no_lookback(self) -> None:
        assert validate_candles([], lookback=None) == []

    def test_missing_fields_in_batch(self) -> None:
        rows = [
            {
                "symbol": "BTC-USDT",
                "timeframe": "1h",
                "datetime": "2026-01-01T00:00:00Z",
                "open": 50000.0,
                "high": 50050.0,
                "low": 49950.0,
                "close": 50000.0,
                "volume": 100.0,
            },
            {
                "symbol": "ETH-USDT",
                "timeframe": "1h",
                # datetime missing
                "open": 3000.0,
                "high": 3050.0,
                "low": 2950.0,
                "close": 3020.0,
                "volume": 500.0,
            },
        ]
        with pytest.raises(ValidationError, match="datetime"):
            validate_candles(rows, lookback=None)


# ===========================================================================
# check_freshness
# ===========================================================================


class TestCheckFreshness:
    def test_fresh_quote(self) -> None:
        q = MarketQuote(
            symbol=Symbol("BTC-USDT"),
            price=Decimal("50000"),
            updated_at=utc_now(),
        )
        # Should not raise
        check_freshness(q, max_age_seconds=120)

    def test_stale_quote(self) -> None:
        from datetime import timedelta

        old = utc_now() - timedelta(seconds=300)
        q = MarketQuote(
            symbol=Symbol("BTC-USDT"),
            price=Decimal("50000"),
            updated_at=old,
        )
        with pytest.raises(StaleDataError, match="old"):
            check_freshness(q, max_age_seconds=60)


# ===========================================================================
# check_warmup
# ===========================================================================


class TestCheckWarmup:
    def test_sufficient_data(self, sample_ohlcv) -> None:
        candles = validate_candles(sample_ohlcv, lookback=None)
        check_warmup(candles, lookback_bars=5)  # should not raise

    def test_insufficient_data(self, sample_ohlcv) -> None:
        candles = validate_candles(sample_ohlcv, lookback=None)
        with pytest.raises(InsufficientDataError, match="Need"):
            check_warmup(candles, lookback_bars=999)


# ===========================================================================
# normalize_candles (convenience wrapper)
# ===========================================================================


class TestNormalizeCandles:
    def test_basic(self, sample_ohlcv) -> None:
        candles = normalize_candles(sample_ohlcv, lookback=5)
        assert len(candles) == 10
        assert all(c.symbol == "BTC-USDT" for c in candles)

    def test_symbol_filter(self, sample_ohlcv) -> None:
        candles = normalize_candles(sample_ohlcv, symbol=Symbol("BTC-USDT"), lookback=5)
        assert len(candles) == 10
        assert all(c.symbol == "BTC-USDT" for c in candles)
