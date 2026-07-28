"""Shared test fixtures for bot tests."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"


@pytest.fixture(scope="session")
def sample_ohlcv() -> list[dict[str, Any]]:
    """Load the canonical sample OHLCV fixture."""
    path = FIXTURES_DIR / "ohlcv_sample.json"
    if not path.exists():
        # Fallback: return minimal valid data
        return _minimal_ohlcv()
    with open(path) as fh:
        return json.load(fh)


@pytest.fixture(scope="session")
def malformed_ohlcv() -> list[dict[str, Any]]:
    """Load the malformed OHLCV fixture for edge-case tests."""
    path = FIXTURES_DIR / "ohlcv_malformed.json"
    if not path.exists():
        return _minimal_malformed()
    with open(path) as fh:
        return json.load(fh)


def _minimal_ohlcv() -> list[dict[str, Any]]:
    """Generate 10 bars of synthetic valid OHLCV data."""
    from datetime import datetime, timezone

    bars = []
    for i in range(10):
        dt = datetime(2026, 1, 1, i, 0, 0, tzinfo=timezone.utc)
        base = 50000 + i * 10
        bars.append(
            {
                "symbol": "BTC-USDT",
                "timeframe": "1h",
                "datetime": dt.isoformat(),
                "open": base,
                "high": base + 50,
                "low": base - 50,
                "close": base + 10,
                "volume": 100.5 + i,
            }
        )
    return bars


def _minimal_malformed() -> list[dict[str, Any]]:
    """Generate minimal edge-case data."""
    from datetime import datetime, timezone

    return [
        # Row 0: missing field
        {
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "datetime": datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
            "open": 50000,
            "high": 50050,
            "low": 49950,
            # "close" missing
            "volume": 100,
        },
        # Row 1: OHLC inconsistency
        {
            "symbol": "BTC-USDT",
            "timeframe": "1h",
            "datetime": datetime(2026, 1, 1, 1, 0, 0, tzinfo=timezone.utc),
            "open": 50000,
            "high": 50500,
            "low": 49900,
            "close": None,  # will be coerced to null
            "volume": 100,
        },
        # Row 2: future timestamp
        {
            "symbol": "ETH-USDT",
            "timeframe": "1h",
            "datetime": "2099-01-01T00:00:00Z",
            "open": 3000,
            "high": 3050,
            "low": 2950,
            "close": 3020,
            "volume": 500,
        },
        # Row 3: negative price
        {
            "symbol": "XRP-USDT",
            "timeframe": "1h",
            "datetime": "2026-01-01T02:00:00Z",
            "open": -1,
            "high": 1,
            "low": -2,
            "close": 0.5,
            "volume": 1000,
        },
        # Row 4: duplicate of row 3
        {
            "symbol": "XRP-USDT",
            "timeframe": "1h",
            "datetime": "2026-01-01T02:00:00Z",
            "open": -1,
            "high": 1,
            "low": -2,
            "close": 0.5,
            "volume": 1000,
        },
    ]
