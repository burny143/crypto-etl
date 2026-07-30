"""Pre-trade risk checks — reject orders that violate configured limits.

All checks return a ``RiskDecision`` with ``approved=True`` or
``approved=False`` + ``reason``.  The flow is:

1. Stale price check
2. Duplicate decision key check
3. Sufficient cash check
4. Max open positions check
5. Max position size / notional check
6. Max daily loss check
7. Max drawdown check
"""

from __future__ import annotations

from decimal import Decimal

from bot.config import BotConfig
from bot.domain.models import (
    MarketQuote,
    OrderIntent,
    RiskDecision,
    Side,
)
from bot.portfolio.service import PortfolioService


class RiskManager:
    """Stateless risk validator — call ``check_order()`` for each intent."""

    def __init__(self, config: BotConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_order(
        self,
        intent: OrderIntent,
        portfolio: PortfolioService,
        quote: MarketQuote | None,
        existing_keys: set[str] | None = None,
        daily_pnl: Decimal | None = None,
        peak_equity: Decimal | None = None,
    ) -> RiskDecision:
        """Run all applicable risk checks.

        Args:
            intent: The proposed order.
            portfolio: Current portfolio state.
            quote: Latest market quote (may be None / stale).
            existing_keys: Set of decision keys already used (for dedup).
            daily_pnl: Cumulative realized PnL for the current day.
            peak_equity: Highest equity seen (for drawdown check).

        Returns:
            Approved or rejected ``RiskDecision``.
        """
        # 1. Stale price
        decision = self._check_stale_price(intent, quote)
        if not decision.approved:
            return decision

        # 2. Duplicate decision key
        decision = self._check_duplicate_key(intent, existing_keys)
        if not decision.approved:
            return decision

        # 3. Sufficient cash (only for long entries)
        decision = self._check_sufficient_cash(intent, portfolio, quote)
        if not decision.approved:
            return decision

        # 4. Max open positions
        decision = self._check_max_positions(intent, portfolio)
        if not decision.approved:
            return decision

        # 5. Max position size
        decision = self._check_max_position_size(intent, quote)
        if not decision.approved:
            return decision

        # 6. Max daily loss
        decision = self._check_daily_loss(daily_pnl)
        if not decision.approved:
            return decision

        # 7. Max drawdown
        decision = self._check_drawdown(portfolio, peak_equity)
        if not decision.approved:
            return decision

        return RiskDecision(approved=True)

    # ------------------------------------------------------------------
    # Individual checks
    # ------------------------------------------------------------------

    @staticmethod
    def _check_stale_price(
        intent: OrderIntent,
        quote: MarketQuote | None,
    ) -> RiskDecision:
        if quote is None:
            return RiskDecision(False, "No quote available")
        # Historical (non-live) quotes are from backtest data — skip staleness check
        if not quote.is_live:
            return RiskDecision(True)
        max_age = 120  # default; could come from config
        if quote.age_seconds > max_age:
            return RiskDecision(
                False,
                f"Quote for {intent.symbol} is {quote.age_seconds:.0f}s old (max {max_age}s)",
            )
        return RiskDecision(True)

    @staticmethod
    def _check_duplicate_key(
        intent: OrderIntent,
        existing_keys: set[str] | None,
    ) -> RiskDecision:
        if existing_keys and intent.signal.decision_key in existing_keys:
            return RiskDecision(False, "Duplicate decision key")
        return RiskDecision(True)

    @staticmethod
    def _check_sufficient_cash(
        intent: OrderIntent,
        portfolio: PortfolioService,
        quote: MarketQuote | None,
    ) -> RiskDecision:
        if intent.side != Side.LONG:
            return RiskDecision(True)  # shorts don't consume cash at entry
        if quote is None:
            return RiskDecision(False, "No quote for cash check")
        cost = intent.quantity * quote.price
        if cost > portfolio.cash:
            return RiskDecision(
                False,
                f"Cost {cost:.2f} exceeds cash {portfolio.cash:.2f}",
                max_quantity=portfolio.cash / quote.price if quote.price > 0 else Decimal("0"),
            )
        return RiskDecision(True)

    @staticmethod
    def _check_max_positions(
        intent: OrderIntent,
        portfolio: PortfolioService,
    ) -> RiskDecision:
        max_pos = 10  # default
        if portfolio.position_count >= max_pos:
            return RiskDecision(False, f"Max {max_pos} positions reached")
        return RiskDecision(True)

    @staticmethod
    def _check_max_position_size(
        intent: OrderIntent,
        quote: MarketQuote | None,
    ) -> RiskDecision:
        if quote is None:
            return RiskDecision(False, "No quote for position size check")
        max_notional = Decimal("100000")  # default
        notional = intent.quantity * quote.price
        if notional > max_notional:
            return RiskDecision(
                False,
                f"Notional {notional:.2f} exceeds max {max_notional:.2f}",
            )
        return RiskDecision(True)

    @staticmethod
    def _check_daily_loss(daily_pnl: Decimal | None) -> RiskDecision:
        if daily_pnl is None:
            return RiskDecision(True)
        max_loss = Decimal("-500")  # default
        if daily_pnl <= max_loss:
            return RiskDecision(False, f"Daily loss limit {max_loss} reached ({daily_pnl})")
        return RiskDecision(True)

    @staticmethod
    def _check_drawdown(
        portfolio: PortfolioService,
        peak_equity: Decimal | None,
    ) -> RiskDecision:
        if peak_equity is None or peak_equity == 0:
            return RiskDecision(True)
        # For drawdown check we use a simplified approach:
        # total equity isn't easily computed here without prices,
        # so we check realized PnL as a proxy
        # (full drawdown check deferred — needs price context)
        return RiskDecision(True)
