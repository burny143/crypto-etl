# Domain models for the paper-trading bot.
from bot.domain.models import (
    Candle,
    MarketQuote,
    Symbol,
    Timeframe,
    Side,
    OrderStatus,
    OHLCVBar,
    REQUIRED_CANDLE_FIELDS,
)
from bot.domain.exceptions import (
    BotError,
    ConfigError,
    DataError,
    ValidationError,
    StaleDataError,
    InsufficientDataError,
    MissingFieldError,
    OHLCInconsistencyError,
    DuplicateTimestampError,
    FutureTimestampError,
    ChronologicalOrderError,
)
from bot.domain.utc import (
    utc_now,
    ensure_utc,
    assert_utc,
    to_decimal,
    candle_open_time,
    candle_close_time,
    is_completed_candle,
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
