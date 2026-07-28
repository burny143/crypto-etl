"""Typed exceptions for the paper-trading bot."""


class BotError(Exception):
    """Base for all bot-domain errors."""


class ConfigError(BotError):
    """Configuration loading or validation failure."""


# ── Data errors ──────────────────────────────────────────────────────────

class DataError(BotError):
    """Base for data-layer errors."""


class ValidationError(DataError):
    """Data failed validation rules."""


class StaleDataError(DataError):
    """Data is too old to be considered fresh."""


class InsufficientDataError(DataError):
    """Not enough bars to satisfy the lookback requirement."""


class MissingFieldError(ValidationError):
    """A required field is missing or None."""


class OHLCInconsistencyError(ValidationError):
    """OHLC prices violate high >= open/close >= low."""


class DuplicateTimestampError(ValidationError):
    """Two bars share the same (symbol, timeframe, datetime)."""


class FutureTimestampError(ValidationError):
    """A bar's datetime is in the future."""


class ChronologicalOrderError(ValidationError):
    """Bars are not sorted in ascending chronological order."""
