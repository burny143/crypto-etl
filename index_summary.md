# Crypto Trading Terminal - index.html Architectural Summary

## Overall Layout & HTML Structure

### Header (Lines 1-50)
- **DOCTYPE & Language**: HTML5 with lang="en"
- **Meta Tags**: UTF-8 charset and viewport scaling
- **Page Title**: "Crypto Trading Terminal"
- **External Dependencies**: 
  - Supabase JS v2 CDN (`https://cdn.jsdelivr.net/npm/@supabase/supabase-js@2`)
  - Lightweight Charts v5.2.0 standalone (`https://unpkg.com/lightweight-charts@5.2.0/dist/lightweight-charts.standalone.production.js`)
- **Inline Styles**: Complete CSS custom properties and component styles (lines 19-161)

### Body Structure (Lines 163-287)
- **Top Navigation**: Header with branding, asset info, controls (indicators, signal, volume toggle, timeframe selector)
- **Main Layout**: Three-panel grid (left watchlist, center chart, right research panel)
- **Left Panel**: Symbol selector with pair information display
- **Center Panel**: Chart container (`#tvchart`) for Lightweight Charts rendering
- **Right Panel**: Nested sections (AI Insights, Top Strategies, Paper Trading)

## Script Sections & Key Functions

### Global State (Lines 326-336)
```javascript
let currentSymbol = "BTC"
let currentTimeframe = "1d"
let chart, candleSeries, volumeSeries
let activeIndicators = new Map()
let historicalData = []
let signalConditions = []
let signalChartMarkers = []
let symbolPriceCache = {}
```

### Indicator Definitions (Lines 296-324)
- 12 technical indicators with configurable parameters
- Includes: SMA, EMA, RSI, MACD, BB, VWAP, ADX, ATR, OBV, StochRSI, Vol Ratio, Keltner
- Each has dedicated computation function and CSS color schemes

### Core Functions (Major Blocks)

#### 1. Indicator Computation (Lines 337-603)
- Individual compute functions for each indicator type
- Shared utility functions: `getClose`, `getHigh`, `getLow`, `getVolume`, `getTime`
- Map-based lookups for efficient data access (improved in bug fixes)

#### 2. Chart Initialization (Lines 848-897)
- Lightweight Charts setup with v5 compatibility fixes
- Candlestick and volume series configuration
- Responsive resizing handler

#### 3. Data Loading & Processing (Lines 932-1986)
- `loadChartData()`: Fetches crypto_historical data from Supabase
- Rebuilds `historicalData` array with OHLCV + color fields
- Updates price cache and renders chart/series
- Re-initializes indicators on data refresh

#### 4. UI Components & Event Handling (Multiple Sections)
- **Indicator Toggle**: `toggleIndicator()` with max 3 active limit
- **Signal Engine**: `addSignalCondition()`, `runSignal()`, `clearSignal()`
- **Strategy Results**: `loadStrategyResults()`, `applyStrategySignals()`
- **Paper Trading**: `placeOrder()`, `closePosition()`, `renderPositions()`, `refreshTradingUI()`
- **Symbol Selection**: `selectSymbol()` for real-time updates

#### 5. Supabase Integration
- Global Supabase client initialized at lines 291-294
- Multiple data sources: `crypto_historical`, `crypto_data`, `paper_positions`, `paper_orders`, `crypto_research`, `strategy_results`

## External API Endpoints & Data Sources

### Supabase Tables (Read/Write Operations)

#### Historical Data (`crypto_historical`)
- **Purpose**: Primary OHLCV data for charting
- **Schema**: symbol, timeframe, datetime, open, high, low, close, volume
- **Access**: Filtered by symbol/timeframe, ordered by datetime
- **Usage**: `loadChartData()` → transforms → `historicalData`

#### Current Price (`crypto_data`)
- **Purpose**: Real-time price snapshots for watchlists
- **Fields**: symbol, current_price, previous_close
- **Usage**: `loadWatchlist()` for pair selection options

#### Paper Trading (`paper_positions`, `paper_orders`)
- **Positions**: Open trades with symbol, side, quantity, entry_price, current_price, unrealized_pnl
- **Orders**: Trade history with pnl calculation and status tracking
- **RLS Policies**: V4 allows anon INSERT/UPDATE/DELETE on paper tables

#### Research (`crypto_research`)
- **AI-generated**: Technical analysis insights from `generateResearch()`
- **Schema**: symbol, title, summary, sentiment, confidence, details

#### Strategy Results (`strategy_results`)
- **Backtesting**: Historical strategy performance metrics
- **Fields**: strategy_name, symbol, timeframe, params, sharpe_ratio, total_return_pct, win_rate, trade_count, validation flag

## Major CSS Classes & Framework

### Custom Properties (Lines 20-30)
```css
--bg-base, --bg-panel, --bg-hover
--border, --text-main, --text-muted
--up, --down, --accent
```

### Component Classes
- **Layout**: `.topbar`, `.main-layout`, `.sidebar`, `.chart-container`
- **Indicators**: `.ind-option`, `.indicator-btn`, `.indicator-dropdown`
- **Trading UI**: `.trade-row`, `.pos-item`, `.order-item`, `.strat-item`
- **Chart Styling**: Custom colors for up/down candles, volume bars

## Section Ranges Overview

| Section | Line Range | Description |
|---------|------------|-------------|
| **Header/Styles** | 1-161 | HTML meta, dependencies, and core CSS |
| **Body Layout** | 163-287 | UI structure and main panels |
| **Script State** | 326-336 | Global variables and state |
| **Indicator Definitions** | 296-324 | 12 indicator configs with colors |
| **Indicator Math** | 337-603 | Pure JS indicator computation functions |
| **UI & Event Handlers** | 639-1986 | Core application logic and event handling |
| **Research** | 1435-1581 | AI research generation and display |
| **Paper Trading** | 1583-1799 | Trading position and order management |
| **Chart Data** | 932-1986 | Data loading and rendering logic |

## Critical Dependencies & Notes

1. **Lightweight Charts v5.2.0**: Pinned specific version to avoid breaking changes
2. **Supabase**: Real-time data sync with RLS policies for security
3. **Client-Side Computation**: All indicators calculated in JS, no server needed for core functionality
4. **Service Worker**: `initTrading()` initializes $10K starting balance (resets on reload)
5. **7-Day Strategy Results**: Limited to strategies with ≥5 trades for reliability
6. **Position Netting**: Opposite-side orders automatically reduce existing positions (fixed in bug fixes)
7. **Cache Management**: `symbolPriceCache` for fast symbol-specific price lookup

## Debugging & Monitoring

- **Console Logging**: Comprehensive error logging in Supabase operations
- **Visual Indicators**: Active indicator count display and status badges
- **Error Handling**: Try-catch blocks with user alerts for critical failures
- **Debug Info**: Strategy result OOS/IS labeling for validation tracking