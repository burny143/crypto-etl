#!/usr/bin/env python3
"""
historical_etl.py

Downloads historical OHLCV data for a list of cryptocurrencies via CCXT
(OKX → Binance → fallback) across multiple timeframes, resamples 1h→4h locally,
and upserts everything into the Supabase ``crypto_historical`` table.

Environment: SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
"""

import os
import sys
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
from supabase import create_client, Client

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

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

# CCXT timeframe → milliseconds. Used to compute the "since" parameter.
TF_MS = {
    "1m": 60_000,
    "5m": 300_000,
    "15m": 900_000,
    "30m": 1_800_000,
    "1h": 3_600_000,
    "4h": 14_400_000,
    "1d": 86_400_000,
}

TIMEFRAME_CONFIG = {
    "1d": {"since_days_ago": 3 * 365, "ccxt_tf": "1d", "resample": None},   # 3 years
    "1h": {"since_days_ago": 180,     "ccxt_tf": "1h", "resample": None},   # 6 months
    "4h": {"since_days_ago": 180,     "ccxt_tf": "1h", "resample": "4h"},   # resample from 1h
}

BATCH_SIZE = 500
SLEEP_BETWEEN_CALLS_SECONDS = 0.8  # CCXT built-in rate limit handles most; this is extra safety


# ---------------------------------------------------------------------------
# Exchange bootstrap
# ---------------------------------------------------------------------------

def _boot_exchange():
    """Return a CCXT exchange (OKX → Binance → first with fetchOHLCV)."""
    import ccxt

    candidates = [
        ("okx", ccxt.okx),
        ("binance", ccxt.binance),
    ]
    for name, klass in candidates:
        try:
            ex = klass()
            ex.load_markets()
            print(f"  Exchange: {name}")
            return ex
        except Exception as exc:
            print(f"  {name} unavailable ({exc}), trying next…")
    for name in ccxt.exchanges:
        try:
            klass = getattr(ccxt, name)
            ex = klass()
            if ex.has.get("fetchOHLCV"):
                ex.load_markets()
                print(f"  Exchange: {name} (fallback)")
                return ex
        except Exception:
            continue
    raise RuntimeError("No CCXT exchange with fetchOHLCV available")


# ---------------------------------------------------------------------------
# Supabase
# ---------------------------------------------------------------------------

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
if not SUPABASE_URL or not SUPABASE_SERVICE_ROLE_KEY:
    print("ERROR: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.")
    sys.exit(1)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def ohlcv_to_df(ohlcv: list, symbol: str, timeframe: str) -> pd.DataFrame:
    """Convert a CCXT OHLCV list-of-lists into a clean DataFrame."""
    df = pd.DataFrame(ohlcv, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    df = df.drop(columns=["timestamp"])
    df = df.set_index("datetime")

    # Coerce to float
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # Drop any row missing essential OHLC
    df = df.dropna(subset=["open", "high", "low", "close"])

    # CCXT returns newest-first for some exchanges; sort ascending
    df = df.sort_index()

    df["symbol"] = symbol
    df["timeframe"] = timeframe
    return df


def resample_ohlcv(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    """Resample a datetime-indexed OHLCV frame to a coarser bar."""
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    agg = {k: v for k, v in agg.items() if k in df.columns}
    resampled = df.resample(rule).agg(agg)
    resampled = resampled.dropna(subset=["open", "high", "low", "close"])
    return resampled


def compute_derived_fields(df: pd.DataFrame) -> pd.DataFrame:
    """Add bar_return, bar_change_pct, price_range."""
    df["bar_return"] = (df["close"] - df["open"]) / df["open"]
    df["bar_change_pct"] = df["bar_return"] * 100
    df["price_range"] = df["high"] - df["low"]
    return df


def df_to_records(df: pd.DataFrame) -> list[dict]:
    """Convert a DataFrame into a list of row dicts for Supabase upsert."""
    records = []
    for _, row in df.iterrows():
        dt = row.get("datetime") if "datetime" in df.columns else row.name
        if pd.isna(dt):
            continue
        records.append({
            "symbol": row["symbol"],
            "timeframe": row["timeframe"],
            "datetime": dt.isoformat(),
            "open": _sf(row.get("open")),
            "high": _sf(row.get("high")),
            "low": _sf(row.get("low")),
            "close": _sf(row.get("close")),
            "adj_close": _sf(row.get("close")),  # CCXT has no adj_close; use close
            "volume": _si(row.get("volume")),
            "bar_return": _sf(row.get("bar_return")),
            "bar_change_pct": _sf(row.get("bar_change_pct")),
            "price_range": _sf(row.get("price_range")),
        })
    return records


import math

def _sf(val):
    """Safe float."""
    if val is None:
        return None
    if isinstance(val, float):
        if math.isnan(val) or math.isinf(val):
            return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (TypeError, ValueError):
        return None


def _si(val):
    """Safe int."""
    if val is None or (isinstance(val, float) and pd.isna(val)):
        return None
    return int(val)


def upsert_batch(rows: list[dict]):
    """Upsert rows into Supabase in BATCH_SIZE chunks."""
    if not rows:
        return
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i:i + BATCH_SIZE]
        try:
            supabase.table("crypto_historical").upsert(
                batch, on_conflict="symbol,timeframe,datetime"
            ).execute()
            print(f"    Upserted rows {i + 1}–{i + len(batch)} of {len(rows)}")
        except Exception as e:
            print(f"    ERROR upserting batch {i + 1}–{i + len(batch)}: {e}")


# ---------------------------------------------------------------------------
# Fetch logic
# ---------------------------------------------------------------------------

def fetch_symbol_data(
    exchange,
    symbol: str,
    timeframe: str,
    config: dict,
) -> pd.DataFrame:
    """Fetch OHLCV for one symbol/timeframe, resample if configured."""
    since_days = config["since_days_ago"]
    since = (datetime.now(timezone.utc) - timedelta(days=since_days)).timestamp() * 1000

    print(
        f"  Downloading {symbol} [{timeframe}] "
        f"(~{since_days}d, exchange_tf={config['ccxt_tf']}) ..."
    )

    try:
        raw = exchange.fetch_ohlcv(symbol, timeframe=config["ccxt_tf"], since=int(since))
    except Exception as exc:
        print(f"  WARNING: fetch failed for {symbol} [{timeframe}]: {exc}")
        return pd.DataFrame()

    if not raw or len(raw) < 2:
        print(f"  WARNING: too few rows ({len(raw or [])}) for {symbol} [{timeframe}]")
        return pd.DataFrame()

    df = ohlcv_to_df(raw, symbol, timeframe)

    # Resample if needed (e.g. 1h → 4h)
    if config["resample"]:
        # Reindex symbol/timeframe since resample drops non-OHLCV columns
        df_resampled = resample_ohlcv(df[["open", "high", "low", "close", "volume"]], config["resample"])
        df_resampled["symbol"] = symbol
        df_resampled["timeframe"] = timeframe
        df = df_resampled

    df = compute_derived_fields(df)
    return df.reset_index()  # datetime back to column


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 60)
    print("Crypto Historical ETL — starting run (CCXT backend)")
    print(f"UTC: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    exchange = _boot_exchange()
    total_rows = 0

    for timeframe, config in TIMEFRAME_CONFIG.items():
        print(f"\n--- Timeframe: {timeframe} ---")
        for symbol in SYMBOLS:
            try:
                df = fetch_symbol_data(exchange, symbol, timeframe, config)
                if df.empty:
                    print(f"  Skipping {symbol} [{timeframe}]: no data")
                else:
                    records = df_to_records(df)
                    print(f"  {symbol} [{timeframe}]: {len(records)} rows")
                    upsert_batch(records)
                    total_rows += len(records)
            except Exception as exc:
                print(f"  ERROR {symbol} [{timeframe}]: {exc}")
            time.sleep(SLEEP_BETWEEN_CALLS_SECONDS)

    print(f"\n{'=' * 60}")
    print(f"ETL complete. Total rows upserted: {total_rows}")
    print("=" * 60)


if __name__ == "__main__":
    main()
