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
   - `SUPABASE_ANON_KEY` (for the frontend dashboard)

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

## Dashboard

A simple browser-based dashboard is available at `index.html`.

### Setup

Run this SQL in your Supabase SQL editor once to allow public read access:

```sql
CREATE POLICY "Allow public read" ON crypto_data FOR SELECT USING (true);
CREATE POLICY "Allow public read" ON crypto_historical FOR SELECT USING (true);
ALTER TABLE crypto_data ENABLE ROW LEVEL SECURITY;
ALTER TABLE crypto_historical ENABLE ROW LEVEL SECURITY;
```

### Deploy to GitHub Pages

The dashboard is deployed automatically via GitHub Actions (`.github/workflows/deploy.yml`). Supabase credentials are injected from GitHub secrets at build time — no manual editing needed.

1. In your GitHub repo, add the **repository secret** `SUPABASE_ANON_KEY` (find this in Supabase Settings → API).
2. Push to `main` or run the **Deploy Dashboard** workflow manually from the Actions tab.
3. Enable GitHub Pages for your repo (Settings → Pages → Source: GitHub Actions).

### Features

- Live price cards (current price, 24h change, market cap)
- Closing price line chart
- Candlestick chart (OHLCV)
- Volume bar chart
- Symbol and timeframe selectors
