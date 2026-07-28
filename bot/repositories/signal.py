"""Signal persistence — stores strategy signals for frontend traceability."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any

from supabase import Client

from bot.domain.models import Signal


class SignalRepository(ABC):
    """Abstract interface for signal persistence."""

    @abstractmethod
    def save(self, signal: Signal) -> None:
        """Persist a generated signal."""


class SupabaseSignalRepository(SignalRepository):
    """Saves signals to the ``paper_signals`` Supabase table."""

    def __init__(self, client: Client) -> None:
        self._client = client

    def save(self, signal: Signal) -> None:
        row = _signal_to_row(signal)
        self._client.table("paper_signals").insert(row).execute()


class InMemorySignalRepository(SignalRepository):
    """Keeps signals in memory (useful for testing)."""

    def __init__(self) -> None:
        self._signals: list[Signal] = []

    def save(self, signal: Signal) -> None:
        self._signals.append(signal)

    def all(self) -> list[Signal]:
        return list(self._signals)

    def __len__(self) -> int:
        return len(self._signals)


def _signal_to_row(signal: Signal) -> dict[str, Any]:
    """Convert a ``Signal`` domain object to a Supabase row dict."""
    return {
        "symbol": signal.symbol,
        "timeframe": signal.timeframe.value,
        "strategy_id": signal.strategy_id,
        "action": signal.action.value,
        "confidence": signal.confidence,
        "candle_timestamp": _ts(signal.candle_timestamp),
        "decision_key": signal.decision_key,
        "params": str(signal.params),
        "generated_at": _ts(datetime.now(timezone.utc)),
    }


def _ts(dt: datetime) -> str:
    """Format a datetime as ISO-8601 for Supabase."""
    return dt.isoformat().replace("+00:00", "Z")
