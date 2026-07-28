"""Tests for the BotEngine orchestrator and row mapping for Supabase repos."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from bot.config import BotConfig
from bot.data.provider import MarketDataProvider
from bot.domain.models import (
    Candle,
    MarketQuote,
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
from bot.engine.engine import BotEngine, EngineResult
from bot.execution.executor import PaperExecutor
from bot.portfolio.service import PortfolioService
from bot.repositories.memory import InMemoryOrderRepository, InMemoryPositionRepository
from bot.repositories.supabase_repos import (
    SupabaseOrderRepository,
    SupabasePositionRepository,
    _parse_ts,
)
from bot.risk.manager import RiskManager

# ===========================================================================
# Mock market data provider
# ===========================================================================


class MockMarketData(MarketDataProvider):
    """Returns predetermined candles and quotes."""

    def __init__(
        self,
        candles: dict[tuple[Symbol, Timeframe], list[Candle]],
        quotes: dict[Symbol, MarketQuote],
    ) -> None:
        self.candles = candles
        self.quotes = quotes

    def fetch_ohlcv(
        self, symbol: Symbol, timeframe: Timeframe, lookback: int = 200
    ) -> list[Candle]:
        key = (symbol, timeframe)
        if key not in self.candles:
            raise ValueError(f"No data for {symbol} {timeframe}")
        return self.candles[key]

    def fetch_quote(self, symbol: Symbol) -> MarketQuote | None:
        return self.quotes.get(symbol)


# ===========================================================================
# Test double: strategy that produces a fixed signal sequence
# ===========================================================================


class FixedSignalStrategy:
    """Strategy that yields predetermined signals in order."""

    def __init__(self, signals: list[Signal], strategy_id: str = "test_strat") -> None:
        self._signals = signals
        self._idx = 0
        self._strategy_id = strategy_id

    @property
    def id(self) -> str:
        return self._strategy_id

    @property
    def name(self) -> str:
        return "Test Strategy"

    @property
    def params(self) -> dict:
        return {}

    @property
    def min_history(self) -> int:
        return 1

    def evaluate(self, candles: list[Candle]) -> Signal:
        if self._idx >= len(self._signals):
            return Signal(
                symbol=candles[-1].symbol if candles else Symbol("BTC-USDT"),
                timeframe=Timeframe.H1,
                strategy_id=self._strategy_id,
                action=SignalAction.HOLD,
                confidence=0.0,
                candle_timestamp=utc_now(),
                decision_key="end-of-sequence",
            )
        sig = self._signals[self._idx]
        self._idx += 1
        return sig


# ===========================================================================
# Helpers
# ===========================================================================


def _make_candle(symbol: Symbol, ts: datetime, close: int) -> Candle:
    d = Decimal(str(close))
    return Candle(
        symbol=symbol,
        timeframe=Timeframe.H1,
        datetime=ts,
        open=d,
        high=d,
        low=d,
        close=d,
        volume=Decimal("100"),
    )


def _make_signal(
    symbol: Symbol,
    action: SignalAction,
    key: str = "key",
    strategy_id: str = "test_strat",
) -> Signal:
    return Signal(
        symbol=symbol,
        timeframe=Timeframe.H1,
        strategy_id=strategy_id,
        action=action,
        confidence=0.8,
        candle_timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        decision_key=key,
    )


@pytest.fixture
def btc() -> Symbol:
    return Symbol("BTC-USDT")


@pytest.fixture
def cfg() -> BotConfig:
    return BotConfig(
        {
            "symbols": ["BTC-USDT"],
            "timeframes": ["1h"],
            "poll_interval_seconds": 1,
            "price_max_age_seconds": 120,
            "candle_grace_seconds": 30,
            "lookback_bars": 100,
            "starting_balance": 10000.0,
            "logging_level": "ERROR",
        }
    )


@pytest.fixture
def candles(btc) -> list[Candle]:
    ts = datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
    return [_make_candle(btc, ts, 50000 + i) for i in range(5)]


@pytest.fixture
def quote(btc) -> MarketQuote:
    return MarketQuote(symbol=btc, price=Decimal("50000"), updated_at=utc_now())


# ===========================================================================
# BotEngine tests
# ===========================================================================


class TestBotEngine:
    """Integration-style tests with mock data and strategies."""

    def _make_engine(
        self,
        cfg: BotConfig,
        signals: list[Signal],
        quote_value: Decimal | None = Decimal("50000"),
        btc: Symbol | None = None,
    ) -> BotEngine:
        btc = btc or Symbol("BTC-USDT")

        # Mock data — add quote unless explicitly set to None
        mock_candles = [
            _make_candle(btc, datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc), 50000)
        ]
        quotes: dict[Symbol, MarketQuote] = {}
        if quote_value is not None:
            quotes[btc] = MarketQuote(symbol=btc, price=quote_value, updated_at=utc_now())
        data = MockMarketData(
            candles={(btc, Timeframe.H1): mock_candles},
            quotes=quotes,
        )

        # Strategy registry — just pass our fixed-signal strategy
        class FakeRegistry:
            @property
            def available(self) -> list:
                return [FixedSignalStrategy(signals)]

        # Other deps
        portfolio = PortfolioService(Decimal(str(cfg.starting_balance)))
        risk = RiskManager(cfg)
        executor = PaperExecutor(slippage_bps=0, fee_bps=0)
        order_repo = InMemoryOrderRepository()
        pos_repo = InMemoryPositionRepository()

        return BotEngine(
            config=cfg,
            data_provider=data,
            registry=FakeRegistry(),  # type: ignore[arg-type]
            portfolio=portfolio,
            risk_manager=risk,
            executor=executor,
            order_repo=order_repo,
            position_repo=pos_repo,
            trade_fraction=Decimal("0.1"),
        )

    # ------------------------------------------------------------------
    # Entry
    # ------------------------------------------------------------------

    def test_entry_long(self, cfg, btc) -> None:
        signal = _make_signal(btc, SignalAction.ENTER_LONG, key="entry1")
        engine = self._make_engine(cfg, [signal], btc=btc)

        result = engine.run_once()
        assert result.orders_created == 1
        assert result.orders_rejected == 0
        assert result.signals_generated == 1

        # Portfolio should reflect the trade
        assert engine._portfolio.cash < Decimal("10000")  # spent cash
        pos = engine._portfolio.get_position(btc, Side.LONG)
        assert pos is not None
        assert pos.quantity > 0

        # Order should be in repo
        orders = list(engine._order_repo)
        assert len(orders) == 1
        assert orders[0].decision_key == "entry1"
        assert orders[0].status == OrderStatus.FILLED

    def test_entry_short(self, cfg, btc) -> None:
        signal = _make_signal(btc, SignalAction.ENTER_SHORT, key="short1")
        engine = self._make_engine(cfg, [signal], btc=btc)

        result = engine.run_once()
        assert result.orders_created == 1

        # Short increases cash (credit from sale)
        assert engine._portfolio.cash > Decimal("10000")
        pos = engine._portfolio.get_position(btc, Side.SHORT)
        assert pos is not None

    def test_duplicate_key_rejected(self, cfg, btc) -> None:
        """Risk should reject duplicate decision keys."""
        signal = _make_signal(btc, SignalAction.ENTER_LONG, key="dup")
        engine = self._make_engine(cfg, [signal], btc=btc)

        # First run — approved
        r1 = engine.run_once()
        assert r1.orders_created == 1

        # Second run — same key, should be rejected
        # Reset the strategy to re-emit the same signal
        engine._registry = FixedSignalStrategy(
            [_make_signal(btc, SignalAction.ENTER_LONG, key="dup")]
        )
        signal2 = _make_signal(btc, SignalAction.ENTER_LONG, key="dup")
        engine._registry = type(
            "FakeReg",
            (),
            {"available": [FixedSignalStrategy([signal2])]},
        )()

        # Clear the portfolio but keep the order repo with the old key
        engine._portfolio = PortfolioService(Decimal("10000"))
        r2 = engine.run_once()
        # Should be rejected because "dup" is already in order_repo
        assert r2.orders_rejected >= 1

    # ------------------------------------------------------------------
    # Exit
    # ------------------------------------------------------------------

    def test_exit_long(self, cfg, btc) -> None:
        """Enter long, then exit on next cycle."""
        # First: enter
        enter_sig = _make_signal(btc, SignalAction.ENTER_LONG, key="entry")
        engine = self._make_engine(cfg, [enter_sig], btc=btc)
        engine.run_once()

        cash_before = engine._portfolio.cash
        pos = engine._portfolio.get_position(btc, Side.LONG)
        assert pos is not None

        # Second: exit (higher price = profit)
        exit_sig = _make_signal(btc, SignalAction.EXIT_LONG, key="exit")
        engine._registry = type(
            "FakeReg",
            (),
            {"available": [FixedSignalStrategy([exit_sig])]},
        )()

        # Use a higher quote for profit
        engine._data.quotes[btc] = MarketQuote(
            symbol=btc, price=Decimal("51000"), updated_at=utc_now()
        )

        result = engine.run_once()
        assert result.orders_created == 1

        # Position should be closed
        assert engine._portfolio.get_position(btc, Side.LONG) is None

        # Cash should have increased by proceeds
        assert engine._portfolio.cash > cash_before

        # Should have an exit order
        orders = list(engine._order_repo)
        exit_orders = [o for o in orders if o.decision_key == "exit"]
        assert len(exit_orders) == 1

    def test_exit_no_position(self, cfg, btc) -> None:
        """Exit signal without a position should be a no-op."""
        signal = _make_signal(btc, SignalAction.EXIT_LONG, key="exit_no_pos")
        engine = self._make_engine(cfg, [signal], btc=btc)

        result = engine.run_once()
        assert result.orders_created == 0
        assert result.errors == []

    # ------------------------------------------------------------------
    # No-op
    # ------------------------------------------------------------------

    def test_hold_does_nothing(self, cfg, btc) -> None:
        signal = _make_signal(btc, SignalAction.HOLD, key="hold")
        engine = self._make_engine(cfg, [signal], btc=btc)

        result = engine.run_once()
        assert result.orders_created == 0
        assert result.orders_rejected == 0
        assert result.signals_generated == 0  # HOLD is skipped before counting
        assert len(list(engine._order_repo)) == 0

    def test_no_quote_skips(self, cfg, btc) -> None:
        signal = _make_signal(btc, SignalAction.ENTER_LONG, key="no_quote")
        engine = self._make_engine(cfg, [signal], quote_value=None, btc=btc)

        result = engine.run_once()
        assert result.orders_created == 0  # skipped because quote is None

    # ------------------------------------------------------------------
    # Error isolation
    # ------------------------------------------------------------------

    def test_error_isolation(self, cfg, btc) -> None:
        """One symbol's failure shouldn't block others."""
        eth = Symbol("ETH-USDT")
        cfg.symbols = [btc, eth]

        signal = _make_signal(btc, SignalAction.ENTER_LONG, key="btc_entry")
        engine = self._make_engine(cfg, [signal], btc=btc)

        # Don't add ETH to mock data — will raise on fetch_ohlcv
        result = engine.run_once()

        # BTC should still have been processed
        assert result.orders_created == 1  # BTC entry succeeded
        assert len(result.errors) >= 1  # ETH failed

    # ------------------------------------------------------------------
    # Result structure
    # ------------------------------------------------------------------

    def test_result_structure(self, cfg, btc) -> None:
        signal = _make_signal(btc, SignalAction.ENTER_LONG, key="result_test")
        engine = self._make_engine(cfg, [signal], btc=btc)

        result = engine.run_once()
        assert isinstance(result, EngineResult)
        assert result.timestamp.tzinfo is not None
        assert result.signals_generated >= 1

    def test_run_once_idempotent(self, cfg, btc) -> None:
        """Multiple runs with same keys should reject duplicates."""
        signal = _make_signal(btc, SignalAction.ENTER_LONG, key="idempotent")
        engine = self._make_engine(cfg, [signal], btc=btc)

        r1 = engine.run_once()
        assert r1.orders_created == 1

        # Reset strategy to emit the same signal again
        engine._registry = type(
            "FakeReg",
            (),
            {"available": [FixedSignalStrategy([signal])]},
        )()
        engine._portfolio = PortfolioService(Decimal("10000"))

        r2 = engine.run_once()
        assert r2.orders_rejected >= 1  # duplicate key


# ===========================================================================
# Supabase repository row mapping
# ===========================================================================


class TestSupabaseOrderRepoMapping:
    """Test row serialisation/deserialisation without a live Supabase."""

    def test_to_row(self, btc) -> None:
        order = PaperOrder(
            symbol=btc,
            side=Side.LONG,
            quantity=Decimal("0.1"),
            price=Decimal("50000"),
            status=OrderStatus.FILLED,
            decision_key="dk",
            strategy_id="s1",
        )
        repo = SupabaseOrderRepository.__new__(SupabaseOrderRepository)
        row = repo._to_row(order)

        assert row["symbol"] == "BTC-USDT"
        assert row["side"] == "long"
        assert row["quantity"] == 0.1
        assert row["price"] == 50000.0
        assert row["status"] == "filled"
        assert row["decision_key"] == "dk"

    def test_from_row(self) -> None:
        row = {
            "id": 42,
            "symbol": "BTC-USDT",
            "side": "long",
            "quantity": "0.1",
            "order_type": "market",
            "price": "50000.0",
            "status": "filled",
            "decision_key": "dk",
            "strategy_id": "s1",
            "reason": "",
        }
        repo = SupabaseOrderRepository.__new__(SupabaseOrderRepository)
        order = repo._from_row(row)

        assert order.id == 42
        assert order.symbol == Symbol("BTC-USDT")
        assert order.side == Side.LONG
        assert order.quantity == Decimal("0.1")
        assert order.price == Decimal("50000")
        assert order.status == OrderStatus.FILLED
        assert order.decision_key == "dk"

    def test_from_row_null_price(self) -> None:
        row = {
            "id": None,
            "symbol": "BTC-USDT",
            "side": "short",
            "quantity": "1",
            "order_type": "market",
            "price": None,
            "status": "pending",
            "decision_key": "dk2",
            "strategy_id": "s2",
            "reason": "",
        }
        repo = SupabaseOrderRepository.__new__(SupabaseOrderRepository)
        order = repo._from_row(row)

        assert order.price is None
        assert order.status == OrderStatus.PENDING


class TestSupabasePositionRepoMapping:
    def test_to_row(self, btc) -> None:
        pos = PaperPosition(
            symbol=btc,
            side=Side.LONG,
            quantity=Decimal("0.1"),
            entry_price=Decimal("50000"),
        )
        repo = SupabasePositionRepository.__new__(SupabasePositionRepository)
        row = repo._to_row(pos)

        assert row["symbol"] == "BTC-USDT"
        assert row["side"] == "long"
        assert row["quantity"] == 0.1
        assert row["entry_price"] == 50000.0

    def test_from_row(self) -> None:
        row = {
            "id": 1,
            "symbol": "BTC-USDT",
            "side": "long",
            "quantity": "0.1",
            "entry_price": "50000",
            "strategy_id": "s1",
            "current_price": None,
            "unrealized_pnl": None,
            "realized_pnl": "0",
            "status": "open",
        }
        repo = SupabasePositionRepository.__new__(SupabasePositionRepository)
        pos = repo._from_row(row)

        assert pos.id == 1
        assert pos.symbol == Symbol("BTC-USDT")
        assert pos.side == Side.LONG
        assert pos.quantity == Decimal("0.1")
        assert pos.entry_price == Decimal("50000")


# ===========================================================================
# _parse_ts
# ===========================================================================


class TestParseTs:
    def test_none(self) -> None:
        assert _parse_ts(None) is None

    def test_datetime(self) -> None:
        dt = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = _parse_ts(dt)
        assert result == dt
        assert result.tzinfo is not None

    def test_naive_datetime(self) -> None:
        dt = datetime(2026, 1, 1)
        result = _parse_ts(dt)
        assert result == dt.replace(tzinfo=timezone.utc)

    def test_iso_string(self) -> None:
        result = _parse_ts("2026-01-01T00:00:00Z")
        assert result is not None
        assert result.year == 2026

    def test_invalid_string(self) -> None:
        assert _parse_ts("not-a-date") is None
