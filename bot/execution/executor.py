"""Paper order executor — fills approved orders with fee/slippage modelling.

Flow:

1. Receive approved ``OrderIntent`` + fresh ``MarketQuote``
2. Compute fill price: quote ± slippage (adverse for entry, no slippage for exit)
3. Apply fees (maker/taker bps)
4. Return filled ``PaperOrder``
5. Portfolio service applies the fill (cash + position update)
"""

from __future__ import annotations

from decimal import Decimal

from bot.domain.models import (
    MarketQuote,
    OrderIntent,
    OrderStatus,
    PaperOrder,
    Side,
)
from bot.domain.utc import utc_now


class PaperExecutor:
    """Fill approved orders with configurable slippage and fees."""

    # Default rates (can be overridden per-instance)
    SLIPPAGE_BPS: int = 5  # 0.05%
    FEE_BPS: int = 10  # 0.10%

    def __init__(
        self,
        slippage_bps: int | None = None,
        fee_bps: int | None = None,
    ) -> None:
        self._slippage_bps = slippage_bps if slippage_bps is not None else self.SLIPPAGE_BPS
        self._fee_bps = fee_bps if fee_bps is not None else self.FEE_BPS

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def fill_order(self, intent: OrderIntent, quote: MarketQuote) -> PaperOrder:
        """Model a fill for an approved order intent.

        Args:
            intent: An approved ``OrderIntent``.
            quote: A fresh market quote to derive the fill price.

        Returns:
            A filled ``PaperOrder`` with computed price, fees, and status.
        """
        fill_price = self._compute_fill_price(intent.side, quote.price)

        now = utc_now()
        return PaperOrder(
            symbol=intent.symbol,
            side=intent.side,
            quantity=intent.quantity,
            price=fill_price,
            status=OrderStatus.FILLED,
            decision_key=intent.signal.decision_key,
            strategy_id=intent.signal.strategy_id,
            signal_timestamp=intent.signal.candle_timestamp,
            order_type="market",
            opened_at=now,
            filled_at=now,
        )

    # ------------------------------------------------------------------
    # Fee / slippage helpers
    # ------------------------------------------------------------------

    def _compute_fill_price(self, side: Side, market_price: Decimal) -> Decimal:
        """Apply adverse slippage to the market price.

        Long entries buy at a slight premium; short entries sell at a slight
        discount.  Exits use the raw market price (no slippage).
        """
        slippage = market_price * Decimal(self._slippage_bps) / Decimal(10000)
        if side == Side.LONG:
            return market_price + slippage
        else:
            return market_price - slippage

    def _compute_fee(self, quantity: Decimal, price: Decimal) -> Decimal:
        """Total fee in quote currency (always a cost)."""
        return quantity * price * Decimal(self._fee_bps) / Decimal(10000)

    @property
    def slippage_bps(self) -> int:
        return self._slippage_bps

    @property
    def fee_bps(self) -> int:
        return self._fee_bps
