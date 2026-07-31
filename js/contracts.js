/*
Contracts for Phase 3 (Traceability) and Phase 4 (Backtesting) in the crypto research terminal.

This module defines lightweight JavaScript classes for:
- Signals: Research-to-chart traceability entities
- Trades: Backtest execution contracts
- Research Results: Combined results and generated signals

All contracts use Unix millisecond timestamps to ensure consistency across the system.
*/
(function(root) {

// ==============================================================================
// Phase 3 Contracts - Research to Chart Traceability
// ==============================================================================

/**
 * Signal Contract
 * 
 * Represents a single research-generated signal with full traceability.
 * Used for both real-time execution and historical research analysis.
 * 
 * @note All timestamps are Unix milliseconds for consistency with Lightweight Charts
 */
class Signal {
  constructor(
    timestamp,
    symbol,
    strategy,
    direction,
    strength,
    price,
    metadata,
    signalId,
    createdAt = Date.now()
  ) {
    this.timestamp = timestamp;
    this.symbol = symbol;
    this.strategy = strategy;
    this.direction = direction;
    this.strength = strength;
    this.price = price;
    this.metadata = metadata;
    this.signalId = signalId;
    this.createdAt = createdAt;
  }

  /**
   * Check if signal is still valid (within strategy cooldown)
   * 
   * @param cooldownMs - Strategy-specific cooldown in milliseconds
   * @returns true if signal hasn't expired
   */
  isValid(cooldownMs) {
    return Date.now() - this.timestamp < cooldownMs;
  }

  /**
   * Format signal for chart tooltip
   */
   formatForChart() {
     if (this.strategy == null) throw new Error('Signal.formatForChart: strategy is undefined');
     if (this.direction == null) throw new Error('Signal.formatForChart: direction is undefined');
     if (this.price == null) throw new Error('Signal.formatForChart: price is undefined');
     const timeStr = new Date(this.timestamp).toLocaleString();
     const strengthPercent = Math.round(this.strength * 100);
     return `${this.strategy} ${this.direction} (${strengthPercent}% confidence)\n` +
            `${timeStr}\nPrice: $${this.price.toLocaleString()}`;
   }

  /**
   * Determine chart marker color based on signal direction
   */
  getChartColor() {
    if (this.direction === 'BUY') return '#089981';
    if (this.direction === 'SELL') return '#F23645';
    throw new Error(`getChartColor: unrecognized direction "${this.direction}" — expected 'BUY' or 'SELL'`);
  }

  /**
   * Determine chart marker shape based on signal direction
   */
  getChartShape() {
    if (this.direction === 'BUY') return 'arrowUp';
    if (this.direction === 'SELL') return 'arrowDown';
    throw new Error(`getChartShape: unrecognized direction "${this.direction}" — expected 'BUY' or 'SELL'`);
  }

  /**
   * Convert signal to Lightweight Charts marker format
   */
   toChartMarker(timezone = 'UTC') {
     if (this.direction == null) throw new Error('Signal.toChartMarker: direction is undefined');
     if (this.strategy == null) throw new Error('Signal.toChartMarker: strategy is undefined');
     return {
       time: Math.round(this.timestamp / 1000), // Lightweight Charts expects seconds
       position: this.direction === 'BUY' ? 'belowBar' : 'aboveBar',
       color: this.getChartColor(),
       shape: this.getChartShape(),
       text: `${this.strategy.substring(0, 8)}${this.direction === 'BUY' ? 'B' : 'S'}`, // Truncated label
       title: this.formatForChart()
     };
   }
}

/**
 * Signal Metadata Contract
 * 
 * Strategy-specific context for a signal, including parameters used,
 * current indicators, and cross-validation results.
 */
class SignalMetadata {
  constructor(
    parameters,
    indicators,
    researchId,
    confidenceFactors,
    marketData
  ) {
    this.parameters = parameters;
    this.indicators = indicators;
    this.researchId = researchId;
    this.confidenceFactors = confidenceFactors;
    this.marketData = marketData;
  }

  /**
   * Get all indicators used for signal generation
   */
  getIndicatorNames() {
    return Object.keys(this.indicators);
  }

  /**
   * Check if signal has sufficient confidence
   */
  hasSufficientConfidence(minStrength) {
    return this.confidenceFactors.overall >= minStrength;
  }
}

/**
 * Confidence Factors for Signal
 * 
 * Breakdown of why a signal got its confidence score, for transparency
 * and explainability.
 */
class ConfidenceFactors {
  constructor(
    strength,
    consistency,
    volume,
    trend,
    overall
  ) {
    this.strength = strength;
    this.consistency = consistency;
    this.volume = volume;
    this.trend = trend;
    this.overall = overall;
  }

  /**
   * Calculate weighted overall score
   */
  static calculateWeighted(strength, consistency, volume, trend) {
    return strength * 0.4 + consistency * 0.2 + volume * 0.2 + trend * 0.2;
  }
}

/**
 * Market Snapshot at Signal Time
 * 
 * Current market state snapshot for reference and validation.
 */
class MarketSnapshot {
  constructor(
    price,
    volume,
    volatility,
    liquidity,
    trend,
    timestamp
  ) {
    this.price = price;
    this.volume = volume;
    this.volatility = volatility;
    this.liquidity = liquidity;
    this.trend = trend;
    this.timestamp = timestamp;
  }
}

/**
 * Backtest Trade Contract
 * 
 * Represents a completed trade from the backtesting engine, with exact
 * PnL calculation logic for auditability.
 */
class BacktestTrade {
   constructor(
     tradeId,
     symbol,
     direction,
     entryTime,
     exitTime,
     entryPrice,
     exitPrice,
     quantity,
     strategy,
     signalId,
     fees = 0,
     slippage = 0,
     metadata
   ) {
     if (exitTime !== undefined && entryTime !== undefined && exitTime <= entryTime) {
       throw new Error(`exitTime (${exitTime}) must be greater than entryTime (${entryTime})`);
     }
     this.tradeId = tradeId;
     this.symbol = symbol;
     this.direction = direction;
     this.entryTime = entryTime;
     this.exitTime = exitTime;
     this.entryPrice = entryPrice;
     this.exitPrice = exitPrice;
     this.quantity = quantity;
     this.strategy = strategy;
     this.signalId = signalId;
     this.fees = fees;
     this.slippage = slippage;
     this.metadata = metadata;
   }

  /**
   * Calculate position size based on portfolio and risk parameters.
   * Throws if riskAmount is zero (degenerate input — would produce a zero-size position).
   */
  static calculatePositionSize(
    portfolioValue,
    riskPercent,
    entryPrice,
    stopLossPrice,
    direction = 'LONG'
  ) {
    const riskAmount = portfolioValue * riskPercent;
    if (riskAmount === 0) {
      throw new Error('Cannot calculate position size: riskAmount is zero (zero portfolio value or zero risk percent)');
    }
    const priceRisk = direction === 'SHORT'
      ? stopLossPrice - entryPrice
      : entryPrice - stopLossPrice;
    if (priceRisk <= 0) throw new Error('Invalid stop loss price');
    return riskAmount / priceRisk;
  }

  /**
   * Calculate PnL with detailed breakdown.
   *
   * Fee convention: this.fees is a percentage (e.g. 0.1 = 0.1%) applied
   * per trade leg (entry and exit). This is distinct from
   * ExecutableSignal.executionFee which is a flat currency amount.
   * See ExecutableSignal.calculateExecutionPnL() for the flat-fee contract.
   */
  calculatePnL() {
    if (this.quantity === 0 || this.entryPrice === 0) {
      throw new Error("Cannot calculate PnL percentage: quantity and entryPrice must be non-zero");
    }
    const grossPnl = this.direction === 'LONG'
      ? (this.exitPrice - this.entryPrice) * this.quantity
      : (this.entryPrice - this.exitPrice) * this.quantity;

    const entryFee = this.entryPrice * this.quantity * (this.fees / 100);
    const exitFee = this.exitPrice * this.quantity * (this.fees / 100);
    const totalFees = entryFee + exitFee;
    const slippageCost = this.slippage * this.quantity;

    const netPnl = grossPnl - totalFees - slippageCost;
    const grossPnlPercent = (grossPnl / (this.entryPrice * this.quantity)) * 100;
    const netPnlPercent = (netPnl / (this.entryPrice * this.quantity)) * 100;

    return new PnLBreakdown(
      grossPnl,
      netPnl,
      grossPnlPercent,
      netPnlPercent,
      entryFee,
      exitFee,
      totalFees,
      slippageCost,
      this.quantity,
      this.entryPrice,
      this.exitPrice,
      this.direction
    );
  }

  /**
   * Format trade for display
   */
   formatForDisplay() {
     if (this.symbol == null) throw new Error('BacktestTrade.formatForDisplay: symbol is undefined');
     if (this.direction == null) throw new Error('BacktestTrade.formatForDisplay: direction is undefined');
     if (this.entryPrice == null) throw new Error('BacktestTrade.formatForDisplay: entryPrice is undefined');
     if (this.exitPrice == null) throw new Error('BacktestTrade.formatForDisplay: exitPrice is undefined');
     if (this.quantity == null) throw new Error('BacktestTrade.formatForDisplay: quantity is undefined');
     if (this.strategy == null) throw new Error('BacktestTrade.formatForDisplay: strategy is undefined');
     const entryTimeStr = new Date(this.entryTime).toLocaleString();
     const exitTimeStr = new Date(this.exitTime).toLocaleString();
     const pnlBreakdown = this.calculatePnL();

     return `
Trade: ${this.symbol} ${this.direction}
Entry: ${entryTimeStr} @ $${this.entryPrice.toLocaleString()}
Exit: ${exitTimeStr} @ $${this.exitPrice.toLocaleString()}
Qty: ${this.quantity.toLocaleString()}
PnL: $${pnlBreakdown.netPnl.toFixed(2)} (${pnlBreakdown.netPnlPercent.toFixed(2)}%)
Strategy: ${this.strategy}
`;
   }
}

/**
 * PnL Breakdown Contract
 * 
 * Detailed breakdown of a single trade's profit and loss calculation
 * to ensure mathematical accuracy and transparency.
 */
class PnLBreakdown {
  constructor(
    grossPnl,
    netPnl,
    grossPnlPercent,
    netPnlPercent,
    entryFee,
    exitFee,
    totalFees,
    slippageCost,
    quantity,
    entryPrice,
    exitPrice,
    direction
  ) {
    this.grossPnl = grossPnl;
    this.netPnl = netPnl;
    this.grossPnlPercent = grossPnlPercent;
    this.netPnlPercent = netPnlPercent;
    this.entryFee = entryFee;
    this.exitFee = exitFee;
    this.totalFees = totalFees;
    this.slippageCost = slippageCost;
    this.quantity = quantity;
    this.entryPrice = entryPrice;
    this.exitPrice = exitPrice;
    this.direction = direction;
  }

  /**
   * Validate PnL calculation mathematically
   */
  validateCalculation() {
    // Expected net PnL based on price difference per direction convention
    let expectedGross = (this.exitPrice - this.entryPrice) * this.quantity;
    if (this.direction === 'SHORT') {
      expectedGross = (this.entryPrice - this.exitPrice) * this.quantity;
    }

    const tolerance = 0.01; // 1 cent tolerance
    const grossOk = Math.abs(this.grossPnl - expectedGross) < tolerance;

    // netPnl must equal grossPnl minus all costs
    const netOk = Math.abs(this.netPnl - (this.grossPnl - this.totalFees - this.slippageCost)) < tolerance;

    // Fee breakdown must be internally consistent (entryFee + exitFee = totalFees)
    const feesOk = Math.abs((this.entryFee + this.exitFee) - this.totalFees) < tolerance;

    return grossOk && netOk && feesOk;
  }
}

/**
 * Research Result Contract
 * 
 * Complete output from strategy research including all generated signals,
 * performance metrics, and walk-forward validation details.
 */
class ResearchResult {
  constructor(
    runId,
    strategy,
    parameters,
    symbols,
    timeframe,
    inSampleResults,
    outOfSampleResults,
    totalTrades,
    totalSignals,
    signals,
    createdAt,
    decayRatio,
    confidenceScore
  ) {
    this.runId = runId;
    this.strategy = strategy;
    this.parameters = parameters;
    this.symbols = symbols;
    this.timeframe = timeframe;
    this.inSampleResults = inSampleResults;
    this.outOfSampleResults = outOfSampleResults;
    this.totalTrades = totalTrades;
    this.totalSignals = totalSignals;
    this.signals = signals;
    this.createdAt = createdAt;
    this.decayRatio = decayRatio;
    this.confidenceScore = confidenceScore;
  }

  /**
   * Get Sharpe decay percentage
   */
  getSharpeDecay() {
    if (this.decayRatio === undefined) return 0;
    return Math.round(this.decayRatio * 100);
  }

  /**
   * Check if strategy shows significant decay (overfitting indicator)
   */
  hasSignificantDecay(threshold = 0.3) {
    return this.decayRatio !== undefined && this.decayRatio > threshold;
  }

  /**
   * Format summary for research results display
   */
  formatSummary() {
    const inSampleSharpe = this.inSampleResults?.sharpeRatio?.toFixed(3) ?? 'N/A';
    const outOfSampleSharpe = this.outOfSampleResults?.sharpeRatio?.toFixed(3) ?? 'N/A';
    const totalBuy = this.signals ? this.signals.filter(s => s.direction === 'BUY').length : 0;
    const totalSell = this.signals ? this.signals.filter(s => s.direction === 'SELL').length : 0;
    return `
Strategy: ${this.strategy}
Parameters: ${JSON.stringify(this.parameters, null, 2)}
Symbols: ${this.symbols.join(', ')}
Timeframe: ${this.timeframe}
Total Trades: ${this.totalTrades}
Total Signals: ${this.totalSignals}
In-Sample Sharpe: ${inSampleSharpe}
Out-of-Sample Sharpe: ${outOfSampleSharpe}
Sharpe Decay: ${this.getSharpeDecay()}%
Confidence: ${Math.round(this.confidenceScore * 100)}%

Generated Signals Summary:
- Buy Signals: ${totalBuy}
- Sell Signals: ${totalSell}
`;
  }
}

/**
 * Performance Metrics Contract
 * 
 * Standardized performance metrics for research results, audit-ready.
 */
class PerformanceMetrics {
  constructor(
    sharpeRatio,
    totalReturnPct,
    maxDrawdownPct,
    winRate,
    profitFactor,
    avgTradePnl,
    avgHoldingBars,
    totalTrades,
    totalSignals,
    calmarRatio,
    sortinoRatio,
    recoveryFactor,
    avgWinPnl,
    avgLossPnl,
    largestWin,
    largestLoss,
    meanAbsoluteDeviation,
    tailRatio,
    painIndex,
    serenityIndex
  ) {
    this.sharpeRatio = sharpeRatio;
    this.totalReturnPct = totalReturnPct;
    this.maxDrawdownPct = maxDrawdownPct;
    this.winRate = winRate;
    this.profitFactor = profitFactor;
    this.avgTradePnl = avgTradePnl;
    this.avgHoldingBars = avgHoldingBars;
    this.totalTrades = totalTrades;
    this.totalSignals = totalSignals;
    this.calmarRatio = calmarRatio;
    this.sortinoRatio = sortinoRatio;
    this.recoveryFactor = recoveryFactor;
    this.avgWinPnl = avgWinPnl;
    this.avgLossPnl = avgLossPnl;
    this.largestWin = largestWin;
    this.largestLoss = largestLoss;
    this.meanAbsoluteDeviation = meanAbsoluteDeviation;
    this.tailRatio = tailRatio;
    this.painIndex = painIndex;
    this.serenityIndex = serenityIndex;
  }

  /**
   * Calculate additional derived metrics
   */
  getVolatilityAdjustedReturn() {
    const absDrawdown = Math.abs(this.maxDrawdownPct);
    const divisor = absDrawdown === 0 ? 0.001 : absDrawdown;
    return this.totalReturnPct / (divisor / 100);
  }

  /**
   * Determine if metrics are statistically significant at a given confidence level.
   * Uses a one-tailed z-test approximation: the critical z-value for the given
   * confidence level is compared against the absolute Sharpe ratio.
   *
   * Common z-scores: 90% → 1.28, 95% → 1.645, 99% → 2.33
   */
  isStatisticallySignificant(confidence = 0.95) {
    const zCritical = { 0.9: 1.28, 0.95: 1.645, 0.99: 2.33 };
    const zThreshold = zCritical[confidence] ?? 1.645;
    return this.totalTrades >= 30 && Math.abs(this.sharpeRatio) > zThreshold;
  }
}

/**
  * Trade Signal with Time Validation
  *
  * Specialized version of Signal for real-time execution with time-based
  * validity checks and execution ordering.
  *
  * @note Constructor parameter order mirrors Signal's: signalId is the 8th
  * positional argument (after metadata), followed by executionPrice and
  * executionFee. executionPrice and executionFee use flat currency units
  * (consistent with mark-to-market PnL), whereas BacktestTrade.fees is a
  * percentage applied per trade leg — see the fee-unit comments on
  * BacktestTrade.calculatePnL() and ExecutableSignal.calculateExecutionPnL().
  */
class ExecutableSignal extends Signal {
  constructor(
    timestamp,
    symbol,
    strategy,
    direction,
    strength,
    price,
    metadata,
    signalId,
    executionPrice,
    executionFee,
    createdAt = Date.now()
  ) {
    super(timestamp, symbol, strategy, direction, strength, price, metadata, signalId, createdAt);
    this._executed = false;
    this._executedAt = undefined;
    this.executionPrice = executionPrice;
    this.executionFee = executionFee;
    // If execution data was supplied at construction time, mark as already executed.
    if (executionPrice !== undefined && executionFee !== undefined) {
      this._executed = true;
      this._executedAt = Date.now();
    }
  }

  /**
   * Mark signal as executed
   */
  markAsExecuted(executionPrice, executionFee) {
    if (this._executed) {
      throw new Error(`Signal ${this.signalId || 'unknown'} already executed`);
    }
    this._executed = true;
    this._executedAt = Date.now();
    this.executionPrice = executionPrice;
    this.executionFee = executionFee;
  }

  /**
   * Check if signal is still pending execution
   */
  isPending() {
    return !this._executed;
  }

   /**
    * Calculate actual execution PnL.
    *
    * Fee convention: executionFee is a flat currency amount (not a
    * percentage). This differs from BacktestTrade.fees which is a
    * percentage applied per trade leg. See the fee-unit comments on
    * BacktestTrade.calculatePnL() for the percentage-based contract.
    */
   calculateExecutionPnL(quantity) {
     if (!this._executed || this.executionPrice === undefined) {
       throw new Error('Cannot calculate execution PnL for unexecuted signal');
     }

     const grossPnl = this.direction === 'BUY'
       ? (this.price - this.executionPrice) * quantity
       : (this.executionPrice - this.price) * quantity;

     return grossPnl - (this.executionFee || 0);
   }
}

// ==============================================================================
// Export All Types
// ==============================================================================

const api = {
  Signal,
  SignalMetadata,
  ConfidenceFactors,
  MarketSnapshot,
  BacktestTrade,
  PnLBreakdown,
  ResearchResult,
  PerformanceMetrics,
  ExecutableSignal
};

if (typeof module !== 'undefined' && module.exports) {
  module.exports = api;
}
if (root) {
  // Populate root.* from api to avoid duplicating class names.
  // Future class additions only need to be added to the `api` object.
  Object.keys(api).forEach((key) => { root[key] = api[key]; });
  root.Contracts = api;
}
})(typeof window !== 'undefined' ? window : globalThis);
