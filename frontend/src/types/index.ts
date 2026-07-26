/** OHLCV bar as stored in Supabase */
export interface OHLCVBar {
  datetime: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
  adj_close?: number;
  bar_return?: number;
  bar_change_pct?: number;
  price_range?: number;
}

/** Trading pair symbol metadata */
export interface SymbolMeta {
  id: number;
  symbol: string;
  base_asset: string;
  quote_asset: string;
  display_name: string;
  exchange: string;
  active: boolean;
  sort_order: number;
}

/** Available timeframes */
export type Timeframe = "1m" | "5m" | "15m" | "30m" | "1h" | "4h" | "1d" | "1w";

/** Indicator descriptor */
export interface IndicatorDef {
  name: string;
  label: string;
  defaultParams: Record<string, number>;
  params: IndicatorParamDef[];
}

export interface IndicatorParamDef {
  key: string;
  label: string;
  type: "int" | "float";
  default: number;
  min?: number;
  max?: number;
}

/** Indicator data point */
export interface IndicatorPoint {
  datetime: string;
  value?: number | null;
  macd?: number | null;
  signal?: number | null;
  hist?: number | null;
  upper?: number | null;
  mid?: number | null;
  lower?: number | null;
}

/** Indicator with its computed data */
export interface IndicatorState {
  def: IndicatorDef;
  enabled: boolean;
  params: Record<string, number>;
  data?: IndicatorPoint[];
  loading: boolean;
}

/** AI Research entry */
export interface ResearchEntry {
  id: number;
  symbol: string;
  report_type: string;
  title: string;
  summary: string;
  details: Record<string, unknown>;
  sentiment: "bullish" | "bearish" | "neutral" | null;
  confidence: number | null;
  source: string;
  created_at: string;
}

/** Technical analysis summary */
export interface TechnicalSummary {
  symbol: string;
  timeframe: string;
  current_price: number;
  price_change_24h: number | null;
  indicators: Record<string, number | string | null>;
  support_resistance: {
    resistance: number[];
    support: number[];
  };
  summary: string;
}

/** Paper trading order */
export interface PaperOrder {
  id: number;
  symbol: string;
  side: "long" | "short";
  order_type: "market" | "limit" | "stop";
  quantity: number;
  price: number | null;
  status: string;
  pnl: number | null;
  opened_at: string;
  filled_at: string | null;
}

/** Paper trading position */
export interface PaperPosition {
  id: number;
  symbol: string;
  side: "long" | "short";
  quantity: number;
  entry_price: number;
  current_price: number | null;
  unrealized_pnl: number | null;
  realized_pnl: number;
  market_value: number | null;
  opened_at: string;
}

/** Portfolio summary */
export interface PortfolioSummary {
  cash: number;
  total_equity: number;
  margin_used: number;
  open_positions: number;
  total_realized_pnl: number;
  total_unrealized_pnl: number;
}

/** Equity curve point */
export interface EquityPoint {
  timestamp: string;
  equity: number;
  cash: number;
  margin_used: number;
}

// ─── Signal Engine Types ───

export type SignalOperator = "gt" | "lt" | "cross_above" | "cross_below" | "range";
export type SignalSide = "long" | "short";
export type SignalLogic = "all" | "any";

export interface SignalCondition {
  indicator: string;
  params: Record<string, number>;
  value_key?: string;
  operator: SignalOperator;
  value: number;
  value_low?: number;
  value_high?: number;
  side: SignalSide;
}

export interface SignalConfig {
  conditions: SignalCondition[];
  logic: SignalLogic;
}

export interface SignalPoint {
  datetime: string;
  signal: number;  // -1, 0, 1
  indicators: Record<string, number | null>;
}

export interface SignalResponse {
  symbol: string;
  timeframe: string;
  logic: string;
  signals: SignalPoint[];
  condition_count: number;
}

// ─── Available indicator definitions ───
export const AVAILABLE_INDICATORS: IndicatorDef[] = [
  {
    name: "sma",
    label: "SMA",
    defaultParams: { period: 20 },
    params: [{ key: "period", label: "Period", type: "int", default: 20, min: 2, max: 200 }],
  },
  {
    name: "ema",
    label: "EMA",
    defaultParams: { period: 20 },
    params: [{ key: "period", label: "Period", type: "int", default: 20, min: 2, max: 200 }],
  },
  {
    name: "rsi",
    label: "RSI",
    defaultParams: { period: 14 },
    params: [{ key: "period", label: "Period", type: "int", default: 14, min: 2, max: 50 }],
  },
  {
    name: "macd",
    label: "MACD",
    defaultParams: { fast: 12, slow: 26, signal: 9 },
    params: [
      { key: "fast", label: "Fast", type: "int", default: 12, min: 2, max: 100 },
      { key: "slow", label: "Slow", type: "int", default: 26, min: 2, max: 200 },
      { key: "signal", label: "Signal", type: "int", default: 9, min: 2, max: 50 },
    ],
  },
  {
    name: "bb",
    label: "Bollinger Bands",
    defaultParams: { period: 20, std: 2 },
    params: [
      { key: "period", label: "Period", type: "int", default: 20, min: 2, max: 100 },
      { key: "std", label: "Std Dev", type: "float", default: 2, min: 0.5, max: 4 },
    ],
  },
  {
    name: "vwap",
    label: "VWAP",
    defaultParams: {},
    params: [],
  },
  {
    name: "adx",
    label: "ADX",
    defaultParams: { period: 14 },
    params: [{ key: "period", label: "Period", type: "int", default: 14, min: 2, max: 50 }],
  },
  {
    name: "atr",
    label: "ATR",
    defaultParams: { period: 14 },
    params: [{ key: "period", label: "Period", type: "int", default: 14, min: 2, max: 50 }],
  },
  {
    name: "obv",
    label: "OBV",
    defaultParams: {},
    params: [],
  },
  {
    name: "stoch_rsi",
    label: "Stoch RSI",
    defaultParams: { period: 14, smooth_k: 3, smooth_d: 3 },
    params: [
      { key: "period", label: "Period", type: "int", default: 14, min: 2, max: 50 },
      { key: "smooth_k", label: "Smooth K", type: "int", default: 3, min: 1, max: 10 },
      { key: "smooth_d", label: "Smooth D", type: "int", default: 3, min: 1, max: 10 },
    ],
  },
  {
    name: "vol_ratio",
    label: "Volume Ratio",
    defaultParams: { period: 20 },
    params: [{ key: "period", label: "Period", type: "int", default: 20, min: 2, max: 100 }],
  },
  {
    name: "kc",
    label: "Keltner Channels",
    defaultParams: { period: 20, mult: 2 },
    params: [
      { key: "period", label: "Period", type: "int", default: 20, min: 2, max: 100 },
      { key: "mult", label: "Multiplier", type: "float", default: 2, min: 0.5, max: 4 },
    ],
  },
];
