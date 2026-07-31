#!/usr/bin/env python3
"""
Synthetic Market Generator — Geometric Brownian Motion with fat-tail shocks.

Generates realistic OHLCV candles at 1 per second for simulation/testing.
Supports threaded continuous generation with start/stop control and
optional historical BTC replay scaled to a configurable base price (~$100).

Usage:

    market = SyntheticMarket(base_price=100.0, volatility=0.02)
    market.start(callback=lambda candle: print(candle))
    ...
    market.stop()
"""

from __future__ import annotations

import math
import random
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

FAT_TAIL_PROB = 0.05   # 5 % chance of a t-distributed shock
T_DF = 3.0              # t-distribution degrees of freedom (low = fatter tails)
DEFAULT_BASE_PRICE = 100.0
DEFAULT_VOLATILITY = 0.02   # ~2 % per step
DEFAULT_DRIFT = 0.0004      # slight upward bias per step
TICK_INTERVAL = 1.0         # seconds between ticks


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SyntheticCandle:
    """A single synthetic OHLCV candle (1-second resolution)."""
    timestamp: float          # Unix seconds
    open: float
    high: float
    low: float
    close: float
    volume: float

    @property
    def timestamp_ms(self) -> int:
        return int(self.timestamp * 1000)

    @property
    def is_bullish(self) -> bool:
        return self.close >= self.open


@dataclass
class MarketState:
    """Current market state snapshot for broadcasting to frontend."""
    symbol: str = "FRED/USDT"
    price: float = DEFAULT_BASE_PRICE
    bid: float = DEFAULT_BASE_PRICE * 0.995
    ask: float = DEFAULT_BASE_PRICE * 1.005
    change_24h: float = 0.0
    volume_24h: float = 0.0
    high_24h: float = DEFAULT_BASE_PRICE
    low_24h: float = DEFAULT_BASE_PRICE
    timestamp: float = 0.0


# ---------------------------------------------------------------------------
# GBM helpers
# ---------------------------------------------------------------------------


def _t_sample(df: float = T_DF) -> float:
    """Student-t random variable using Box-Muller + chi-squared."""
    # Normal sample via Box-Muller
    u1 = random.random()
    u2 = random.random()
    z = math.sqrt(-2.0 * math.log(u1)) * math.cos(2.0 * math.pi * u2)
    # Chi-squared with df degrees of freedom
    chi2 = sum(random.gauss(0, 1) ** 2 for _ in range(int(df)))
    return z / math.sqrt(chi2 / df)


def _gbm_shock(drift: float, volatility: float, dt: float = 1.0) -> float:
    """Return the multiplicative return for one GBM step."""
    if random.random() < FAT_TAIL_PROB:
        epsilon = _t_sample(T_DF)
    else:
        epsilon = random.gauss(0, 1)
    return drift * dt + volatility * epsilon * math.sqrt(dt)


# ---------------------------------------------------------------------------
# Synthetic Market
# ---------------------------------------------------------------------------


class SyntheticMarket:
    """Generates synthetic OHLCV data using GBM with fat tails.

    Produces 1 candle per second.  Thread-safe — call ``start()`` to begin
    continuous generation and ``stop()`` to halt.
    """

    def __init__(
        self,
        base_price: float = DEFAULT_BASE_PRICE,
        volatility: float = DEFAULT_VOLATILITY,
        drift: float = DEFAULT_DRIFT,
        tick_interval: float = TICK_INTERVAL,
        symbol: str = "FRED/USDT",
    ) -> None:
        self._base_price = base_price
        self._volatility = volatility
        self._drift = drift
        self._tick_interval = tick_interval
        self._symbol = symbol

        # Internal state
        self._price = base_price
        self._prev_close = base_price
        self._candle_buffer: list[SyntheticCandle] = []
        self._max_buffer = 10_000

        # Threading
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()

        # Callbacks — called with (SyntheticCandle, MarketState) on each tick
        self._callbacks: list[Callable[[SyntheticCandle, MarketState], None]] = []

        # Replay mode
        self._replay_data: list[float] | None = None
        self._replay_idx: int = 0

        # 24h tracking
        self._prices_24h: list[float] = []

        # Lock for thread-safe state access
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def price(self) -> float:
        with self._lock:
            return self._price

    @property
    def candles(self) -> list[SyntheticCandle]:
        with self._lock:
            return list(self._candle_buffer)

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def register_callback(self, cb: Callable[[SyntheticCandle, MarketState], None]) -> None:
        """Register a callback invoked on every tick with (candle, state)."""
        self._callbacks.append(cb)

    def set_replay_data(self, prices: list[float]) -> None:
        """Set historical price data for replay mode.

        When set, GBM generation is paused and the generator replays
        the historical price sequence scaled to the base price range.
        """
        self._replay_data = prices
        self._replay_idx = 0

    def clear_replay(self) -> None:
        """Return to GBM generation mode."""
        self._replay_data = None
        self._replay_idx = 0

    # ------------------------------------------------------------------
    # Single-step generation
    # ------------------------------------------------------------------

    def tick(self) -> tuple[SyntheticCandle, MarketState]:
        """Generate a single synthetic candle and return (candle, state).

        Can be called manually or driven by the threaded loop.
        Thread-safe.
        """
        with self._lock:
            return self._do_tick()

    def _do_tick(self) -> tuple[SyntheticCandle, MarketState]:
        """Internal tick — caller must hold ``_lock``."""
        now = time.time()

        # Determine next price
        if self._replay_data is not None:
            # Historical replay mode
            raw = self._replay_data[self._replay_idx % len(self._replay_data)]
            self._replay_idx += 1
            # Scale to base_price range
            self._price = raw * (self._base_price / self._replay_data[0])
        else:
            # GBM step
            ret = _gbm_shock(self._drift, self._volatility)
            self._price *= math.exp(ret)
            # Prevent extreme values
            self._price = max(self._price, self._base_price * 0.1)
            self._price = min(self._price, self._base_price * 10.0)

        # Build candle
        spread = self._price * 0.001  # 0.1% intra-candle range
        candle_high = self._price + spread * random.random()
        candle_low = self._price - spread * random.random()
        # Ensure high >= open/close and low <= open/close
        open_price = self._prev_close
        close_price = self._price
        candle_high = max(candle_high, open_price, close_price)
        candle_low = min(candle_low, open_price, close_price)
        volume = random.uniform(100, 10_000)

        candle = SyntheticCandle(
            timestamp=now,
            open=round(open_price, 4),
            high=round(candle_high, 4),
            low=round(candle_low, 4),
            close=round(close_price, 4),
            volume=round(volume, 2),
        )

        # Update state
        self._candle_buffer.append(candle)
        if len(self._candle_buffer) > self._max_buffer:
            self._candle_buffer = self._candle_buffer[-self._max_buffer:]
        self._prev_close = self._price

        # 24h tracking
        self._prices_24h.append(self._price)
        cutoff = now - 86400
        self._prices_24h = [p for p in self._prices_24h if p >= cutoff]
        high_24h = max(self._prices_24h) if self._prices_24h else self._price
        low_24h = min(self._prices_24h) if self._prices_24h else self._price
        change_24h = (
            (self._price - self._prices_24h[0]) / self._prices_24h[0]
            if len(self._prices_24h) > 1 else 0.0
        )

        state = MarketState(
            symbol=self._symbol,
            price=round(self._price, 4),
            bid=round(self._price * 0.998, 4),
            ask=round(self._price * 1.002, 4),
            change_24h=round(change_24h * 100, 2),
            volume_24h=round(sum(
                c.volume for c in self._candle_buffer[-3600:]
            ), 2),
            high_24h=round(high_24h, 4),
            low_24h=round(low_24h, 4),
            timestamp=now,
        )

        return candle, state

    # ------------------------------------------------------------------
    # Continuous generation (threaded)
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start continuous generation in a background thread."""
        if self.is_running:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._generation_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        """Signal the generation loop to stop and wait for thread exit."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None

    def _generation_loop(self) -> None:
        """Background thread: generate candles at tick_interval."""
        while not self._stop_event.is_set():
            tick_start = time.time()
            candle, state = self.tick()
            # Notify callbacks
            for cb in self._callbacks:
                try:
                    cb(candle, state)
                except Exception:
                    pass  # don't let a bad callback crash the loop
            # Sleep for remaining tick interval
            elapsed = time.time() - tick_start
            sleep_for = max(0, self._tick_interval - elapsed)
            if sleep_for > 0:
                self._stop_event.wait(sleep_for)

    # ------------------------------------------------------------------
    # Reset
    # ------------------------------------------------------------------

    def reset(self) -> None:
        """Reset all state to initial values."""
        was_running = self.is_running
        if was_running:
            self.stop()
        with self._lock:
            self._price = self._base_price
            self._prev_close = self._base_price
            self._candle_buffer.clear()
            self._prices_24h.clear()
            self._replay_idx = 0
        # Clear callbacks
        self._callbacks.clear()
        if was_running:
            self.start()


# ---------------------------------------------------------------------------
# Convenience factory
# ---------------------------------------------------------------------------

def create_default_market() -> SyntheticMarket:
    """Create a SyntheticMarket with sensible simulation defaults."""
    return SyntheticMarket(
        base_price=100.0,
        volatility=0.02,
        drift=0.0004,
        tick_interval=1.0,
        symbol="FRED/USDT",
    )


__all__ = [
    "SyntheticMarket",
    "SyntheticCandle",
    "MarketState",
    "create_default_market",
]
