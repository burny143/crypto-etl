"""Abstract interface for market-data providers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from bot.domain.models import Candle, MarketQuote, Symbol, Timeframe


class MarketDataProvider(ABC):
    """Read-only interface to market data sources.

    Implementations fetch from Supabase, CSV files, or other backends.
    All methods return domain objects with validated, UTC-normalized data.
    """

    @abstractmethod
    def fetch_ohlcv(
        self, symbol: Symbol, timeframe: Timeframe, lookback: int = 200
    ) -> Sequence[Candle]:
        """Fetch the most recent *lookback* OHLCV bars.

        Returns bars in chronological order (oldest first).
        Raises ``DataError`` if the source is unreachable.
        Raises ``InsufficientDataError`` if fewer than *lookback* bars
        are available.
        """

    @abstractmethod
    def fetch_quote(self, symbol: Symbol) -> MarketQuote | None:
        """Fetch the latest current/reference price for *symbol*.

        Returns ``None`` when no quote is available.
        """
