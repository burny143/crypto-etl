"""Tests for market data provider interface and Supabase adapter.

Integration tests (marked ``integration``) require credentials and are
skipped by default.  Unit tests use isolated mock objects.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from bot.config import BotConfig
from bot.data.supabase_adapter import SupabaseMarketData
from bot.data.validation import normalize_candles
from bot.domain.exceptions import DataError, InsufficientDataError, StaleDataError
from bot.domain.models import Symbol, Timeframe, MarketQuote
from bot.domain.utc import utc_now


# ===========================================================================
# Unit tests (no network)
# ===========================================================================

class TestSupabaseMarketDataUnit:
    """Tests with a mocked Supabase client."""

    @pytest.fixture
    def config(self) -> BotConfig:
        return BotConfig({
            "symbols": ["BTC-USDT"],
            "timeframes": ["1h"],
        })

    @pytest.fixture
    def mock_client(self) -> MagicMock:
        return MagicMock()

    @pytest.fixture
    def adapter(self, mock_client: MagicMock, config: BotConfig) -> SupabaseMarketData:
        return SupabaseMarketData(mock_client, config)

    def test_fetch_ohlcv_empty_response(self, adapter, mock_client) -> None:
        mock_resp = MagicMock()
        mock_resp.data = []
        (mock_client.table.return_value.select.return_value
         .eq.return_value.eq.return_value.order.return_value
         .limit.return_value.execute.return_value) = mock_resp

        with pytest.raises(InsufficientDataError, match="No OHLCV"):
            adapter.fetch_ohlcv(Symbol("BTC-USDT"), Timeframe.H1, lookback=10)

    def test_fetch_ohlcv_query_error(self, adapter, mock_client) -> None:
        mock_client.table.side_effect = Exception("Network error")

        with pytest.raises(DataError, match="Supabase query failed"):
            adapter.fetch_ohlcv(Symbol("BTC-USDT"), Timeframe.H1, lookback=10)

    def test_fetch_quote_empty(self, adapter, mock_client) -> None:
        mock_resp = MagicMock()
        mock_resp.data = []
        (mock_client.table.return_value.select.return_value
         .eq.return_value.order.return_value.limit.return_value
         .execute.return_value) = mock_resp

        result = adapter.fetch_quote(Symbol("BTC-USDT"))
        assert result is None

    def test_fetch_quote_returns_quote(self, adapter, mock_client) -> None:
        mock_resp = MagicMock()
        mock_resp.data = [{"symbol": "BTC-USDT", "current_price": 50000.0, "updated_at": utc_now().isoformat()}]
        # Mock the full chain: table -> select -> eq -> order -> limit -> execute
        (mock_client.table.return_value.select.return_value
         .eq.return_value.order.return_value.limit.return_value
         .execute.return_value) = mock_resp

        quote = adapter.fetch_quote(Symbol("BTC-USDT"))
        assert quote is not None, (
            f"fetch_quote returned None. Data: {mock_resp.data}")
        assert quote.price == Decimal("50000")
        assert quote.symbol == "BTC-USDT"


# ===========================================================================
# Data quality tests (no network, using fixtures)
# ===========================================================================

class TestDataQuality:
    """Test data quality checks using the malformed fixture."""

    def test_ohlc_inconsistency_detected(self, malformed_ohlcv) -> None:
        """Row 4: high < low should fail."""
        from bot.data.validation import validate_candle
        row = malformed_ohlcv[4]
        with pytest.raises(Exception):
            validate_candle(row)

    def test_future_timestamp_detected(self, malformed_ohlcv) -> None:
        """Row 7: future timestamp should fail."""
        from bot.data.validation import validate_candle
        row = malformed_ohlcv[7]
        with pytest.raises(Exception, match="future"):
            validate_candle(row)

    def test_negative_price_detected(self, malformed_ohlcv) -> None:
        """Row 8: negative open should fail."""
        from bot.data.validation import validate_candle
        row = malformed_ohlcv[8]
        with pytest.raises(Exception, match="positive"):
            validate_candle(row)

    def test_duplicate_timestamp_detected(self) -> None:
        """Two valid candles with same timestamp should raise."""
        from bot.data.validation import validate_candles
        from bot.domain.exceptions import DuplicateTimestampError
        rows = [
            {"symbol": "BTC-USDT", "timeframe": "1h", "datetime": "2026-01-01T00:00:00Z",
             "open": 50000.0, "high": 50050.0, "low": 49950.0, "close": 50020.0, "volume": 100.0},
            {"symbol": "BTC-USDT", "timeframe": "1h", "datetime": "2026-01-01T00:00:00Z",
             "open": 50010.0, "high": 50060.0, "low": 49960.0, "close": 50030.0, "volume": 110.0},
        ]
        with pytest.raises(DuplicateTimestampError):
            validate_candles(rows, lookback=None)
