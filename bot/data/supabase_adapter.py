"""Supabase-backed market data provider."""

from __future__ import annotations

from collections.abc import Sequence

from supabase import Client

from bot.config import BotConfig
from bot.data.provider import MarketDataProvider
from bot.data.validation import normalize_candles
from bot.domain.exceptions import DataError, InsufficientDataError
from bot.domain.models import Candle, MarketQuote, Symbol, Timeframe
from bot.domain.utc import ensure_utc, to_decimal, utc_now


class SupabaseMarketData(MarketDataProvider):
    """Reads OHLCV from the ``crypto_historical`` table and current prices
    from ``crypto_data``.
    """

    def __init__(self, client: Client, config: BotConfig) -> None:
        self._client = client
        self._config = config

    # ------------------------------------------------------------------
    # OHLCV
    # ------------------------------------------------------------------

    def fetch_ohlcv(
        self, symbol: Symbol, timeframe: Timeframe, lookback: int = 200
    ) -> Sequence[Candle]:
        """Fetch the most recent *lookback* OHLCV bars from Supabase.

        Queries ``crypto_historical`` ordered by datetime descending, takes
        *lookback* rows, then reverses to chronological order.
        """
        try:
            resp = (
                self._client.table("crypto_historical")
                .select("symbol,timeframe,datetime,open,high,low,close,volume")
                .eq("symbol", symbol)
                .eq("timeframe", timeframe.value)
                .order("datetime", desc=True)
                .limit(lookback)
                .execute()
            )
        except Exception as exc:
            raise DataError(f"Supabase query failed for {symbol} {timeframe.value}: {exc}") from exc

        raw_rows = resp.data if resp.data else []
        if not raw_rows:
            raise InsufficientDataError(f"No OHLCV data for {symbol} {timeframe.value}")

        # Reverse to chronological order
        raw_rows.reverse()

        # Normalise
        candles = normalize_candles(
            raw_rows,
            symbol=symbol,
            timeframe=timeframe,
            lookback=lookback,
        )
        return candles

    # ------------------------------------------------------------------
    # Current quote
    # ------------------------------------------------------------------

    def fetch_quote(self, symbol: Symbol) -> MarketQuote | None:
        """Fetch the latest current price from ``crypto_data``."""
        try:
            resp = (
                self._client.table("crypto_data")
                .select("symbol,current_price,updated_at")
                .eq("symbol", symbol)
                .order("updated_at", desc=True)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            raise DataError(f"Supabase quote query failed for {symbol}: {exc}") from exc

        if not resp.data or len(resp.data) == 0:
            return None

        row = resp.data[0]
        price = to_decimal(row.get("current_price"), "current_price")
        if price is None:
            return None

        updated_at = ensure_utc(_parse_ts(row.get("updated_at"))) or utc_now()

        return MarketQuote(
            symbol=symbol,
            price=price,
            updated_at=updated_at,
        )


def _parse_ts(value: object) -> object:
    """Parse a Supabase timestamp into a datetime if possible."""
    from datetime import datetime

    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
    return value
