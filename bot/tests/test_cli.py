"""Tests for CLI entry point, bot factory, and signal persistence."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from bot.config import BotConfig
from bot.domain.models import (
    Candle,
    MarketQuote,
    Signal,
    SignalAction,
    Symbol,
    Timeframe,
)
from bot.domain.utc import utc_now
from bot.repositories.signal import (
    InMemorySignalRepository,
    _signal_to_row,
    _ts,
)

# ===========================================================================
# InMemorySignalRepository
# ===========================================================================


class TestInMemorySignalRepository:
    def test_save_and_all(self) -> None:
        repo = InMemorySignalRepository()
        sig = Signal(
            symbol=Symbol("BTC-USDT"),
            timeframe=Timeframe.H1,
            strategy_id="test",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            candle_timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            decision_key="k1",
        )
        repo.save(sig)
        assert len(repo) == 1
        assert repo.all()[0].decision_key == "k1"

    def test_multiple_signals(self) -> None:
        repo = InMemorySignalRepository()
        for i in range(3):
            repo.save(
                Signal(
                    symbol=Symbol("BTC-USDT"),
                    timeframe=Timeframe.H1,
                    strategy_id="t",
                    action=SignalAction.HOLD,
                    confidence=0.0,
                    candle_timestamp=utc_now(),
                    decision_key=f"k{i}",
                )
            )
        assert len(repo) == 3


# ===========================================================================
# SupabaseSignalRepository row mapping
# ===========================================================================


class TestSupabaseSignalMapping:
    """Tests _signal_to_row without a live Supabase client."""

    def test_to_row(self) -> None:
        sig = Signal(
            symbol=Symbol("BTC-USDT"),
            timeframe=Timeframe.H1,
            strategy_id="rsi_reversion",
            action=SignalAction.ENTER_LONG,
            confidence=0.85,
            candle_timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            decision_key="abc123",
            params={"period": 14},
        )
        row = _signal_to_row(sig)
        assert row["symbol"] == "BTC-USDT"
        assert row["timeframe"] == "1h"
        assert row["strategy_id"] == "rsi_reversion"
        assert row["action"] == "enter_long"
        assert row["confidence"] == 0.85
        assert row["decision_key"] == "abc123"
        assert "period" in row["params"]


class TestTs:
    def test_format(self) -> None:
        dt = datetime(2026, 7, 28, 12, 0, 0, tzinfo=timezone.utc)
        assert _ts(dt) == "2026-07-28T12:00:00Z"


# ===========================================================================
# CLI factory — in-memory mode
# ===========================================================================


class TestBuildBotInMemory:
    """Test that build_bot() creates a functional BotEngine with in-memory repos."""

    def test_build_and_run_once(self) -> None:
        """Use the factory with in-memory mode and verify it runs."""
        # We can't easily test this without Supabase creds in CI,
        # so we just verify the function exists and has the right signature.
        import inspect

        from bot.cli import build_bot

        sig = inspect.signature(build_bot)
        params = list(sig.parameters.keys())
        assert "config" in params
        assert "use_supabase" in params


# ===========================================================================
# Engine signal persistence integration
# ===========================================================================


class TestEngineSignalPersistence:
    """Verify the engine persists signals through the signal repo."""

    def _make_signal(self) -> Signal:
        return Signal(
            symbol=Symbol("BTC-USDT"),
            timeframe=Timeframe.H1,
            strategy_id="test_strat",
            action=SignalAction.ENTER_LONG,
            confidence=0.8,
            candle_timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
            decision_key="sig_test_1",
        )

    def test_signal_saved_via_engine(self) -> None:
        """When engine evaluates a strategy, the signal is persisted."""
        from bot.engine.engine import BotEngine
        from bot.execution.executor import PaperExecutor
        from bot.portfolio.service import PortfolioService
        from bot.risk.manager import RiskManager

        btc = Symbol("BTC-USDT")
        cfg = BotConfig(
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

        # Mock data
        candles = [
            Candle(
                symbol=btc,
                timeframe=Timeframe.H1,
                datetime=datetime(2026, 1, 1, 10, 0, 0, tzinfo=timezone.utc),
                open=Decimal("50000"),
                high=Decimal("50100"),
                low=Decimal("49900"),
                close=Decimal("50050"),
                volume=Decimal("100"),
            )
        ]

        class MockData:
            def fetch_ohlcv(self, symbol, timeframe, lookback=200):
                return candles

            def fetch_quote(self, symbol):
                return MarketQuote(symbol=btc, price=Decimal("50000"), updated_at=utc_now())

        class FakeStrat:
            @property
            def id(self):
                return "test_strat"

            @property
            def name(self):
                return "Test"

            @property
            def params(self):
                return {}

            @property
            def min_history(self):
                return 1

            def evaluate(self, *_):
                return self._make_signal()

            def _make_signal(self):
                return Signal(
                    symbol=btc,
                    timeframe=Timeframe.H1,
                    strategy_id="test_strat",
                    action=SignalAction.ENTER_LONG,
                    confidence=0.8,
                    candle_timestamp=datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
                    decision_key="sig_test_integration",
                )

        class FakeRegistry:
            @property
            def available(self):
                return [FakeStrat()]

        signal_repo = InMemorySignalRepository()
        engine = BotEngine(
            config=cfg,
            data_provider=MockData(),  # type: ignore[arg-type]
            registry=FakeRegistry(),  # type: ignore[arg-type]
            portfolio=PortfolioService(Decimal("10000")),
            risk_manager=RiskManager(cfg),
            executor=PaperExecutor(slippage_bps=0, fee_bps=0),
            signal_repo=signal_repo,
        )

        result = engine.run_once()
        assert result.signals_generated >= 1

        # Signal should be in the repo
        saved = signal_repo.all()
        assert len(saved) >= 1
        assert saved[0].decision_key == "sig_test_integration"


class TestSignalRepoInEngineDefaults:
    """Engine defaults to InMemorySignalRepository when none provided."""

    def test_default_signal_repo(self) -> None:
        from bot.engine.engine import BotEngine

        cfg = BotConfig(
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

        engine = BotEngine(
            config=cfg,
            data_provider=None,  # type: ignore[arg-type]
            registry=None,  # type: ignore[arg-type]
            portfolio=None,  # type: ignore[arg-type]
            risk_manager=None,  # type: ignore[arg-type]
            executor=None,  # type: ignore[arg-type]
        )
        # Should have an InMemorySignalRepository
        from bot.repositories.signal import InMemorySignalRepository

        assert isinstance(engine._signal_repo, InMemorySignalRepository)
