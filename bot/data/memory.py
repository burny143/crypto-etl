"""In-memory market-data provider for offline use (--in-memory mode).

Returns empty results for all queries. No network or credentials required.
"""

from __future__ import annotations

from collections.abc import Sequence

from bot.data.provider import MarketDataProvider
from bot.domain.models import Candle, MarketQuote, Symbol, Timeframe


class InMemoryMarketData(MarketDataProvider):
    """Market-data provider that always returns no data.

    Used when running with ``--in-memory`` where no Supabase credentials
    are available.  The engine will skip all symbols gracefully (no candles
    to evaluate).
    """

    def fetch_ohlcv(
        self, symbol: Symbol, timeframe: Timeframe, lookback: int = 200
    ) -> Sequence[Candle]:
        return []

    def fetch_quote(self, symbol: Symbol) -> MarketQuote | None:
        return None
