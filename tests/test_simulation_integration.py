#!/usr/bin/env python3
"""Integration test for simulation runner (HTTP + SSE)."""

import json
import threading
import time
import urllib.request
from http.server import HTTPServer
from bot.simulation_runner import SimulationHTTPHandler


def test_sse_streaming():
    """Test that SSE streams candle, state, and trade events."""
    server = HTTPServer(("127.0.0.1", 8774), SimulationHTTPHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)

    try:
        # Start the simulation
        req = urllib.request.Request(
            "http://127.0.0.1:8774/api/start", data=b"", method="POST"
        )
        urllib.request.urlopen(req)

        # Connect to SSE stream
        resp = urllib.request.urlopen("http://127.0.0.1:8774/api/stream")

        events: list[dict] = []
        event_types: list[str] = []
        deadline = time.time() + 6

        while time.time() < deadline and len(events) < 5:
            line = resp.readline().decode().strip()
            if line.startswith("event: "):
                event_types.append(line[7:])
            elif line.startswith("data: "):
                try:
                    events.append(json.loads(line[6:]))
                except json.JSONDecodeError:
                    pass
            time.sleep(0.01)

        print(f"Received {len(events)} events, types: {set(event_types)}")

        # Verify we got actual data
        state_events = [e for e in events if "price" in e and "cash" in e]
        candle_events = [e for e in events if "close" in e and "volume" in e]

        print(f"  State events: {len(state_events)}")
        print(f"  Candle events: {len(candle_events)}")

        if state_events:
            s = state_events[-1]
            price = s.get("price", 0)
            cash = s.get("cash", 0)
            equity = s.get("equity", 0)
            trades = s.get("total_trades", 0)
            print(f"  Latest state: price={price:.4f}, cash={cash:.2f}, "
                  f"equity={equity:.2f}, trades={trades}")

        if candle_events:
            c = candle_events[-1]
            print(f"  Latest candle: O={c['open']:.4f} H={c['high']:.4f} "
                  f"L={c['low']:.4f} C={c['close']:.4f} V={c['volume']:.2f}")

        assert len(state_events) > 0, "Should have received state events"
        assert len(candle_events) > 0, "Should have received candle events"
        print("SSE streaming test PASSED")

    finally:
        # Cleanup
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:8774/api/stop", data=b"", method="POST"
            )
            urllib.request.urlopen(req)
        except Exception:
            pass
        server.shutdown()


def test_cors():
    """Test CORS headers are set."""
    server = HTTPServer(("127.0.0.1", 8775), SimulationHTTPHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.5)

    try:
        req = urllib.request.Request(
            "http://127.0.0.1:8775/api/status"
        )
        resp = urllib.request.urlopen(req)
        cors = resp.getheader("Access-Control-Allow-Origin")
        print(f"CORS header: {cors}")
        assert cors == "*", f"Expected * got {cors}"
        print("CORS test PASSED")
    finally:
        server.shutdown()


if __name__ == "__main__":
    test_cors()
    test_sse_streaming()
    print("\nAll integration tests PASSED")
