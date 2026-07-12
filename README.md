# Supabase Crypto ETL

Pulls cryptocurrency data from **Yahoo Finance (yfinance)** and stores it in **Supabase**.

## Pipelines

### 1. Live Price Snapshot

- **Script:** `etl.py`
- **Workflow:** **Scheduled Crypto ETL** (`.github/workflows/schedule.yml`)
- **What:** Current price, previous close, market cap, and short name
- **Frequency:** Every 30 minutes via GitHub Actions (`*/30 * * * *`)
- **Symbols:** BTC-USD, ETH-USD, XRP-USD, SOL-USD, BNB-USD
- **Target table:** `crypto_data`

### 2. Historical OHLCV

- **Script:** `historical_etl.py`
- **Workflow:** **Daily Historical ETL** (`.github/workflows/historical_etl.yml`)
- **What:** Full OHLCV bar history with derived fields (bar return, change %, price range)
- **Frequency:** Daily at 00:05 UTC via GitHub Actions
- **Timeframes:** 1d (from 2023-01-01), 1h (from 2026-01-01), 4h (resampled from 1h)
- **Symbols:** Same 5 as above
- **Target table:** `crypto_historical`

## Setup

1. Create a Supabase project and get your URL and service role key.
2. In your GitHub repo, add the following **repository secrets**:
   - `SUPABASE_URL`
   - `SUPABASE_SERVICE_ROLE_KEY`

## Run Locally

```bash
pip install yfinance supabase pandas
$env:SUPABASE_URL = "your_url"
$env:SUPABASE_SERVICE_ROLE_KEY = "your_key"
python etl.py
python historical_etl.py
```

## Workflows

| Workflow Name | Script | Target Table | Trigger |
|---------------|--------|-------------|---------|
| **Scheduled Crypto ETL** | `etl.py` | `crypto_data` | Every 30 min + manual `workflow_dispatch` |
| **Daily Historical ETL** | `historical_etl.py` | `crypto_historical` | Daily at 00:05 UTC + manual `workflow_dispatch` |

Both workflows support manual triggering from the GitHub Actions tab.
