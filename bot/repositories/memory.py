"""In-memory repository implementations for testing and default use."""

from __future__ import annotations

from collections.abc import Iterator

from bot.domain.models import PaperOrder, PaperPosition, Side, Symbol


class InMemoryOrderRepository:
    """Thread-safe in-memory order storage."""

    def __init__(self) -> None:
        self._orders: list[PaperOrder] = []
        self._next_id = 1

    def save(self, order: PaperOrder) -> PaperOrder:
        """Persist an order.  Assigns an id if new."""
        if order.id is None:
            order.id = self._next_id
            self._next_id += 1
            self._orders.append(order)
        else:
            # Update existing — find and replace
            for i, o in enumerate(self._orders):
                if o.id == order.id:
                    self._orders[i] = order
                    break
        return order

    def find_by_key(self, decision_key: str) -> PaperOrder | None:
        for o in self._orders:
            if o.decision_key == decision_key:
                return o
        return None

    def find_by_symbol(self, symbol: Symbol) -> list[PaperOrder]:
        return [o for o in self._orders if o.symbol == symbol]

    def all(self) -> list[PaperOrder]:
        return list(self._orders)

    def __len__(self) -> int:
        return len(self._orders)

    def __iter__(self) -> Iterator[PaperOrder]:
        return iter(self._orders)


class InMemoryPositionRepository:
    """Thread-safe in-memory open position storage."""

    def __init__(self) -> None:
        self._positions: dict[tuple[Symbol, Side], PaperPosition] = {}

    def save(self, position: PaperPosition) -> PaperPosition:
        key = (position.symbol, position.side)
        self._positions[key] = position
        return position

    def find_open(self, symbol: Symbol, side: Side) -> PaperPosition | None:
        return self._positions.get((symbol, side))

    def all_open(self) -> list[PaperPosition]:
        return list(self._positions.values())

    def delete(self, symbol: Symbol, side: Side) -> None:
        self._positions.pop((symbol, side), None)

    def __len__(self) -> int:
        return len(self._positions)

    def __contains__(self, key: tuple[Symbol, Side]) -> bool:
        return key in self._positions
