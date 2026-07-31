// =============================================================================
// Shared Strategy Signal Generators
// Pure functions — parse OHLCV data, return signal or null.
// No DOM, no engine coupling, no exchange dependency.
//   Input:  [{ time, open, high, low, close, volume }, ...]
//   Output: { action: 'enter_long' | 'exit_long', confidence: 0.65, strategy: 'id' }
//        or: null
// =============================================================================

// ---------- config ----------
// Centralized so thresholds/periods can't drift out of sync between the
// trigger condition and the confidence-scaling formula that uses it.

const RSI_PERIOD = 14;
const RSI_OVERSOLD = 28;   // enter_long trigger + confidence reference
const RSI_OVERBOUGHT = 72; // exit_long trigger + confidence reference

const BREAKOUT_ENTRY_LOOKBACK = 20;
const BREAKOUT_EXIT_LOOKBACK = 10;
const BREAKOUT_SMA_PERIOD = 20;
const ATR_PERIOD = 14;
// Confirmation distance above the SMA, expressed in ATRs rather than a fixed
// percentage. This is what makes the buffer self-scale to each asset's own
// volatility: 0.5 ATR is "meaningful" whether that asset typically moves
// 0.1%/day or 8%/day, whereas a fixed 1% buffer is not.
const BREAKOUT_ATR_CONFIRM_MULT = 0.5;

// Only the trailing WINDOW candles are ever needed by any strategy below.
// Bounding the slice keeps evaluation O(1) relative to total history size
// instead of remapping a buffer that may hold thousands of candles.
const MAX_LOOKBACK_WINDOW = 60;

// ---------- math helpers ----------

function calcRSI(closes, period = RSI_PERIOD) {
  if (!Array.isArray(closes) || closes.length < period + 1) return 50;
  const changes = [];
  for (let i = 1; i < closes.length; i++) {
    const current = closes[i];
    const prev = closes[i - 1];
    if (!Number.isFinite(current) || !Number.isFinite(prev)) return 50;
    changes.push(current - prev);
  }

  if (changes.length < period) return 50;

  let avgGain = 0;
  let avgLoss = 0;
  for (let i = 0; i < period; i++) {
    const change = changes[i];
    if (change >= 0) avgGain += change;
    else avgLoss += -change;
  }
  avgGain /= period;
  avgLoss /= period;

  // Flat market: no gains and no losses → neutral RSI, not maximally overbought
  if (avgGain === 0 && avgLoss === 0) return 50;
  if (avgLoss === 0) return 100;

  for (let i = period; i < changes.length; i++) {
    const change = changes[i];
    avgGain = ((avgGain * (period - 1)) + (change > 0 ? change : 0)) / period;
    avgLoss = ((avgLoss * (period - 1)) + (change < 0 ? -change : 0)) / period;
  }

  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

function calcSMA(closes, period) {
  const vals = closes.slice(-period);
  if (vals.length === 0) return NaN; // caller's responsibility to guard length beforehand
  return vals.reduce((s, v) => s + v, 0) / vals.length;
}

function calcHighest(highs, period) {
  if (!Array.isArray(highs) || highs.length === 0) return NaN;
  const start = Math.max(0, highs.length - period);
  let h = NaN;
  for (let i = start; i < highs.length; i++) {
    const value = highs[i];
    if (!Number.isFinite(value)) continue;
    if (Number.isNaN(h) || value > h) h = value;
  }
  return h;
}

function calcLowest(lows, period) {
  if (!Array.isArray(lows) || lows.length === 0) return NaN;
  const start = Math.max(0, lows.length - period);
  let l = NaN;
  for (let i = start; i < lows.length; i++) {
    const value = lows[i];
    if (!Number.isFinite(value)) continue;
    if (Number.isNaN(l) || value < l) l = value;
  }
  return l;
}

// Average True Range — asset-agnostic volatility measure, in the asset's
// own price units. candles must include a leading candle before the window
// so the first true-range calculation has a previous close to compare to.
function calcATR(candles, period = ATR_PERIOD) {
  if (candles.length < period + 1) return null;
  const trueRanges = [];
  for (let i = 1; i < candles.length; i++) {
    const cur = candles[i];
    const prevClose = candles[i - 1].close;
    const tr = Math.max(
      cur.high - cur.low,
      Math.abs(cur.high - prevClose),
      Math.abs(cur.low - prevClose),
    );
    trueRanges.push(tr);
  }
  const window = trueRanges.slice(-period);
  const atr = window.reduce((s, v) => s + v, 0) / window.length;
  return Number.isNaN(atr) ? null : atr;
}

// ---------- strategies ----------

/**
 * Buy-and-hold baseline: opens a single long on the first evaluation and never
 * exits. This is the critical reference point — any strategy must beat this
 * *net of costs* to demonstrate genuine edge rather than merely capturing the
 * market's constant drift. Returns a fresh evaluator per call (each run gets
 * its own "already entered" state).
 */
function createBuyAndHoldEvaluator() {
  let entered = false;
  return function evaluateBuyAndHold(candles) {
    if (entered) return null;
    entered = true;
    return { action: 'enter_long', confidence: 1, strategy: 'buy_and_hold' };
  };
}

function evaluateRSI(candles) {
  if (!Array.isArray(candles) || candles.length < 20) return null;
  // Bound the work: RSI only ever looks at the trailing period+1 closes.
  const window = candles.length > MAX_LOOKBACK_WINDOW ? candles.slice(-MAX_LOOKBACK_WINDOW) : candles;
  const isValid = window.every(c => c && Number.isFinite(c.close) && Number.isFinite(c.open) && Number.isFinite(c.high) && Number.isFinite(c.low));
  if (!isValid) return null;
  const closes = window.map(c => c.close);
  const rsi = calcRSI(closes, RSI_PERIOD);
  // Trigger thresholds and confidence-scaling reference the same constants,
  // so they can never silently drift apart.
  if (rsi < RSI_OVERSOLD) {
    return { action: 'enter_long', confidence: Math.min(1, (RSI_OVERSOLD - rsi) / 10), strategy: 'rsi_reversion' };
  }
  if (rsi > RSI_OVERBOUGHT) {
    return { action: 'exit_long', confidence: Math.min(1, (rsi - RSI_OVERBOUGHT) / 10), strategy: 'rsi_reversion' };
  }
  return null;
}

function evaluateBreakout(candles) {
  // Need 1 current candle + enough lookback history behind it (ATR needs
  // one extra leading candle for its first true-range comparison).
  const minRequired = Math.max(BREAKOUT_ENTRY_LOOKBACK, BREAKOUT_SMA_PERIOD, ATR_PERIOD + 1) + 1;
  if (!Array.isArray(candles) || candles.length < minRequired) return null;

  // Bound the work before slicing off the current candle.
  const window = candles.length > MAX_LOOKBACK_WINDOW ? candles.slice(-MAX_LOOKBACK_WINDOW) : candles;
  const isValid = window.every(c => c && Number.isFinite(c.close) && Number.isFinite(c.open) && Number.isFinite(c.high) && Number.isFinite(c.low));
  if (!isValid) return null;
  const current = window[window.length - 1].close;

  // Exclude the current/last candle from the lookback windows so the
  // conditions are reachable — a candle's own high/low can never breach
  // its own boundaries.
  const history = window.slice(0, -1);
  const closes = history.map(c => c.close);
  const highs = history.map(c => c.high);
  const lows = history.map(c => c.low);
  if (closes.length < BREAKOUT_SMA_PERIOD) return null;

  const entryHigh = calcHighest(highs, BREAKOUT_ENTRY_LOOKBACK);
  const exitLow = calcLowest(lows, BREAKOUT_EXIT_LOOKBACK);
  const sma20 = calcSMA(closes, BREAKOUT_SMA_PERIOD);
  const atr = calcATR(history, ATR_PERIOD);
  if (atr === null || atr === 0) return null; // not enough history, or a dead/flat feed

  // Confirmation buffer is ATR-scaled instead of a fixed percentage, so the
  // "how far above the SMA counts as a real breakout" question self-adjusts
  // to each asset's own volatility rather than a value tuned for one asset.
  const confirmLevel = sma20 + atr * BREAKOUT_ATR_CONFIRM_MULT;

  if (current > entryHigh && current > confirmLevel) {
    // Confidence scales with how many ATRs past confirmation the breakout is,
    // capped at 1 — a break that clears the level by 2 ATRs is a stronger
    // signal than one that barely ticks over it, regardless of asset.
    const strength = (current - confirmLevel) / atr;
    return { action: 'enter_long', confidence: Math.min(1, 0.5 + strength * 0.25), strategy: 'breakout_hunter' };
  }
  if (current < exitLow) {
    const strength = (exitLow - current) / atr;
    return { action: 'exit_long', confidence: Math.min(1, 0.5 + strength * 0.25), strategy: 'breakout_hunter' };
  }
  return null;
}

// ---- Node export (for headless backtest validation in CI/CLI) ----
if (typeof module !== 'undefined' && module.exports) {
  module.exports = {
    createBuyAndHoldEvaluator,
    evaluateBreakout,
    evaluateRSI,
    calcRSI,
    calcSMA,
    calcATR,
    calcHighest,
    calcLowest,
  };
}