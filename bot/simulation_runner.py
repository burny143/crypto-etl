#!/usr/bin/env python3
"""
Simulation Runner — connects synthetic market generator to the paper-trading
bot engine with real-time SSE streaming.

Architecture::

    SyntheticMarket (1 candle/sec)
        │
        ▼
    SimulationOrchestrator
        ├── PortfolioService   (cash / positions / equity)
        ├── PaperExecutor      (fill orders, fees)
        ├── RiskManager        (pre-trade checks)
        └── StrategyRegistry   (strategy instances)
        │
        ├──▶ SSE broadcast (every tick)
        │      └── candle, state, trade events
        │
        └──▶ HTTP API
               ├── GET  /api/stream   → SSE stream
               ├── POST /api/start    → start simulation
               ├── POST /api/stop     → stop simulation
               └── POST /api/reset    → reset to initial state

Usage:
    python -m bot.simulation_runner  [--port 8766]
"""

from __future__ import annotations

import json
import logging
import os
import sys
import threading
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from decimal import Decimal
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any, Callable

# Ensure the crypto-etl root is on sys.path
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.normpath(os.path.join(_THIS_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from bot.synthetic_market import SyntheticMarket, SyntheticCandle, MarketState
from bot.domain.models import (
    Candle,
    MarketQuote,
    OrderIntent,
    PortfolioSnapshot,
    Side,
    Signal,
    SignalAction,
    Symbol,
    Timeframe,
)
from bot.domain.utc import utc_now
from bot.execution.executor import PaperExecutor
from bot.portfolio.service import PortfolioService
from bot.risk.manager import RiskManager
from bot.config import BotConfig
from bot.strategies.registry import StrategyRegistry

logger = logging.getLogger("simulation_runner")


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_PORT = 8766
SSE_HEARTBEAT_INTERVAL = 15.0  # seconds between keepalive comments
SIMULATION_POLL_INTERVAL = 1.0  # seconds between simulation ticks
PRE_SEED_CANDLES = 500  # candles to pre-generate before starting
SYMBOL = Symbol("FRED/USDT")
STARTING_CASH = Decimal("10000.00")
POSITIONS_HISTORY_MAX = 50


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------

def _decimal_to_float(d: Decimal) -> float:
    return float(d) if d is not None else 0.0


def _serialize_candle(candle: SyntheticCandle) -> dict:
    return {
        "time": int(candle.timestamp),  # Unix seconds for Lightweight Charts
        "open": candle.open,
        "high": candle.high,
        "low": candle.low,
        "close": candle.close,
        "volume": candle.volume,
    }


# ---------------------------------------------------------------------------
# SSE Event
# ---------------------------------------------------------------------------


@dataclass
class SseEvent:
    """A single Server-Sent Event."""
    event: str
    data: dict

    def serialize(self) -> str:
        body = json.dumps(self.data, default=str)
        return f"event: {self.event}\ndata: {body}\n\n"


# ---------------------------------------------------------------------------
# Simulation Orchestrator
# ---------------------------------------------------------------------------


class SimulationOrchestrator:
    """Drives the simulation loop: generate candles → evaluate → trade → broadcast."""

    def __init__(self) -> None:
        self.market = SyntheticMarket(
            base_price=100.0,
            volatility=0.02,
            drift=0.0004,
            tick_interval=1.0,
            symbol="FRED/USDT",
        )
        self.portfolio = PortfolioService(starting_balance=STARTING_CASH)
        self.executor = PaperExecutor(slippage_bps=5, fee_bps=10)
        # Minimal config for risk manager (only need max_positions etc.)
        config = BotConfig({
            "symbols": ["FRED-USDT"],
            "timeframes": ["1h"],
            "poll_interval_seconds": 1,
            "price_max_age_seconds": 120,
            "candle_grace_seconds": 30,
            "lookback_bars": 200,
            "starting_balance": 10000.0,
            "logging_level": "INFO",
            "env": {
                "supabase_url": "SUPABASE_URL",
                "supabase_service_role_key": "SUPABASE_SERVICE_ROLE_KEY",
            },
        })
        self.risk_manager = RiskManager(config)
        self.registry = StrategyRegistry()
        self.registry.register_defaults()

        # Candle buffer (domain Candle objects for strategy evaluation)
        self._candle_buffer: list[Candle] = []
        self._synthetic_buffer: list[SyntheticCandle] = []
        self._max_buffer = 5000

        # Trade tracking
        self._trades: list[dict] = []
        self._total_trades = 0
        self._seen_decision_keys: set[str] = set()

        # Threading
        self._running = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # SSE subscribers
        self._subscribers: list[Callable[[SseEvent], None]] = []

        # Current state cache
        self._current_price: Decimal = Decimal("100.0")
        self._current_state: MarketState | None = None
        self._start_time: float = 0.0
        self._candles_generated = 0

    # ------------------------------------------------------------------
    # Subscriptions
    # ------------------------------------------------------------------

    def subscribe(self, callback: Callable[[SseEvent], None]) -> None:
        """Register an SSE event callback."""
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[SseEvent], None]) -> None:
        if callback in self._subscribers:
            self._subscribers.remove(callback)

    def _broadcast(self, event: SseEvent) -> None:
        """Send an event to all subscribers."""
        dead: list[Callable] = []
        for cb in self._subscribers:
            try:
                cb(event)
            except Exception:
                dead.append(cb)
        for cb in dead:
            self._subscribers.remove(cb)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        """Start the simulation in a background thread."""
        if self._running:
            logger.warning("Simulation already running")
            return

        self._running = True
        self._start_time = time.time()
        self._thread = threading.Thread(target=self._simulation_loop, daemon=True)
        self._thread.start()

        # Start synthetic market generation
        if not self.market.is_running:
            self.market.start()

        logger.info("Simulation started")

    def stop(self) -> None:
        """Stop the simulation."""
        self._running = False
        if self.market.is_running:
            self.market.stop()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5.0)
        self._thread = None
        logger.info("Simulation stopped")

    def reset(self) -> None:
        """Reset portfolio and candle buffers to initial state."""
        was_running = self._running
        if was_running:
            self.stop()

        with self._lock:
            self.portfolio = PortfolioService(starting_balance=STARTING_CASH)
            self._candle_buffer.clear()
            self._synthetic_buffer.clear()
            self._trades.clear()
            self._total_trades = 0
            self._seen_decision_keys.clear()
            self._current_price = Decimal("100.0")
            self._current_state = None
            self._candles_generated = 0

        self.market.reset()

        if was_running:
            self.start()

        logger.info("Simulation reset")

    # ------------------------------------------------------------------
    # Main simulation loop
    # ------------------------------------------------------------------

    def _simulation_loop(self) -> None:
        """Main loop: generate candle, evaluate strategies, trade, broadcast."""
        # Pre-seed the candle buffer with historical data
        self._pre_seed()

        while self._running:
            tick_start = time.time()

            try:
                # 1. Generate a candle
                synthetic_candle, market_state = self.market.tick()
                self._current_state = market_state
                self._current_price = Decimal(str(market_state.price))
                self._candles_generated += 1

                # 2. Convert to domain Candle and buffer
                domain_candle = self._to_domain_candle(synthetic_candle)
                with self._lock:
                    self._synthetic_buffer.append(synthetic_candle)
                    self._candle_buffer.append(domain_candle)
                    if len(self._candle_buffer) > self._max_buffer:
                        self._candle_buffer = self._candle_buffer[-self._max_buffer:]
                        self._synthetic_buffer = self._synthetic_buffer[-self._max_buffer:]

                # 3. Broadcast candle event
                self._broadcast(SseEvent("candle", _serialize_candle(synthetic_candle)))

                # 4. Evaluate strategies (only if enough candles)
                signals: list[Signal] = []
                if len(self._candle_buffer) >= 50:
                    signals = self._evaluate_strategies()

                # 5. Process signals
                for signal in signals:
                    self._process_signal(signal)

                # 6. Update position prices
                self._update_position_prices()

                # 7. Broadcast state snapshot
                self._broadcast_state()

            except Exception as exc:
                logger.error("Simulation tick error: %s", exc)

            # Throttle to ~1 tick per second
            elapsed = time.time() - tick_start
            sleep_for = max(0, SIMULATION_POLL_INTERVAL - elapsed)
            if sleep_for > 0:
                time.sleep(sleep_for)

        logger.info("Simulation loop ended")

    def _pre_seed(self) -> None:
        """Generate historical candles so strategies have data on first tick."""
        logger.info("Pre-seeding %d candles...", PRE_SEED_CANDLES)
        for _ in range(PRE_SEED_CANDLES):
            synthetic, state = self.market.tick()
            domain = self._to_domain_candle(synthetic)
            self._synthetic_buffer.append(synthetic)
            self._candle_buffer.append(domain)
            self._current_state = state
            self._current_price = Decimal(str(state.price))
            self._candles_generated += 1
        logger.info("Pre-seed complete — current price: %.4f", float(self._current_price))

    # ------------------------------------------------------------------
    # Strategy evaluation
    # ------------------------------------------------------------------

    def _evaluate_strategies(self) -> list[Signal]:
        """Run all registered strategies on current candle buffer."""
        signals: list[Signal] = []
        candles = list(self._candle_buffer)

        for strategy in self.registry.available:
            try:
                signal = strategy.evaluate(candles)
                if signal.action != SignalAction.HOLD:
                    signals.append(signal)
            except Exception as exc:
                logger.debug("Strategy %s: %s", strategy.id, exc)

        return signals

    def _process_signal(self, signal: Signal) -> None:
        """Route entry/exit signals to handlers."""
        if signal.action in (SignalAction.ENTER_LONG, SignalAction.ENTER_SHORT):
            self._process_entry(signal)
        elif signal.action in (SignalAction.EXIT_LONG, SignalAction.EXIT_SHORT):
            self._process_exit(signal)

    def _process_entry(self, signal: Signal) -> None:
        """Check risk → execute fill → update portfolio → record trade."""
        side = Side.LONG if signal.action == SignalAction.ENTER_LONG else Side.SHORT

        # Compute quantity (10% of available)
        if side == Side.LONG:
            available = self.portfolio.cash
        else:
            available = self.portfolio.total_equity({SYMBOL: self._current_price})
        quantity_raw = available * Decimal("0.1") / self._current_price
        quantity = quantity_raw.quantize(Decimal("0.0001"))

        if quantity <= 0:
            return

        intent = OrderIntent(
            symbol=signal.symbol,
            side=side,
            quantity=quantity,
            signal=signal,
        )

        # Build a MarketQuote for risk checks
        quote = MarketQuote(
            symbol=signal.symbol,
            price=self._current_price,
            updated_at=utc_now(),
            is_live=True,
        )

        # Risk check
        decision = self.risk_manager.check_order(
            intent, self.portfolio, quote, existing_keys=self._seen_decision_keys
        )
        if not decision.approved:
            logger.debug("Risk rejected %s %s: %s", signal.symbol, side, decision.reason)
            self._broadcast(SseEvent("trade", {
                "type": "rejected",
                "side": side.value,
                "price": _decimal_to_float(self._current_price),
                "reason": decision.reason,
                "timestamp": time.time(),
            }))
            return

        # Execute
        order = self.executor.fill_order(intent, quote)
        self.portfolio.apply_fill(order)

        # Track
        if order.decision_key:
            self._seen_decision_keys.add(order.decision_key)
        self._total_trades += 1

        # Record
        trade = {
            "type": "entry",
            "side": side.value,
            "quantity": _decimal_to_float(quantity),
            "price": _decimal_to_float(order.price) if order.price else 0,
            "strategy": signal.strategy_id,
            "timestamp": time.time(),
            "pnl": None,
        }
        self._trades.append(trade)
        if len(self._trades) > POSITIONS_HISTORY_MAX:
            self._trades = self._trades[-POSITIONS_HISTORY_MAX:]

        logger.info(
            "ENTER %s %s %.4f @ %.4f [%s]",
            side.value.upper(), signal.symbol, float(quantity),
            float(order.price or 0), signal.strategy_id,
        )
        self._broadcast(SseEvent("trade", trade))

    def _process_exit(self, signal: Signal) -> None:
        """Close an existing position."""
        exit_side = Side.LONG if signal.action == SignalAction.EXIT_LONG else Side.SHORT
        position = self.portfolio.get_position(signal.symbol, exit_side)

        if position is None:
            return

        try:
            close_order = self.portfolio.close_position(
                signal.symbol, exit_side, self._current_price
            )
            close_order.decision_key = signal.decision_key
            if close_order.decision_key:
                self._seen_decision_keys.add(close_order.decision_key)
            self._total_trades += 1

            pnl = _decimal_to_float(close_order.pnl or Decimal("0"))
            trade = {
                "type": "exit",
                "side": exit_side.value,
                "quantity": _decimal_to_float(close_order.quantity),
                "price": _decimal_to_float(self._current_price),
                "strategy": signal.strategy_id,
                "timestamp": time.time(),
                "pnl": round(pnl, 2),
            }
            self._trades.append(trade)
            if len(self._trades) > POSITIONS_HISTORY_MAX:
                self._trades = self._trades[-POSITIONS_HISTORY_MAX:]

            logger.info(
                "EXIT %s %s @ %.4f PnL: %.2f [%s]",
                exit_side.value.upper(), signal.symbol,
                float(self._current_price), pnl, signal.strategy_id,
            )
            self._broadcast(SseEvent("trade", trade))

        except ValueError as exc:
            logger.debug("Exit failed: %s", exc)

    def _update_position_prices(self) -> None:
        """Update unrealized PnL on open positions."""
        for pos in self.portfolio.positions:
            pos.current_price = self._current_price
            if pos.side == Side.LONG:
                pos.unrealized_pnl = (self._current_price - pos.entry_price) * pos.quantity
            else:
                pos.unrealized_pnl = (pos.entry_price - self._current_price) * pos.quantity

    # ------------------------------------------------------------------
    # State broadcasting
    # ------------------------------------------------------------------

    def _broadcast_state(self) -> None:
        """Send a full state snapshot to all SSE subscribers."""
        equity = self.portfolio.total_equity({SYMBOL: self._current_price})
        positions = []
        for pos in self.portfolio.positions:
            entry_pnl = _decimal_to_float(pos.unrealized_pnl) if pos.unrealized_pnl else 0.0
            entry_qty = _decimal_to_float(pos.quantity)
            entry_price = _decimal_to_float(pos.entry_price)
            current = _decimal_to_float(self._current_price)
            positions.append({
                "side": pos.side.value,
                "quantity": round(entry_qty, 4),
                "entry_price": round(entry_price, 4),
                "current_price": round(current, 4),
                "pnl": round(entry_pnl, 2),
                "pnl_percent": round(
                    (entry_pnl / (entry_qty * entry_price)) * 100
                    if entry_qty * entry_price > 0 else 0.0,
                    2,
                ),
            })

        initial = _decimal_to_float(STARTING_CASH)
        total_pnl = _decimal_to_float(equity) - initial

        state = {
            "running": self._running,
            "uptime": round(time.time() - self._start_time, 1) if self._start_time else 0,
            "candles_generated": self._candles_generated,
            "price": _decimal_to_float(self._current_price),
            "bid": self._current_state.bid if self._current_state else self._current_price,
            "ask": self._current_state.ask if self._current_state else self._current_price,
            "change_24h": self._current_state.change_24h if self._current_state else 0.0,
            "volume_24h": self._current_state.volume_24h if self._current_state else 0.0,
            "high_24h": self._current_state.high_24h if self._current_state else _decimal_to_float(self._current_price),
            "low_24h": self._current_state.low_24h if self._current_state else _decimal_to_float(self._current_price),
            "cash": round(_decimal_to_float(self.portfolio.cash), 2),
            "equity": round(_decimal_to_float(equity), 2),
            "total_pnl": round(total_pnl, 2),
            "total_pnl_percent": round(
                (total_pnl / initial) * 100 if initial > 0 else 0.0, 2
            ),
            "position_count": self.portfolio.position_count,
            "total_trades": self._total_trades,
            "positions": positions,
            "recent_trades": self._trades[-10:],
            "timestamp": time.time(),
        }

        self._broadcast(SseEvent("state", state))

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        """Return current simulation status."""
        equity = self.portfolio.total_equity({SYMBOL: self._current_price})
        return {
            "running": self._running,
            "uptime": round(time.time() - self._start_time, 1) if self._start_time else 0,
            "candles_generated": self._candles_generated,
            "price": _decimal_to_float(self._current_price),
            "cash": round(_decimal_to_float(self.portfolio.cash), 2),
            "equity": round(_decimal_to_float(equity), 2),
            "total_pnl": round(
                _decimal_to_float(equity) - _decimal_to_float(STARTING_CASH), 2
            ),
            "position_count": self.portfolio.position_count,
            "total_trades": self._total_trades,
        }

    # ------------------------------------------------------------------
    # Domain model conversion
    # ------------------------------------------------------------------

    @staticmethod
    def _to_domain_candle(sc: SyntheticCandle) -> Candle:
        """Convert a SyntheticCandle to a domain Candle."""
        dt = datetime.fromtimestamp(sc.timestamp, tz=timezone.utc)
        return Candle(
            symbol=SYMBOL,
            timeframe=Timeframe.H1,  # Strategies treat data as 1h candles
            datetime=dt,
            open=Decimal(str(sc.open)),
            high=Decimal(str(sc.high)),
            low=Decimal(str(sc.low)),
            close=Decimal(str(sc.close)),
            volume=Decimal(str(sc.volume)),
        )


# ---------------------------------------------------------------------------
# SSE Handler
# ---------------------------------------------------------------------------

# Global orchestrator instance
_orchestrator: SimulationOrchestrator | None = None


def _get_orchestrator() -> SimulationOrchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = SimulationOrchestrator()
    return _orchestrator


class SimulationHTTPHandler(BaseHTTPRequestHandler):
    """HTTP handler for simulation server.

    Routes:
        GET  /                → simulation.html
        GET  /api/stream      → SSE stream
        POST /api/start       → start simulation
        POST /api/stop        → stop simulation
        POST /api/reset       → reset simulation
        POST /api/status      → get status JSON
    """

    # Silence per-request log lines from BaseHTTPRequestHandler
    def log_message(self, format: str, *args: Any) -> None:
        if "/api/stream" in str(args[0]) if args else False:
            return  # suppress SSE polling logs
        logger.debug(format, *args)

    def _send_json(self, data: dict, status: int = 200) -> None:
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, path: str) -> None:
        try:
            with open(path, "rb") as f:
                content = f.read()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except FileNotFoundError:
            self._send_json({"error": "Not found"}, 404)

    def _handle_sse(self) -> None:
        """Handle SSE streaming connection."""
        orchestrator = _get_orchestrator()

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "keep-alive")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Callback to send events to this client
        def send_event(event: SseEvent) -> None:
            try:
                payload = event.serialize()
                self.wfile.write(payload.encode("utf-8"))
                self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                orchestrator.unsubscribe(send_event)

        orchestrator.subscribe(send_event)

        # Send initial state immediately
        initial = SseEvent("status", orchestrator.get_status())
        try:
            self.wfile.write(initial.serialize().encode("utf-8"))
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            orchestrator.unsubscribe(send_event)
            return

        # Heartbeat thread to keep connection alive
        stop_heartbeat = threading.Event()

        def _heartbeat() -> None:
            while not stop_heartbeat.is_set():
                if stop_heartbeat.wait(SSE_HEARTBEAT_INTERVAL):
                    break
                try:
                    self.wfile.write(": heartbeat\n\n".encode("utf-8"))
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError, OSError):
                    stop_heartbeat.set()
                    orchestrator.unsubscribe(send_event)

        hb_thread = threading.Thread(target=_heartbeat, daemon=True)
        hb_thread.start()

        # Block until client disconnects
        try:
            while not stop_heartbeat.is_set():
                if self.wfile.write(b""):
                    pass
                time.sleep(1)
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            stop_heartbeat.set()
            orchestrator.unsubscribe(send_event)

    # ------------------------------------------------------------------
    # Route dispatch
    # ------------------------------------------------------------------

    def do_GET(self) -> None:
        if self.path == "/" or self.path == "/index.html" or self.path == "/simulation.html":
            sim_html = os.path.join(_PROJECT_ROOT, "simulation.html")
            if not os.path.exists(sim_html):
                # Fallback: look in bot directory
                sim_html = os.path.join(_THIS_DIR, "..", "simulation.html")
            self._send_html(sim_html)
        elif self.path == "/api/stream":
            self._handle_sse()
        elif self.path == "/api/status":
            self._send_json(_get_orchestrator().get_status())
        else:
            self._send_json({"error": "Not found"}, 404)

    def do_POST(self) -> None:
        orchestrator = _get_orchestrator()

        if self.path == "/api/start":
            if orchestrator._running:
                self._send_json({"status": "already_running"})
            else:
                orchestrator.start()
                self._send_json({"status": "started"})

        elif self.path == "/api/stop":
            if not orchestrator._running:
                self._send_json({"status": "already_stopped"})
            else:
                orchestrator.stop()
                self._send_json({"status": "stopped"})

        elif self.path == "/api/reset":
            orchestrator.reset()
            self._send_json({"status": "reset"})

        else:
            self._send_json({"error": "Not found"}, 404)

    def do_OPTIONS(self) -> None:
        """CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """Run the simulation server."""
    import argparse

    parser = argparse.ArgumentParser(description="Simulation Runner for FRED/USDT paper trading")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Bind address")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    server = HTTPServer((args.host, args.port), SimulationHTTPHandler)
    logger.info("Simulation runner listening on http://%s:%d", args.host, args.port)
    logger.info("Open http://%s:%d/simulation.html in your browser", args.host, args.port)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
        # Stop simulation if running
        orch = _get_orchestrator()
        if orch._running:
            orch.stop()
        server.server_close()


if __name__ == "__main__":
    main()
