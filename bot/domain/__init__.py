# Domain models for the paper-trading bot.
from bot.domain.exceptions import (
    BotError,
    ChronologicalOrderError,
    ConfigError,
    DataError,
    DuplicateTimestampError,
    FutureTimestampError,
    InsufficientDataError,
    MissingFieldError,
    OHLCInconsistencyError,
    StaleDataError,
    ValidationError,
)
from bot.domain.models import (
    REQUIRED_CANDLE_FIELDS,
    Candle,
    MarketQuote,
    OHLCVBar,
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

__all__ = [
    # Models
    "Candle",
    "MarketQuote",
    "OHLCVBar",
    "Symbol",
    "Timeframe",
    "Side",
    "OrderStatus",
    "REQUIRED_CANDLE_FIELDS",
    # Exceptions
    "BotError",
    "ConfigError",
    "DataError",
    "ValidationError",
    "StaleDataError",
    "InsufficientDataError",
    "MissingFieldError",
    "OHLCInconsistencyError",
    "DuplicateTimestampError",
    "FutureTimestampError",
    "ChronologicalOrderError",
    # Utilities
    "utc_now",
    "ensure_utc",
    "assert_utc",
    "to_decimal",
    "candle_open_time",
    "candle_close_time",
    "is_completed_candle",
]
