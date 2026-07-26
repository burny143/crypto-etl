#!/usr/bin/env python3
"""
etl.py — Current price snapshot ETL

Fetches current ticker data (price, 24h change, volume) for a list of crypto
symbols and upserts it to Supabase ``crypto_data``.

Sources (in order of preference, with automatic fallback):
  1. OKX  (free, no API key)
  2. Binance (free, no API key)
  3. CCXT any other installed exchange

Environment: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""

import os
import time
from datetime import datetime, timezone

from supabase import create_client, Client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Supported pairs. OKX format (BASE-QUOTE) — also works on most CEX exchanges.
# Add any pair from https://www.okx.com/api/v5/public/instruments?instType=SPOT
SYMBOLS = [
    "BTC-USDT",
    "ETH-USDT",
    "XRP-USDT",
    "SOL-USDT",
    "BNB-USDT",
    "ADA-USDT",
    "DOGE-USDT",
    "AVAX-USDT",
    "DOT-USDT",
    "LINK-USDT",
    "POL-USDT",
    "UNI-USDT",
    "SHIB-USDT",
    "LTC-USDT",
    "BCH-USDT",
    "ATOM-USDT",
    "ETC-USDT",
    "XLM-USDT",
    "FIL-USDT",
    "TRX-USDT",
    "NEAR-USDT",
    "APT-USDT",
    "ARB-USDT",
    "OP-USDT",
    "SUI-USDT",
    "PEPE-USDT",
    "INJ-USDT",
    "TIA-USDT",
    "SEI-USDT",
    "STRK-USDT",
]

SLEEP_SECONDS = 0.5  # polite rate limit between symbols


# ---------------------------------------------------------------------------
# Exchange bootstrap — try exchanges in order, use the first that works
# ---------------------------------------------------------------------------

def _boot_exchange():
    """Return a CCXT exchange instance (OKX → Binance → first available)."""
    import ccxt

    candidates = [
        ("okx", ccxt.okx),
        ("binance", ccxt.binance),
    ]
    # Also try any other exchange that supports fetch_ticker
    for name, klass in candidates:
        try:
            ex = klass()
            ex.load_markets()
            print(f"  Exchange: {name}")
            return ex
        except Exception as exc:
            print(f"  {name} unavailable ({exc}), trying next…")
    # Last resort: scan all exchanges
    for name in ccxt.exchanges:
        try:
            klass = getattr(ccxt, name)
            ex = klass()
            if ex.has.get("fetchTicker"):
                ex.load_markets()
                print(f"  Exchange: {name} (fallback)")
                return ex
        except Exception:
            continue
    raise RuntimeError("No CCXT exchange with fetchTicker available")


# ---------------------------------------------------------------------------
# Supabase helpers
# ---------------------------------------------------------------------------

def _supabase() -> Client:
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise ValueError("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set")
    return create_client(url, key)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_etl():
    supabase = _supabase()
    exchange = _boot_exchange()
    now_iso = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    successes = 0
    failures = 0

    for raw_symbol in SYMBOLS:
        # CCXT prefers a forward-slash delimiter internally, but OKX accepts
        # both. Pass the symbol as-is and let CCXT normalise it.
        try:
            ticker = exchange.fetch_ticker(raw_symbol)

            last = ticker.get("last") or ticker.get("close")
            if last is None:
                print(f"  SKIP  {raw_symbol}: no last price")
                failures += 1
                continue

            # Build the upsert payload matching the crypto_data schema
            payload = {
                "symbol": raw_symbol,
                "current_price": float(last),
                "previous_close": float(ticker["open"]) if ticker.get("open") else None,
                "market_cap": None,  # CCXT doesn't return mcap; dashboard handles null gracefully
                "name": raw_symbol.replace("-", "/"),  # human-friendly display name
                "updated_at": now_iso,
            }

            supabase.table("crypto_data").upsert(payload).execute()
            print(f"  OK    {raw_symbol}: ${last:,.2f}")
            successes += 1

        except Exception as exc:
            print(f"  FAIL  {raw_symbol}: {exc}")
            failures += 1

        time.sleep(SLEEP_SECONDS)

    print(f"\nDone — {successes} ok, {failures} failed, {len(SYMBOLS)} total")


if __name__ == "__main__":
    run_etl()
