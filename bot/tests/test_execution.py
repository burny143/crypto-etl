"""Tests for portfolio accounting, risk checks, order execution, and repositories."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bot.config import BotConfig
from bot.domain.models import (
    MarketQuote,
    OrderIntent,
    OrderStatus,
    PaperOrder,
    PaperPosition,
    Side,
    Signal,
    SignalAction,
    Symbol,
    Timeframe,
)
from bot.domain.utc import utc_now
from bot.execution.executor import PaperExecutor
from bot.portfolio.service import PortfolioService
from bot.repositories.memory import InMemoryOrderRepository, InMemoryPositionRepository
from bot.risk.manager import RiskManager

# ===========================================================================
# Fixtures
# ===========================================================================


@pytest.fixture
def btc() -> Symbol:
    return Symbol("BTC-USDT")


@pytest.fixture
def cfg() -> BotConfig:
    return BotConfig(
        {
            "symbols": ["BTC-USDT"],
            "timeframes": ["1h"],
        }
    )


@pytest.fixture
def quote(btc) -> MarketQuote:
    return MarketQuote(symbol=btc, price=Decimal("50000"), updated_at=utc_now())


@pytest.fixture
def signal(btc) -> Signal:
    return Signal(
        symbol=btc,
        timeframe=Timeframe.H1,
        strategy_id="rsi_reversion",
        action=SignalAction.ENTER_LONG,
        confidence=0.8,
        candle_timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        decision_key="abc123",
    )


@pytest.fixture
def intent_long(btc, signal) -> OrderIntent:
    return OrderIntent(symbol=btc, side=Side.LONG, quantity=Decimal("0.1"), signal=signal)


@pytest.fixture
def intent_short(btc, signal) -> OrderIntent:
    return OrderIntent(symbol=btc, side=Side.SHORT, quantity=Decimal("1"), signal=signal)


# ===========================================================================
# Portfolio Service
# ===========================================================================


class TestPortfolioService:
    def test_starting_balance(self) -> None:
        ps = PortfolioService(Decimal("10000"))
        assert ps.cash == Decimal("10000")
        assert ps.position_count == 0

    def test_negative_balance_raises(self) -> None:
        with pytest.raises(ValueError, match="positive"):
            PortfolioService(Decimal("-100"))

    def test_apply_long_fill(self, btc) -> None:
        ps = PortfolioService(Decimal("10000"))
        order = PaperOrder(
            symbol=btc,
            side=Side.LONG,
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            status=OrderStatus.FILLED,
        )
        ps.apply_fill(order)
        assert ps.cash == Decimal("10000") - Decimal("5000")  # 0.1 * 50000
        pos = ps.get_position(btc, Side.LONG)
        assert pos is not None
        assert pos.quantity == Decimal("0.1")
        assert pos.entry_price == Decimal("50000")

    def test_apply_short_fill(self, btc) -> None:
        ps = PortfolioService(Decimal("10000"))
        order = PaperOrder(
            symbol=btc,
            side=Side.SHORT,
            quantity=Decimal("1"),
            price=Decimal("50000"),
            status=OrderStatus.FILLED,
        )
        ps.apply_fill(order)
        # Short: cash increases by sale proceeds
        assert ps.cash == Decimal("10000") + Decimal("50000")
        pos = ps.get_position(btc, Side.SHORT)
        assert pos is not None
        assert pos.quantity == Decimal("1")
        assert pos.entry_price == Decimal("50000")

    def test_average_in_long(self, btc) -> None:
        ps = PortfolioService(Decimal("20000"))
        ps.apply_fill(
            PaperOrder(
                symbol=btc,
                side=Side.LONG,
                quantity=Decimal("0.1"),
                price=Decimal("50000"),
                status=OrderStatus.FILLED,
            )
        )
        ps.apply_fill(
            PaperOrder(
                symbol=btc,
                side=Side.LONG,
                quantity=Decimal("0.1"),
                price=Decimal("51000"),
                status=OrderStatus.FILLED,
            )
        )
        pos = ps.get_position(btc, Side.LONG)
        assert pos is not None
        assert pos.quantity == Decimal("0.2")
        assert pos.entry_price == Decimal("50500")  # avg of 50000 and 51000

    def test_close_position_full(self, btc) -> None:
        ps = PortfolioService(Decimal("10000"))
        ps.apply_fill(
            PaperOrder(
                symbol=btc,
                side=Side.LONG,
                quantity=Decimal("0.1"),
                price=Decimal("50000"),
                status=OrderStatus.FILLED,
            )
        )
        close_order = ps.close_position(btc, Side.LONG, close_price=Decimal("51000"))
        assert close_order.pnl == Decimal("100")  # (51000 - 50000) * 0.1
        assert close_order.side == Side.SHORT  # selling to close
        assert ps.cash == Decimal("10100")  # 10000 start + 100 profit
        assert ps.get_position(btc, Side.LONG) is None

    def test_close_position_partial(self, btc) -> None:
        ps = PortfolioService(Decimal("10000"))
        ps.apply_fill(
            PaperOrder(
                symbol=btc,
                side=Side.LONG,
                quantity=Decimal("0.2"),
                price=Decimal("50000"),
                status=OrderStatus.FILLED,
            )
        )
        ps.close_position(
            btc, Side.LONG, close_price=Decimal("51000"), close_quantity=Decimal("0.1")
        )
        pos = ps.get_position(btc, Side.LONG)
        assert pos is not None
        assert pos.quantity == Decimal("0.1")  # remaining

    def test_close_nonexistent_position_raises(self, btc) -> None:
        ps = PortfolioService(Decimal("10000"))
        with pytest.raises(ValueError, match="No open"):
            ps.close_position(btc, Side.LONG, close_price=Decimal("50000"))

    def test_total_equity(self, btc) -> None:
        ps = PortfolioService(Decimal("10000"))
        ps.apply_fill(
            PaperOrder(
                symbol=btc,
                side=Side.LONG,
                quantity=Decimal("0.1"),
                price=Decimal("50000"),
                status=OrderStatus.FILLED,
            )
        )
        equity = ps.total_equity({btc: Decimal("51000")})
        assert equity == Decimal("5100")  # cash 5000 + unrealized 100

    def test_unfilled_order_raises(self, btc) -> None:
        ps = PortfolioService(Decimal("10000"))
        order = PaperOrder(
            symbol=btc,
            side=Side.LONG,
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            status=OrderStatus.PENDING,
        )
        with pytest.raises(ValueError, match="unfilled"):
            ps.apply_fill(order)


# ===========================================================================
# Risk Manager
# ===========================================================================


class TestRiskManager:
    def test_approve_valid_intent(self, cfg, intent_long, quote) -> None:
        rm = RiskManager(cfg)
        ps = PortfolioService(Decimal("10000"))
        decision = rm.check_order(intent_long, ps, quote)
        assert decision.approved

    def test_reject_stale_price(self, cfg, intent_long) -> None:
        from datetime import timedelta

        rm = RiskManager(cfg)
        ps = PortfolioService(Decimal("10000"))
        stale = MarketQuote(
            symbol=intent_long.symbol,
            price=Decimal("50000"),
            updated_at=utc_now() - timedelta(seconds=300),
        )
        decision = rm.check_order(intent_long, ps, stale)
        assert not decision.approved
        assert "stale" in decision.reason.lower() or "old" in decision.reason.lower()

    def test_reject_no_quote(self, cfg, intent_long) -> None:
        rm = RiskManager(cfg)
        ps = PortfolioService(Decimal("10000"))
        decision = rm.check_order(intent_long, ps, None)
        assert not decision.approved

    def test_reject_duplicate_key(self, cfg, intent_long, quote) -> None:
        rm = RiskManager(cfg)
        ps = PortfolioService(Decimal("10000"))
        decision = rm.check_order(intent_long, ps, quote, existing_keys={"abc123"})
        assert not decision.approved
        assert "duplicate" in decision.reason.lower()

    def test_reject_insufficient_cash(self, cfg, intent_long, quote) -> None:
        rm = RiskManager(cfg)
        ps = PortfolioService(Decimal("100"))  # not enough cash
        decision = rm.check_order(intent_long, ps, quote)
        assert not decision.approved
        assert "cash" in decision.reason.lower()

    def test_reject_max_positions(self, cfg, intent_long, quote, btc) -> None:
        rm = RiskManager(cfg)
        ps = PortfolioService(Decimal("1000000"))
        # Fill 10 positions to hit limit
        for i in range(10):
            sym = Symbol(f"COIN-{i:04d}-USDT")
            ps.apply_fill(
                PaperOrder(
                    symbol=sym,
                    side=Side.LONG,
                    quantity=Decimal("1"),
                    price=Decimal("100"),
                    status=OrderStatus.FILLED,
                )
            )
        decision = rm.check_order(intent_long, ps, quote)
        assert not decision.approved
        assert "position" in decision.reason.lower()

    def test_reject_max_notional(self, cfg, intent_long, quote) -> None:
        rm = RiskManager(cfg)
        ps = PortfolioService(Decimal("1000000"))
        huge = OrderIntent(
            symbol=intent_long.symbol,
            side=Side.LONG,
            quantity=Decimal("100"),
            signal=intent_long.signal,
        )
        decision = rm.check_order(huge, ps, quote)
        assert not decision.approved

    def test_reject_daily_loss(self, cfg, intent_long, quote) -> None:
        rm = RiskManager(cfg)
        ps = PortfolioService(Decimal("10000"))
        decision = rm.check_order(intent_long, ps, quote, daily_pnl=Decimal("-600"))
        assert not decision.approved

    def test_short_does_not_check_cash(self, cfg, intent_short, quote) -> None:
        rm = RiskManager(cfg)
        ps = PortfolioService(Decimal("100"))  # low cash, but short don't need it
        decision = rm.check_order(intent_short, ps, quote)
        # May fail on other checks (max notional), but not cash
        if not decision.approved:
            assert "cash" not in decision.reason.lower()


# ===========================================================================
# Paper Executor
# ===========================================================================


class TestPaperExecutor:
    def test_fill_long(self, intent_long, quote) -> None:
        ex = PaperExecutor(slippage_bps=5, fee_bps=10)
        order = ex.fill_order(intent_long, quote)
        assert order.status == OrderStatus.FILLED
        assert order.side == Side.LONG
        assert order.quantity == Decimal("0.1")
        assert order.price > quote.price  # slippage adds premium
        assert order.decision_key == "abc123"
        assert order.strategy_id == "rsi_reversion"

    def test_fill_short(self, intent_short, quote) -> None:
        ex = PaperExecutor(slippage_bps=5, fee_bps=10)
        order = ex.fill_order(intent_short, quote)
        assert order.side == Side.SHORT
        assert order.price < quote.price  # slippage takes discount

    def test_slippage_amount(self, intent_long, quote) -> None:
        ex = PaperExecutor(slippage_bps=50, fee_bps=0)  # 0.5% slippage
        order = ex.fill_order(intent_long, quote)
        expected_slippage = quote.price * Decimal("0.005")
        assert order.price == quote.price + expected_slippage

    def test_fee_amount(self, intent_long, quote) -> None:
        ex = PaperExecutor(slippage_bps=0, fee_bps=100)  # 1% fee
        fee = ex._compute_fee(intent_long.quantity, quote.price)
        assert fee == intent_long.quantity * quote.price * Decimal("0.01")


# ===========================================================================
# Repositories
# ===========================================================================


class TestInMemoryOrderRepository:
    def test_save_and_find_by_key(self, btc) -> None:
        repo = InMemoryOrderRepository()
        order = PaperOrder(
            symbol=btc,
            side=Side.LONG,
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            decision_key="key1",
        )
        saved = repo.save(order)
        assert saved.id == 1
        found = repo.find_by_key("key1")
        assert found is not None
        assert found.symbol == btc

    def test_find_missing_key(self) -> None:
        repo = InMemoryOrderRepository()
        assert repo.find_by_key("nonexistent") is None

    def test_all(self, btc) -> None:
        repo = InMemoryOrderRepository()
        repo.save(
            PaperOrder(
                symbol=btc,
                side=Side.LONG,
                quantity=Decimal("1"),
                price=Decimal("100"),
                decision_key="a",
            )
        )
        repo.save(
            PaperOrder(
                symbol=btc,
                side=Side.SHORT,
                quantity=Decimal("2"),
                price=Decimal("200"),
                decision_key="b",
            )
        )
        assert len(repo) == 2

    def test_find_by_symbol(self, btc) -> None:
        repo = InMemoryOrderRepository()
        repo.save(
            PaperOrder(
                symbol=btc,
                side=Side.LONG,
                quantity=Decimal("1"),
                price=Decimal("100"),
                decision_key="a",
            )
        )
        other = Symbol("ETH-USDT")
        repo.save(
            PaperOrder(
                symbol=other,
                side=Side.LONG,
                quantity=Decimal("1"),
                price=Decimal("100"),
                decision_key="b",
            )
        )
        assert len(repo.find_by_symbol(btc)) == 1


class TestInMemoryPositionRepository:
    def test_save_and_find(self, btc) -> None:
        repo = InMemoryPositionRepository()
        pos = PaperPosition(
            symbol=btc, side=Side.LONG, quantity=Decimal("0.1"), entry_price=Decimal("50000")
        )
        repo.save(pos)
        found = repo.find_open(btc, Side.LONG)
        assert found is not None
        assert found.quantity == Decimal("0.1")

    def test_delete(self, btc) -> None:
        repo = InMemoryPositionRepository()
        repo.save(
            PaperPosition(
                symbol=btc, side=Side.LONG, quantity=Decimal("0.1"), entry_price=Decimal("50000")
            )
        )
        repo.delete(btc, Side.LONG)
        assert repo.find_open(btc, Side.LONG) is None

    def test_all_open(self, btc) -> None:
        repo = InMemoryPositionRepository()
        repo.save(
            PaperPosition(
                symbol=btc, side=Side.LONG, quantity=Decimal("0.1"), entry_price=Decimal("50000")
            )
        )
        assert len(repo.all_open()) == 1
