"""Portfolio accounting — tracks cash, open positions, and equity."""

from __future__ import annotations

from decimal import Decimal

from bot.domain.models import (
    OrderStatus,
    PaperOrder,
    PaperPosition,
    PortfolioSnapshot,
    Side,
    Symbol,
)
from bot.domain.utc import utc_now


class PortfolioService:
    """Pure in-memory portfolio accounting.

    Manages cash balance and open positions.  All monetary values are Decimal.
    """

    def __init__(self, starting_balance: Decimal) -> None:
        if starting_balance <= 0:
            raise ValueError(f"starting_balance must be positive, got {starting_balance}")
        self._cash = starting_balance
        # Keyed by (symbol, side) — one position per pair per side
        self._positions: dict[tuple[Symbol, Side], PaperPosition] = {}
        self._cumulative_realized_pnl: Decimal = Decimal("0")

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def cash(self) -> Decimal:
        return self._cash

    @property
    def positions(self) -> list[PaperPosition]:
        return list(self._positions.values())

    @property
    def position_count(self) -> int:
        return len(self._positions)

    @property
    def total_realized_pnl(self) -> Decimal:
        return self._cumulative_realized_pnl

    def get_position(self, symbol: Symbol, side: Side) -> PaperPosition | None:
        return self._positions.get((symbol, side))

    # ------------------------------------------------------------------
    # Position management
    # ------------------------------------------------------------------

    def apply_fill(self, order: PaperOrder, fee: Decimal = Decimal("0")) -> None:
        """Update portfolio after an order fill (entry or exit).

        Args:
            order: A filled PaperOrder.
            fee: Optional trading fee deducted from cash (default 0).
        """
        if order.status != OrderStatus.FILLED or order.price is None:
            raise ValueError(f"Cannot apply unfilled order: {order.status}")

        cost = order.quantity * order.price
        key = (order.symbol, order.side)

        if order.side == Side.LONG:
            # Opening a long: cash decreases
            existing = self._positions.get((order.symbol, Side.LONG))
            if existing:
                # Increase position (average in)
                total_qty = existing.quantity + order.quantity
                total_cost = (existing.quantity * existing.entry_price) + cost
                existing.entry_price = total_cost / total_qty
                existing.quantity = total_qty
                existing.strategy_id = order.strategy_id  # track latest strategy
            else:
                self._positions[key] = PaperPosition(
                    symbol=order.symbol,
                    side=Side.LONG,
                    quantity=order.quantity,
                    entry_price=order.price,
                    strategy_id=order.strategy_id,
                    opened_at=order.filled_at or utc_now(),
                )
            self._cash -= cost
            self._cash -= fee

        elif order.side == Side.SHORT:
            # Opening a short: cash increases (credit from sale)
            existing = self._positions.get((order.symbol, Side.SHORT))
            if existing:
                total_qty = existing.quantity + order.quantity
                total_credit = (existing.quantity * existing.entry_price) + cost
                existing.entry_price = total_credit / total_qty
                existing.quantity = total_qty
                existing.strategy_id = order.strategy_id  # track latest strategy
            else:
                self._positions[key] = PaperPosition(
                    symbol=order.symbol,
                    side=Side.SHORT,
                    quantity=order.quantity,
                    entry_price=order.price,
                    strategy_id=order.strategy_id,
                    opened_at=order.filled_at or utc_now(),
                )
            self._cash += cost
            self._cash -= fee

    def close_position(
        self,
        symbol: Symbol,
        side: Side,
        close_price: Decimal,
        close_quantity: Decimal | None = None,
        fee: Decimal = Decimal("0"),
    ) -> PaperOrder:
        """Partially or fully close a position, returning the closing order.

        Args:
            symbol: Trading pair.
            side: Side of the position to close.
            close_price: Fill price for the close.
            close_quantity: Quantity to close.  ``None`` = all.
            fee: Optional trading fee deducted from cash (default 0).

        Returns:
            The ``PaperOrder`` that represents the closing trade.
        """
        key = (symbol, side)
        pos = self._positions.get(key)
        if pos is None:
            raise ValueError(f"No open {side} position for {symbol}")

        qty = close_quantity if close_quantity is not None else pos.quantity
        if qty <= 0 or qty > pos.quantity:
            raise ValueError(f"close_quantity {qty} out of range (0, {pos.quantity}]")

        # Compute realized PnL
        if side == Side.LONG:
            pnl = (close_price - pos.entry_price) * qty
            close_side = Side.SHORT
        else:
            pnl = (pos.entry_price - close_price) * qty
            close_side = Side.LONG

        # Update cash
        if side == Side.LONG:
            # Selling long position → cash increases by proceeds
            self._cash += qty * close_price
        else:
            # Buying back short → cash decreases
            self._cash -= qty * close_price

        self._cash -= fee

        # Track realized PnL cumulatively
        pos.realized_pnl += pnl
        self._cumulative_realized_pnl += pnl

        # Reduce or remove position
        remaining = pos.quantity - qty
        if remaining == 0:
            del self._positions[key]
        else:
            pos.quantity = remaining
            # Partial close: invalidate unrealized PnL so next price update
            # recalculates it with the correct quantity
            pos.unrealized_pnl = None

        return PaperOrder(
            symbol=symbol,
            side=close_side,
            quantity=qty,
            price=close_price,
            status=OrderStatus.FILLED,
            strategy_id=pos.strategy_id,
            pnl=pnl,
            filled_at=utc_now(),
            opened_at=pos.opened_at,
            # decision_key intentionally blank — identifying close orders by
            # the exit signal key is done at the engine layer
        )

    # ------------------------------------------------------------------
    # Equity
    # ------------------------------------------------------------------

    def total_equity(self, current_prices: dict[Symbol, Decimal]) -> Decimal:
        """Sum of cash + unrealized PnL for all positions."""
        unrealized = Decimal("0")
        for pos in self._positions.values():
            price = current_prices.get(pos.symbol)
            if price is None:
                continue  # skip if price unavailable
            if pos.side == Side.LONG:
                unrealized += (price - pos.entry_price) * pos.quantity
            else:
                unrealized += (pos.entry_price - price) * pos.quantity
        return self._cash + unrealized

    def snapshot(self, current_prices: dict[Symbol, Decimal]) -> PortfolioSnapshot:
        """Capture a point-in-time portfolio snapshot."""
        return PortfolioSnapshot(
            timestamp=utc_now(),
            cash=self._cash,
            equity=self.total_equity(current_prices),
        )
