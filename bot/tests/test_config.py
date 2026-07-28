"""Tests for configuration loading and validation."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import os

import pytest

from bot.config import load_config, BotConfig, DEFAULT_CONFIG_PATH
from bot.domain.exceptions import ConfigError
from bot.domain.models import Timeframe


# ===========================================================================
# load_config
# ===========================================================================

class TestLoadConfig:
    def test_load_default(self) -> None:
        """Load the shipped config.yaml and verify structure."""
        assert DEFAULT_CONFIG_PATH.exists(), (
            f"Default config not found at {DEFAULT_CONFIG_PATH}")
        config = load_config()
        assert len(config.symbols) == 30
        assert Timeframe.H1 in config.timeframes
        assert config.starting_balance == 10000.0
        assert config.lookback_bars == 200
        assert config.poll_interval_seconds == 60
        assert config.price_max_age_seconds == 120

    def test_missing_file(self) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config(Path("/nonexistent/config.yaml"))

    def test_missing_env_var(self) -> None:
        """supabase_url property should raise when env var is unset."""
        config = load_config()
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ConfigError, match="SUPABASE_URL"):
                _ = config.supabase_url

    def test_env_var_property(self) -> None:
        """Should read env vars when set."""
        config = load_config()
        with patch.dict(os.environ, {
            config.supabase_url_var: "https://test.supabase.co",
            config.supabase_key_var: "test-service-key",
        }, clear=False):
            assert config.supabase_url == "https://test.supabase.co"
            assert config.supabase_service_role_key == "test-service-key"


# ===========================================================================
# BotConfig validation
# ===========================================================================

class TestBotConfig:
    def test_empty_symbols(self) -> None:
        with pytest.raises(ConfigError, match="symbols list is empty"):
            BotConfig({"symbols": [], "timeframes": ["1h"]})

    def test_empty_timeframes(self) -> None:
        with pytest.raises(ConfigError, match="timeframes list is empty"):
            BotConfig({"symbols": ["BTC-USDT"], "timeframes": []})

    def test_invalid_timeframe(self) -> None:
        with pytest.raises(ConfigError, match="unsupported timeframe"):
            BotConfig({"symbols": ["BTC-USDT"], "timeframes": ["15m"]})

    def test_symbol_uppercase(self) -> None:
        cfg = BotConfig({"symbols": ["btc-usdt"], "timeframes": ["1h"]})
        assert cfg.symbols[0] == "BTC-USDT"

    def test_defaults_applied(self) -> None:
        cfg = BotConfig({
            "symbols": ["BTC-USDT"],
            "timeframes": ["1h"],
        })
        assert cfg.poll_interval_seconds == 60
        assert cfg.price_max_age_seconds == 120
        assert cfg.starting_balance == 10000.0
        assert cfg.logging_level == "INFO"

    def test_custom_values(self) -> None:
        cfg = BotConfig({
            "symbols": ["BTC-USDT", "ETH-USDT"],
            "timeframes": ["1h", "4h"],
            "poll_interval_seconds": 30,
            "starting_balance": 50000,
            "logging_level": "DEBUG",
        })
        assert cfg.symbols == ["BTC-USDT", "ETH-USDT"]
        assert len(cfg.timeframes) == 2
        assert cfg.poll_interval_seconds == 30
        assert cfg.starting_balance == 50000.0
        assert cfg.logging_level == "DEBUG"
