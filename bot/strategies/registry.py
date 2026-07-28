"""Strategy registry — maps strategy IDs to concrete instances."""

from __future__ import annotations

from bot.strategies.base import AbstractStrategy
from bot.strategies.rsi import RsiReversionStrategy


class StrategyRegistry:
    """A mutable registry of strategy instances keyed by ``strategy.id``.

    Pre-registered strategies (added by ``register_defaults()``):

    - ``rsi_reversion`` → ``RsiReversionStrategy``
    """

    def __init__(self) -> None:
        self._strategies: dict[str, AbstractStrategy] = {}

    def register(self, strategy: AbstractStrategy) -> None:
        """Register a strategy instance."""
        sid = strategy.id
        if sid in self._strategies:
            raise KeyError(f"Strategy {sid!r} is already registered")
        self._strategies[sid] = strategy

    def get(self, strategy_id: str) -> AbstractStrategy:
        """Look up a strategy by its id."""
        try:
            return self._strategies[strategy_id]
        except KeyError:
            raise KeyError(f"Unknown strategy {strategy_id!r}") from None

    @property
    def available(self) -> list[AbstractStrategy]:
        return list(self._strategies.values())

    @property
    def ids(self) -> list[str]:
        return list(self._strategies)

    def __contains__(self, strategy_id: str) -> bool:
        return strategy_id in self._strategies

    def register_defaults(self) -> None:
        """Register all shipped strategies with default parameters."""
        self.register(RsiReversionStrategy())
