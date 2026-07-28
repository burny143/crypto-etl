"""Configuration loader for the paper-trading bot.

Loads from ``config.yaml`` (module-relative), overlays with environment
variables, and validates all required values.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import yaml

from bot.domain.exceptions import ConfigError
from bot.domain.models import Symbol, Timeframe


# ---------------------------------------------------------------------------
# Path resolution
# ---------------------------------------------------------------------------

def _module_dir() -> Path:
    """Absolute path of the ``bot/`` package directory."""
    return Path(__file__).resolve().parent


DEFAULT_CONFIG_PATH = _module_dir() / "config.yaml"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------

class BotConfig:
    """Validated, frozen-like configuration container."""

    def __init__(self, raw: dict[str, Any]) -> None:
        # Symbols (list[str])
        raw_symbols: list[str] = raw.get("symbols", [])
        if not raw_symbols:
            raise ConfigError("config: symbols list is empty")
        self.symbols: list[Symbol] = [Symbol(s.upper()) for s in raw_symbols]

        # Timeframes (list[Timeframe])
        raw_tfs: list[str] = raw.get("timeframes", [])
        if not raw_tfs:
            raise ConfigError("config: timeframes list is empty")
        self.timeframes: list[Timeframe] = []
        for tf in raw_tfs:
            try:
                self.timeframes.append(Timeframe(tf.lower()))
            except ValueError:
                raise ConfigError(
                    f"config: unsupported timeframe {tf!r} (valid: 1h, 4h, 1d)")

        # Numeric settings
        self.poll_interval_seconds = int(self._require(
            raw, "poll_interval_seconds", 60))
        self.price_max_age_seconds = int(self._require(
            raw, "price_max_age_seconds", 120))
        self.candle_grace_seconds = int(self._require(
            raw, "candle_grace_seconds", 30))
        self.lookback_bars = int(self._require(
            raw, "lookback_bars", 200))
        self.starting_balance = float(self._require(
            raw, "starting_balance", 10000.0))
        self.logging_level = str(self._require(
            raw, "logging_level", "INFO")).upper()

        # Env variable name mappings
        env_section = raw.get("env", {})
        self.supabase_url_var = str(env_section.get(
            "supabase_url", "SUPABASE_URL"))
        self.supabase_key_var = str(env_section.get(
            "supabase_service_role_key", "SUPABASE_SERVICE_ROLE_KEY"))

    @staticmethod
    def _require(raw: dict, key: str, default: Any = None) -> Any:
        val = raw.get(key, default)
        if val is None:
            raise ConfigError(f"config: missing required key '{key}'")
        return val

    @property
    def supabase_url(self) -> str:
        url = os.environ.get(self.supabase_url_var)
        if not url:
            raise ConfigError(
                f"Environment variable {self.supabase_url_var!r} is not set. "
                f"Set it before running the bot.")
        return url

    @property
    def supabase_service_role_key(self) -> str:
        key = os.environ.get(self.supabase_key_var)
        if not key:
            raise ConfigError(
                f"Environment variable {self.supabase_key_var!r} is not set. "
                f"Set it before running the bot.")
        return key

    def __repr__(self) -> str:
        return (
            f"BotConfig(symbols={len(self.symbols)}, "
            f"timeframes={[t.value for t in self.timeframes]}, "
            f"lookback={self.lookback_bars})"
        )


def load_config(path: Path | None = None) -> BotConfig:
    """Load and validate the configuration YAML from *path*.

    If *path* is ``None`` the default location (``bot/config.yaml``) is used.
    """
    if path is None:
        path = DEFAULT_CONFIG_PATH

    if not path.exists():
        raise ConfigError(
            f"Configuration file not found: {path}")

    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except Exception as exc:
        raise ConfigError(
            f"Failed to load config {path}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError(
            f"Config file {path} must contain a YAML mapping (dict)")

    return BotConfig(raw)
