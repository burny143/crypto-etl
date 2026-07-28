"""Abstract strategy interface and supporting types.

All strategies inherit from ``AbstractStrategy`` and implement a single
``evaluate()`` method that transforms validated OHLCV data into a structured
``Signal``.  Strategies are **pure** — they have no database, execution, or
portfolio side-effects.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Sequence

from bot.domain.models import Candle, Signal


class AbstractStrategy(ABC):
    """Base class for all trading strategies.

    Each strategy has a unique ``id`` and a ``name`` (human-readable).
    The ``evaluate()`` method takes a sequence of validated candles (all
    completed, no future bars) and returns a ``Signal`` for the *most recent*
    eligible bar.
    """

    @property
    @abstractmethod
    def id(self) -> str:
        """Machine-readable identifier (e.g. ``"rsi_reversion"``)."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name (e.g. ``"RSI Mean Reversion"``)."""

    @property
    @abstractmethod
    def params(self) -> dict:
        """Current parameter snapshot (read-only)."""

    @abstractmethod
    def evaluate(self, candles: Sequence[Candle]) -> Signal:
        """Evaluate the strategy on a sequence of completed candles.

        Args:
            candles: At least ``min_history`` bars of validated OHLCV data
                     in chronological order (oldest first).

        Returns:
            A ``Signal`` for the most recent bar.

        Raises:
            ``InsufficientDataError`` if fewer than ``min_history`` bars.
        """

    @property
    @abstractmethod
    def min_history(self) -> int:
        """Minimum number of bars needed for a meaningful evaluation."""
