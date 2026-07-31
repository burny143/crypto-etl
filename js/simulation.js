// =============================================================================
// Synthetic Market Generator (GBM + fat tails) — fully client-side
// =============================================================================

// In the browser, strategies.js is loaded via a <script> tag before this file,
// so its functions are globals. Under Node (headless validation) we load it
// explicitly and re-expose the same names as globals to keep both paths equal.
if (typeof module !== 'undefined' && module.exports) {
  const strategies = require('./strategies.js');
  global.createBuyAndHoldEvaluator = strategies.createBuyAndHoldEvaluator;
  global.evaluateBreakout = strategies.evaluateBreakout;
  global.evaluateRSI = strategies.evaluateRSI;
}

/** Small dependency-free seeded PRNG (mulberry32). Deterministic per seed. */
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

class SyntheticMarket {
  constructor(basePrice = 100, volatility = 0.02, drift = 0.0004, realismOptions = null, seed = null) {
    this.price = basePrice;
    this.prevClose = basePrice;
    this.basePrice = basePrice;
    this.volatility = volatility;
    this.drift = drift;
    // Seeded RNG: deterministic runs per seed; null seed = non-deterministic
    this.seed = (seed === null || seed === undefined) ? (Date.now() ^ (Math.random() * 0xffffffff)) >>> 0 : seed >>> 0;
    this._rng = mulberry32(this.seed);
    this.candleBuffer = [];
    // prices24h stores { time, price } objects so the cutoff filter
    // operates on the time field, not price values.
    this.prices24h = [];
    this.maxBuffer = 10000;
    this._timeCounter = 0;
    // Base timestamp so chart displays sensible real-world times. The -500
    // offset lets the 500 preSeeded candles land in the recent past so the
    // chart ends near "now" on first load — shared with reset() so the two
    // can never drift apart again.
    this._epochStart = this._computeEpochStart();

    // ---------------------------------------------------------------------
    // Realism layer (off by default = legacy fixed-parameter GBM exactly).
    // Each feature is independently toggleable; enabling the layer only
    // activates the features whose flags are true.
    // ---------------------------------------------------------------------
    const r = realismOptions || {};

    // Resolve GARCH alpha/beta into locals FIRST so omega's default can be
    // derived from the actually-resolved values. A literal (1 - 0.1 - 0.85)
    // here would silently desync the long-run variance target whenever a
    // caller overrides alpha/beta without also passing omega.
    // NOTE: all of these use explicit !== undefined checks (matching
    // momentumWeight below) so an explicit 0 is honored, not swallowed by ||
    // fallback — e.g. volumeCoupling.strength: 0 is the documented way to
    // disable volume coupling, and must not silently become the default 8.
    const resolvedAlpha = (r.garch && r.garch.alpha !== undefined) ? r.garch.alpha : 0.1;
    const resolvedBeta = (r.garch && r.garch.beta !== undefined) ? r.garch.beta : 0.85;
    const resolvedOmega = (r.garch && r.garch.omega !== undefined)
      ? r.garch.omega
      : (1 - resolvedAlpha - resolvedBeta) * volatility * volatility;

    this.realism = {
      enabled: !!r.enabled,
      // GARCH(1,1): sigma_t^2 = omega + alpha*eps_{t-1}^2 + beta*sigma_{t-1}^2
      // alpha + beta < 1 keeps the process stationary. omega defaults to the
      // value whose long-run variance equals the base volatility^2:
      //   omega = (1 - alpha - beta) * volatility^2
      garch: {
        alpha: resolvedAlpha,
        beta: resolvedBeta,
        omega: resolvedOmega,
        minSigma: (r.garch && r.garch.minSigma !== undefined) ? r.garch.minSigma : volatility * 0.25,
        maxSigma: (r.garch && r.garch.maxSigma !== undefined) ? r.garch.maxSigma : volatility * 4,
      },
      // Fraction of the previous tick's log-return blended into this tick's
      // drift (weak momentum/autocorrelation). 0 disables.
      momentumWeight: (r.momentumWeight !== undefined) ? r.momentumWeight : 0.1,
      // Volume scales with |log-return| / sigma_t. strength > 0 enables.
      volumeCoupling: {
        strength: (r.volumeCoupling && r.volumeCoupling.strength !== undefined) ? r.volumeCoupling.strength : 8,
      },
    };

    // Running stochastic-volatility state
    this.sigma = volatility;       // current sigma_t
    this.sigmaSq = volatility * volatility;
    this.prevEpsilon = 0;          // last standardized shock (for GARCH)
    this.prevReturn = 0;           // last log-return (for momentum)

    // When true, reset() redraws drift/GARCH/momentum parameters so a bot
    // can't overfit to one fixed regime (domain randomization).
    this.randomizeOnReset = false;

    // Headless batch mode: skips the 24h window tracking (UI-only) so long
    // seeded backtest sweeps run in O(1) per tick instead of O(window).
    this.batchMode = false;
  }

  /** Toggle the realism layer (applies from the next tick onward). */
  setRealism(enabled) {
    this.realism.enabled = !!enabled;
    if (this.realism.enabled) this._initVolState();
  }

  /** Shared epoch base used by both the constructor and reset(). */
  _computeEpochStart() {
    return Math.floor(Date.now() / 1000) - 500;
  }

  _initVolState() {
    this.sigma = this.volatility;
    this.sigmaSq = this.volatility * this.volatility;
    this.prevEpsilon = 0;
    this.prevReturn = 0;
  }

  /**
   * Redraw regime parameters within reasonable ranges — call before the
   * start of a run when "randomize regime" is enabled.
   */
  randomizeParams() {
    this.drift = (this._rng() - 0.5) * 0.002; // ±0.1% per tick

    const g = this.realism.garch;
    // Keep alpha + beta < 1 (stationarity)
    g.alpha = 0.05 + this._rng() * 0.1;            // 0.05–0.15
    g.beta = 0.70 + this._rng() * 0.25;            // 0.70–0.95
    if (g.alpha + g.beta >= 1) g.alpha = 1 - g.beta - 0.02;
    // Long-run variance wobbles around base vol^2
    g.omega = (1 - g.alpha - g.beta) * this.volatility * this.volatility * (0.5 + this._rng());

    this.realism.momentumWeight = 0.05 + this._rng() * 0.10; // 5–15%
    this._initVolState();
  }

  _tSample(df = 3) {
    // z is just a standard normal — reuse _gauss() instead of duplicating the
    // Box-Muller formula inline. Draw order must stay (z first, then the df
    // chi-square draws) to keep seeded runs bit-identical to before.
    const z = this._gauss();
    let chi2 = 0;
    for (let i = 0; i < df; i++) chi2 += this._gauss() ** 2;
    return z / Math.sqrt(chi2 / df);
  }

  _gauss() {
    const u1 = Math.max(Number.MIN_VALUE, this._rng());
    const u2 = this._rng();
    return Math.sqrt(-2 * Math.log(u1)) * Math.cos(2 * Math.PI * u2);
  }

  _gbmShock() {
    const epsilon = this._rng() < 0.05 ? this._tSample(3) : this._gauss();
    return Math.exp(this.drift + this.volatility * epsilon);
  }

  /**
   * Realism-mode return generator: GARCH(1,1) stochastic volatility +
   * weak momentum carryover. Returns the multiplier to apply to price.
   */
  _gbmShockRealism() {
    const g = this.realism.garch;

    // GARCH(1,1) update: sigma_t^2 = omega + alpha*eps_{t-1}^2 + beta*sigma_{t-1}^2
    this.sigmaSq = g.omega + g.alpha * (this.prevEpsilon * this.prevEpsilon) + g.beta * this.sigmaSq;
    this.sigma = Math.sqrt(this.sigmaSq);
    // Clamp to sane floor/ceiling so the price path can't go hyperbolic
    this.sigma = Math.min(g.maxSigma, Math.max(g.minSigma, this.sigma));

    const epsilon = this._rng() < 0.05 ? this._tSample(3) : this._gauss();
    // Weak momentum: blend a fraction of the previous tick's return into drift
    const effectiveDrift = this.drift + this.realism.momentumWeight * this.prevReturn;
    const ret = effectiveDrift + this.sigma * epsilon;

    this.prevEpsilon = epsilon;
    this.prevReturn = ret;
    return Math.exp(ret);
  }

  tick() {
    this._timeCounter++;
    // Unix-timestamp-like: base + tick offset, monotonically increasing
    const now = this._epochStart + this._timeCounter;

    const shock = this.realism.enabled ? this._gbmShockRealism() : this._gbmShock();
    this.price *= shock;
    this.price = Math.max(this.price, this.basePrice * 0.1);
    this.price = Math.min(this.price, this.basePrice * 10);

    const spread = this.price * 0.001;
    const high = Math.max(this.price + spread * this._rng(), this.prevClose, this.price);
    const low = Math.min(this.price - spread * this._rng(), this.prevClose, this.price);

    // Volume: legacy mode is independent noise. Realism mode scales volume
    // with the magnitude of this tick's move relative to current volatility,
    // so volume carries genuine signal (big moves → big volume).
    let volume = 100 + this._rng() * 9900;
    if (this.realism.enabled && this.realism.volumeCoupling.strength > 0) {
      const absRet = Math.abs(Math.log(this.price / this.prevClose));
      const relMove = absRet / Math.max(this.sigma, 1e-9);
      volume *= 1 + this.realism.volumeCoupling.strength * relMove;
    }

    const candle = {
      time: now,
      open: parseFloat(this.prevClose.toFixed(4)),
      high: parseFloat(high.toFixed(4)),
      low: parseFloat(low.toFixed(4)),
      close: parseFloat(this.price.toFixed(4)),
      volume: parseFloat(volume.toFixed(2)),
    };

    this.candleBuffer.push(candle);
    // Amortized buffer trim: slice() copies the whole array, so trimming on
    // every tick once the buffer is full is O(ticks × maxBuffer). Instead,
    // let the buffer grow to maxBuffer * 1.1 and trim back to maxBuffer in
    // one slice — the cost is amortized across many ticks (O(1) per tick on
    // average), which keeps long headless runs (ticks > maxBuffer) fast.
    // Nothing reads the buffer between trims in a way that depends on its
    // exact length: strategy slices use slice(-50), the 24h volume window
    // slices the full buffer, and the chart just renders whatever is there.
    if (this.candleBuffer.length > this.maxBuffer * 1.1) {
      this.candleBuffer = this.candleBuffer.slice(-this.maxBuffer);
    }
    this.prevClose = this.price;

    if (this.batchMode) {
      // Headless batch runs don't need the 24h window (UI-only). Skipping it
      // keeps each tick O(1) so long seeded sweeps finish quickly.
      return { candle, state: { price: this.price, high24: this.price, low24: this.price, change24: 0, volume24: 0, timestamp: now } };
    }

    // Store { time, price } pairs so filter operates on the time field.
    this.prices24h.push({ time: now, price: this.price });
    const cutoff = now - 86400;
    this.prices24h = this.prices24h.filter(p => p.time >= cutoff);
    // Manual reduce to avoid spread-on-large-array stack overflow.
    let high24 = this.price, low24 = this.price;
    for (const p of this.prices24h) {
      if (p.price > high24) high24 = p.price;
      if (p.price < low24) low24 = p.price;
    }
    const change24 = this.prices24h.length > 1
      ? ((this.price - this.prices24h[0].price) / this.prices24h[0].price) * 100 : 0;

    // True 24h volume window (86400 simulated seconds = 86400 ticks)
    const vol24 = this.candleBuffer.slice(-86400).reduce((s, c) => s + c.volume, 0);

    return { candle, state: { price: this.price, high24, low24, change24, volume24: vol24, timestamp: now } };
  }

  reset() {
    if (this.randomizeOnReset) this.randomizeParams();
    this._initVolState();
    this.price = this.basePrice;
    this.prevClose = this.basePrice;
    this.candleBuffer = [];
    this.prices24h = [];
    this._timeCounter = 0;
    this._epochStart = this._computeEpochStart();
  }
}

// =============================================================================
// Portfolio — cash, positions, PnL
// =============================================================================

class Portfolio {
  /**
   * @param {number} cash            starting cash
   * @param {number} feeRate         proportional fee per fill (0.001 = 10 bps)
   * @param {number} slippageBps     adverse fill slippage in basis points (5 = 5 bps)
   * @param {number} maxPositionPct  hard cap on single-position risk as a
   *                                 fraction of CURRENT equity (0.15 = 15%).
   *                                 Sizing is bounded to a fraction of initial
   *                                 cash, and this cap keeps it from ever
   *                                 exceeding a fixed share of the live
   *                                 account, even after the account grows.
   * @param {number} volumeSlippageK participation multiplier for volume-aware
   *                                 slippage (see effectiveSlippageBps).
   */
  constructor(cash = 10000, feeRate = 0.001, slippageBps = 5, maxPositionPct = 0.15, volumeSlippageK = 50) {
    this.cash = cash;
    this.initialCash = cash; // retained for the incremental baseline calc
    this.feeRate = feeRate;
    this.slippageBps = slippageBps;
    this.maxPositionPct = maxPositionPct;
    this.volumeSlippageK = volumeSlippageK;
    this.positions = [];
    this.trades = [];
    this.totalTrades = 0;
    this.totalFeesPaid = 0;
    // Running win/loss counters, independent of the trades display array.
    // The trades array is capped at 100 entries for the UI's recent-trades
    // table, so filtering IT for winRate would silently truncate the stat on
    // any run with more than ~50 round trips. These counters are updated on
    // every close regardless of the cap, so batch winRate stays exact.
    this.closedTradesCount = 0;
    this.winningTradesCount = 0;
    // Running realized PnL (net of entry+exit fees) — exact regardless of the
    // 100-entry UI trades-array cap. Feeds the Stop-button trade summary.
    this.totalRealizedPnl = 0;
    // Per-strategy running counters: { [strategyId]: { entries, exits,
    // closed, wins, pnl } }. Same rationale as the win-rate counters — the
    // trades display array truncates at 100 entries, so per-strategy stats
    // from it would silently undercount on any run with >50 round trips.
    this.strategyStats = {};
  }

  hasPosition(side) {
    return this.positions.some(p => p.side === side);
  }

  /**
   * Slippage in bps for an order of `orderNotional` dollars against a candle
   * of `volume` units at `price`. Scales the base slippage up when the order
   * is large relative to the candle's dollar volume (participation), which is
   * how a big order moves the market:
   *   effective = base * (1 + k * orderNotional / (volume * price))
   * Falls back to the flat base slippage when volume data isn't provided, so
   * callers that don't wire volume through keep the fixed-bps behavior.
   */
  effectiveSlippageBps(orderNotional, price, volume) {
    if (!(this.volumeSlippageK > 0) || !volume || volume <= 0 || !price || price <= 0) {
      return this.slippageBps;
    }
    const dollarVolume = volume * price;
    if (!(dollarVolume > 0)) return this.slippageBps;
    const participation = orderNotional / dollarVolume;
    return this.slippageBps * (1 + this.volumeSlippageK * participation);
  }

  /**
   * Fill price including slippage — always adverse to the trader:
   * long entry fills above quote, long exit fills below quote,
   * short entry fills below quote, short exit fills above quote.
   * orderNotional + volume feed volume-aware slippage (effectiveSlippageBps).
   */
  _slippedPrice(quotePrice, side, isEntry, orderNotional = 0, volume = null) {
    const slip = quotePrice * (this.effectiveSlippageBps(orderNotional, quotePrice, volume) / 10000);
    if (side === 'long') return isEntry ? quotePrice + slip : quotePrice - slip;
    return isEntry ? quotePrice - slip : quotePrice + slip;
  }

  /**
   * Bounded entry sizing shared by the live signal path (_processSignal) and
   * the incremental buy-and-hold baseline (_refreshBaseline) so both stay
   * bit-identical. Two guards:
   *   1. Size off INITIAL cash (non-compounding): qty risks only
   *      `sizeFraction` of the original stake, never the growing balance.
   *   2. Hard cap: fill notional never exceeds `maxPositionPct` of current
   *      equity, so exposure can't balloon even after the account grows.
   * @param {number} price          quote price at fill
   * @param {number|null} volume    candle volume for volume-aware slippage
   * @param {number} confidence     0..1 signal strength (sizeFraction 5–15%)
   * @param {number|null} capEquity equity to apply the maxPositionPct cap
   *                                against; defaults to live total equity.
   * @returns {number} quantity to request, or 0 to skip the trade.
   */
  computeEntrySize(price, volume, confidence, capEquity = null) {
    const sizeFraction = 0.05 + confidence * 0.10; // 5%–15% of INITIAL cash
    let qty = parseFloat((this.initialCash * sizeFraction / price).toFixed(4));
    if (qty <= 0) return 0;
    const orderNotional = qty * price;
    const estFill = this._slippedPrice(price, 'long', true, orderNotional, volume);
    const capNotional = (capEquity === null ? this.totalEquity(price) : capEquity) * this.maxPositionPct;
    if (qty * estFill > capNotional) {
      // Floor (not round) to 4 decimals so the cap is never breached by
      // rounding up: qty * fillPrice <= maxPositionPct * equity holds
      // exactly for every fill.
      qty = Math.floor((capNotional / estFill) * 10000) / 10000;
    }
    return qty > 0 ? qty : 0;
  }

  /**
   * Opens a position at the slippage-adjusted fill price, deducts fill cost
   * + fee from cash. Returns { fillPrice, fee } so callers can report them,
   * or null if the true total cost (quantity × fillPrice + fee) exceeds
   * available cash — the sized quantity is never affordable after adverse
   * slippage and fees, so the entry is rejected rather than silently
   * downsized (a partial fill would hide what actually executed).
   */
  openPosition(side, quantity, quotePrice, strategyId, volume = null) {
    const orderNotional = quantity * quotePrice;
    const fillPrice = this._slippedPrice(quotePrice, side, true, orderNotional, volume);
    const fee = this.feeRate * quantity * fillPrice;
    const totalCost = quantity * fillPrice + fee;
    if (totalCost > this.cash + 1e-9) return null; // guard vs float dust
    this.cash -= totalCost;
    this.totalFeesPaid += fee;
    this.positions.push({
      side, quantity, entryPrice: fillPrice, strategyId, entryFee: fee, unrealizedPnl: 0,
    });
    // Per-strategy entry counter (trade summary).
    const sid = strategyId || 'unknown';
    if (!this.strategyStats[sid]) this.strategyStats[sid] = { entries: 0, exits: 0, closed: 0, wins: 0, pnl: 0 };
    this.strategyStats[sid].entries++;
    return { fillPrice, fee };
  }

    /**
     * Closes the position at the slippage-adjusted fill price, credits cash
     * minus exit fee, and returns { pnl, grossPnl, fillPrice, quantity,
     * entryPrice, fee, strategyId } where pnl is net of entry+exit fees — or null if no
     * matching position exists.
     */
   closePosition(side, quotePrice, volume = null) {
     const idx = this.positions.findIndex(p => p.side === side);
     if (idx === -1) return null;
     const pos = this.positions[idx];
     const orderNotional = pos.quantity * quotePrice;
     const fillPrice = this._slippedPrice(quotePrice, side, false, orderNotional, volume);
     const fee = this.feeRate * pos.quantity * fillPrice;
     const grossPnl = side === 'long'
       ? (fillPrice - pos.entryPrice) * pos.quantity
       : (pos.entryPrice - fillPrice) * pos.quantity;
     const pnl = grossPnl - pos.entryFee - fee; // net of both fills' fees
     this.cash += pos.quantity * fillPrice - fee;
     this.totalFeesPaid += fee;
     // Update running win/loss counters regardless of the display-array cap,
     // so batch winRate statistics never get truncated by the 100-entry UI cap.
     this.closedTradesCount++;
     if (pnl > 0) this.winningTradesCount++;
     // Running realized PnL + per-strategy stats (trade summary).
     this.totalRealizedPnl += pnl;
     const sid = pos.strategyId || 'unknown';
     if (!this.strategyStats[sid]) this.strategyStats[sid] = { entries: 0, exits: 0, closed: 0, wins: 0, pnl: 0 };
     this.strategyStats[sid].exits++;
     this.strategyStats[sid].closed++;
     this.strategyStats[sid].pnl += pnl;
     if (pnl > 0) this.strategyStats[sid].wins++;
     const result = { pnl, grossPnl, fillPrice, quantity: pos.quantity, entryPrice: pos.entryPrice, fee, strategyId: pos.strategyId };
     this.positions.splice(idx, 1);
     return result;
   }

  updatePrices(currentPrice) {
    for (const pos of this.positions) {
      const gross = pos.side === 'long'
        ? (currentPrice - pos.entryPrice) * pos.quantity
        : (pos.entryPrice - currentPrice) * pos.quantity;
      pos.unrealizedPnl = gross - pos.entryFee; // reflect entry fee already paid
    }
  }

  totalEquity(currentPrice) {
    let positionValue = 0;
    for (const pos of this.positions) {
      positionValue += pos.quantity * currentPrice;
    }
    return this.cash + positionValue;
  }

  reset() {
    // Honor the cash the instance was actually constructed with, not a
    // hardcoded default — a Portfolio built with a different starting
    // balance would otherwise silently "reset" to $10,000.
    this.cash = this.initialCash;
    this.positions = [];
    this.trades = [];
    this.totalTrades = 0;
    this.totalFeesPaid = 0;
    this.closedTradesCount = 0;
    this.winningTradesCount = 0;
    this.totalRealizedPnl = 0;
    this.strategyStats = {};
  }
}

// =============================================================================
// Simulation Engine
// Strategy evaluators loaded from shared strategies.js
// =============================================================================

// Registry of signal-generator *factories* available to the bot. The UI
// dropdown selects which one(s) drive trading. Entries are factories because
// buy_and_hold is stateful (it needs a fresh "already entered" flag per run);
// the engine calls .create() once per run to get a clean evaluator.
const STRATEGY_REGISTRY = {
  breakout_hunter: { create: () => evaluateBreakout },
  rsi_reversion: { create: () => evaluateRSI },
  buy_and_hold: { create: createBuyAndHoldEvaluator },
};

// Strategies that actually trade. buy_and_hold is excluded from the "all"
// option: it enters once and never exits, so combining it with trading
// strategies would permanently block their entries (single position slot).
const TRADING_STRATEGY_IDS = ['breakout_hunter', 'rsi_reversion'];

// Realistic trading costs — configurable per asset class (crypto: 10bps fee,
// 5bps slippage; stocks would typically use much lower values). Single source
// of truth shared by the live-UI portfolio (constructor) and the headless
// backtest portfolio (runHeadless) so the two can never silently diverge —
// the parity the code promises depends on both using identical costs.
const TRADING_COSTS = { feeRate: 0.001, slippageBps: 5 };

class SimulationEngine {
  constructor() {
    this.market = new SyntheticMarket(100, 0.02, 0.0004, { enabled: false });
    this.portfolio = new Portfolio(10000, TRADING_COSTS.feeRate, TRADING_COSTS.slippageBps);
    this.running = false;
    this.timer = null;
    this.startTime = 0;
    this.candlesGenerated = 0;
    this.speed = 10;
    this.lastTickTime = 0;
    this.preSeedDone = false;
    this._chartDataLoaded = false;
    // Recent-trades sort state (default: newest first)
    this.tradeSort = { key: 'time', dir: -1 };
    // Active strategy set — default to the breakout-focused strategy only.
    this.activeStrategies = ['breakout_hunter'];
    // Fresh evaluator instances for the active strategies (built per run so
    // stateful strategies like buy_and_hold never leak state between runs).
    this._evaluators = {};
    this._buildEvaluators();
    // Same-seed buy-and-hold baseline comparison for the live UI run.
    // The buy-and-hold signal fires on the first strategy-eval tick and —
    // under the one-tick execution-lag model — fills on the NEXT candle's
    // open. Equity is then marked to the live price incrementally — no
    // re-simulation ever.
    this._baselineReturnPct = 0;
    this._baselineEntryPrice = null;
    this._baselineEntryVolume = null;
    this._baselineEntryPending = false;
    this._baselineTicks = 0;
    // Execution-lag queue: signals evaluated on candle N are filled on candle
    // N+1 at its open (see _queueSignal / _fillPendingSignals). Keyed by
    // strategy id; at most one pending signal per strategy.
    this._pendingSignals = {};
    // Headless (no DOM) mode — used by the batch backtester.
    this.headless = false;
  }

  /** Instantiate fresh evaluators from the active strategy set. */
  _buildEvaluators() {
    this._evaluators = {};
    for (const id of this.activeStrategies) {
      const entry = STRATEGY_REGISTRY[id];
      if (entry) this._evaluators[id] = entry.create();
    }
  }

  preSeed(count = 500) {
    if (this.preSeedDone) return;
    for (let i = 0; i < count; i++) this.market.tick();
    this.preSeedDone = true;
  }

  start(speed) {
    if (this.running) return;
    this.running = true;
    this.startTime = Date.now();
    this.speed = speed || this.speed;
    this.preSeed(500);
    this.lastTickTime = performance.now() - 1000 / this.speed;
    this._chartDataLoaded = false;
    this._updateUI(true);
    this._scheduleTick();
  }

  stop() {
    this.running = false;
    if (this.timer) { cancelAnimationFrame(this.timer); this.timer = null; }
    this._updateUI(false);
  }

  reset() {
    this.stop();
    this.market.reset();
    this.portfolio.reset();
    this.candlesGenerated = 0;
    this.preSeedDone = false;
    this.startTime = 0;
    this._chartDataLoaded = false;
    this._baselineReturnPct = 0;
    this._baselineEntryPrice = null;
    this._baselineEntryVolume = null;
    this._baselineEntryPending = false;
    this._baselineTicks = 0;
    this._pendingSignals = {};
    this._buildEvaluators();
  }

  /** Single-point reset of all display fields (no inline DOM in event handlers). */
  resetUI() {
    this._renderTrades();
    document.getElementById('uptimeDisplay').textContent = '';
    document.getElementById('priceDisplay').textContent = '100.00';
    document.getElementById('priceDisplay').className = 'price-value';
    document.getElementById('cashDisplay').textContent = '10000.00';
    document.getElementById('equityDisplay').textContent = '10000.00';
    document.getElementById('pnlDisplay').textContent = '0.00';
    document.getElementById('pnlDisplay').className = 'stat-value';
    document.getElementById('returnDisplay').textContent = '0.00%';
    document.getElementById('returnDisplay').className = 'stat-value';
    const baselineEl = document.getElementById('baselineDisplay');
    if (baselineEl) baselineEl.textContent = '0.00%';
    const alphaEl = document.getElementById('alphaDisplay');
    if (alphaEl) alphaEl.textContent = '0.00%';
    this._baselineReturnPct = 0;
    this._baselineEntryPrice = null;
    this._baselineEntryVolume = null;
    this._baselineEntryPending = false;
    this._baselineTicks = 0;
    document.getElementById('changeDisplay').textContent = '0.00%';
    document.getElementById('positionsCount').textContent = '0';
    document.getElementById('tradesCount').textContent = '0';
    document.getElementById('feesDisplay').textContent = '0.00';
    document.getElementById('positionsContainer').innerHTML = '<div class="positions-empty">No open positions</div>';
  }

  _updateUI(running) {
    const dot = document.getElementById('statusDot');
    if (!dot) return;
    dot.className = 'status-dot ' + (running ? 'running' : 'stopped');
    document.getElementById('statusLabel').textContent = running ? 'Running' : 'Stopped';
    document.getElementById('btnStart').disabled = running;
    document.getElementById('btnStop').disabled = !running;
  }

  _scheduleTick() {
    if (!this.running) return;
    // Speed is controlled solely by the throttle interval — _tick() runs
    // exactly one simulated tick per invocation.
    const interval = 1000 / this.speed;
    const now = performance.now();
    const elapsed = now - this.lastTickTime;
    if (elapsed >= interval) {
      this.lastTickTime = now - (elapsed % interval);
      this._tick();
    }
    this.timer = requestAnimationFrame(() => this._scheduleTick());
  }

  _tick() {
    this._doTick();
  }

  /**
   * Advance one simulated tick — pure logic, no DOM. Shared by the live
   * render loop (_doTick) and the headless batch backtester so both paths
   * evaluate and execute identically.
   *
   * Execution model (one-tick lag): signals are EVALUATED on candle N's close
   * and queued; they FILL on candle N+1 at that candle's OPEN. This mirrors
   * real markets where a signal computed at the close of a bar can only be
   * acted on at the next bar's auction/open — zero-latency same-bar fills
   * would be unrealistic and would leak lookahead bias into backtests.
   */
  _step() {
    const { candle, state } = this.market.tick();
    this.candlesGenerated++;
    const price = candle.close;

    // 1) Fill signals queued by the previous candle's evaluation at THIS
    //    candle's open (execution lag — see _fillPendingSignals).
    this._fillPendingSignals(candle);

    // 2) Evaluate active strategies on a fixed simulated-candle cadence
    //    (every 5 ticks) independent of playback speed, so signal generation
    //    is deterministic and reproducible regardless of the selected speed.
    //    Signals are queued, not filled here — they fill on the next tick.
    if (this.candlesGenerated % 5 === 0 && this.market.candleBuffer.length >= 30) {
      // Buy-and-hold baseline (live UI only — headless runs get their own
      // baseline path): its signal fires on this eval tick, and under the
      // one-tick-lag model its fill happens on the NEXT candle's open. Mark
      // the entry pending so _fillPendingSignals captures that open for us —
      // keeping baseline execution identical to strategy execution.
      if (!this.headless && this._baselineEntryPrice === null && !this._baselineEntryPending) {
        this._baselineEntryPending = true;
      }
      // Feed evaluators the full lookback window they are guaranteed by
      // strategies.js's MAX_LOOKBACK_WINDOW (60). Supplying fewer would
      // silently starve a strategy that (after future tuning) needs more
      // candles than the slice provides — keep the two in lockstep.
      const slice = this.market.candleBuffer.slice(-60);
      for (const id of this.activeStrategies) {
        const evaluator = this._evaluators[id];
        if (!evaluator) continue;
        const sig = evaluator(slice);
        if (sig) this._queueSignal(id, sig);
      }
    }

    this.portfolio.updatePrices(price);
    return { candle, state, price };
  }

  _doTick() {
    const { candle, state } = this._step();
    this._render(candle, state);
  }

  /**
   * Queue a signal for execution on the next candle. At most one pending
   * signal per strategy: evaluations run every 5 ticks and the queue drains
   * every tick, so a collision is essentially impossible — but if one does
   * occur, the NEW signal is dropped in favor of the already-queued one
   * (the position state it was computed against is about to change at fill
   * time, so acting on a stale second signal would be worse than skipping).
   */
  _queueSignal(id, sig) {
    if (this._pendingSignals[id]) return;
    this._pendingSignals[id] = sig;
  }

  /**
   * Fill all queued signals at the given candle's OPEN price, then clear the
   * queue. Also resolves a pending buy-and-hold baseline entry at the same
   * open so the baseline uses the identical execution semantics as
   * strategies (evaluate on N, fill on N+1 at open).
   */
  _fillPendingSignals(candle) {
    if (this._baselineEntryPending) {
      this._baselineEntryPrice = candle.open;
      this._baselineEntryVolume = candle.volume;
      this._baselineEntryPending = false;
    }
    for (const id of Object.keys(this._pendingSignals)) {
      const sig = this._pendingSignals[id];
      delete this._pendingSignals[id];
      this._processSignal(sig, candle.open, candle.volume);
    }
  }

  _processSignal(sig, price, volume) {
    if (sig.action === 'enter_long') {
      if (this.portfolio.hasPosition('long')) return;
      // Confidence-scaled, but BOUNDED position sizing: weak signals risk 5%
      // of INITIAL cash, strong (confidence 1) signals risk 15%. Sizing off
      // initialCash (not the growing cash balance) keeps risk per trade
      // constant and non-compounding — sizing off current cash produced
      // unrealistic multi-thousand-percent backtest returns as wins snowball
      // into ever-larger bets. computeEntrySize additionally clamps the fill
      // notional to maxPositionPct of current equity, so a grown account
      // can't push single-position risk past its cap either.
      const confidence = (typeof sig.confidence === 'number' && isFinite(sig.confidence))
        ? Math.max(0, Math.min(1, sig.confidence))
        : 0.5;
      const qty = this.portfolio.computeEntrySize(price, volume, confidence);
      if (qty <= 0) return;
      // openPosition may reject if the slippage+fee-adjusted cost exceeds
      // cash (e.g. unusually high fee/slippage configs) — skip the trade
      // rather than letting cash go negative.
      const result = this.portfolio.openPosition('long', qty, price, sig.strategy, volume);
      if (result === null) return;
      const { fillPrice, fee } = result;
      this.portfolio.totalTrades++;
      this._addTrade({ type: 'entry', side: 'long', quantity: qty, price: fillPrice, fee, strategy: sig.strategy, timestamp: Date.now(), pnl: null });
    } else if (sig.action === 'exit_long') {
      const result = this.portfolio.closePosition('long', price, volume);
      if (result !== null) {
        this.portfolio.totalTrades++;
        this._addTrade({ type: 'exit', side: 'long', quantity: result.quantity, price: result.fillPrice, strategy: result.strategyId, timestamp: Date.now(), pnl: parseFloat(result.pnl.toFixed(2)) });
      }
    }
  }

  _render(candle, state) {
    if (this.headless) return;
    if (window.candleSeries) {
      if (!this._chartDataLoaded) {
        const buf = this.market.candleBuffer;
        window.candleSeries.setData(buf);
        window.volumeSeries.setData(buf.map(c => ({ time: c.time, value: c.volume, color: 'rgba(59,130,246,0.4)' })));
        this._chartDataLoaded = true;
      } else {
        window.candleSeries.update(candle);
        window.volumeSeries.update({ time: candle.time, value: candle.volume, color: 'rgba(59,130,246,0.4)' });
      }
    }

    document.getElementById('priceDisplay').textContent = candle.close.toFixed(4);
    document.getElementById('priceDisplay').className = 'price-value' + (candle.close >= candle.open ? ' up' : ' down');
    document.getElementById('changeDisplay').textContent = (state.change24 >= 0 ? '+' : '') + state.change24.toFixed(2) + '%';
    document.getElementById('highDisplay').textContent = state.high24.toFixed(4);
    document.getElementById('lowDisplay').textContent = state.low24.toFixed(4);
    document.getElementById('volDisplay').textContent = this._formatVolume(state.volume24);

    const equity = this.portfolio.totalEquity(candle.close);
    // Derive PnL/return from the portfolio's actual starting balance rather
    // than a hardcoded literal — consistent with Portfolio.reset() honoring
    // initialCash; correct if the portfolio is ever constructed differently.
    const initialCash = this.portfolio.initialCash;
    const totalPnl = equity - initialCash;
    const retPct = ((equity - initialCash) / initialCash) * 100;

    document.getElementById('cashDisplay').textContent = this.portfolio.cash.toFixed(2);
    document.getElementById('equityDisplay').textContent = equity.toFixed(2);

    const pnlEl = document.getElementById('pnlDisplay');
    pnlEl.textContent = (totalPnl >= 0 ? '+' : '') + totalPnl.toFixed(2);
    pnlEl.className = 'stat-value' + (totalPnl >= 0 ? ' pos' : ' neg');

    const retEl = document.getElementById('returnDisplay');
    retEl.textContent = (retPct >= 0 ? '+' : '') + retPct.toFixed(2) + '%';
    retEl.className = 'stat-value' + (retPct >= 0 ? ' pos' : ' neg');

    // Same-seed buy-and-hold baseline comparison. O(1) mark-to-market from
    // the entry captured at the first eval tick — recomputed every frame.
    this._refreshBaseline();
    const baselinePct = this._baselineReturnPct;
    const alpha = retPct - baselinePct;
    const baselineEl = document.getElementById('baselineDisplay');
    if (baselineEl) {
      baselineEl.textContent = (baselinePct >= 0 ? '+' : '') + baselinePct.toFixed(2) + '%';
      baselineEl.className = 'stat-value' + (baselinePct >= 0 ? ' pos' : ' neg');
    }
    const alphaEl = document.getElementById('alphaDisplay');
    if (alphaEl) {
      alphaEl.textContent = (alpha >= 0 ? '+' : '') + alpha.toFixed(2) + '%';
      alphaEl.className = 'stat-value' + (alpha >= 0 ? ' pos' : ' neg');
    }

    document.getElementById('positionsCount').textContent = this.portfolio.positions.length;
    document.getElementById('tradesCount').textContent = this.portfolio.totalTrades;
    document.getElementById('feesDisplay').textContent = this.portfolio.totalFeesPaid.toFixed(2);
    this._renderPositions();

    if (this.running) {
      document.getElementById('uptimeDisplay').textContent = this._formatUptime((Date.now() - this.startTime) / 1000);
    }
  }

  _renderPositions() {
    if (this.headless) return;
    const container = document.getElementById('positionsContainer');
    const pos = this.portfolio.positions;
    if (!pos.length) {
      container.innerHTML = '<div class="positions-empty">No open positions</div>';
      return;
    }
    const price = this.market.price;
    let html = '<table class="positions-table"><thead><tr><th>Side</th><th>Qty</th><th>Entry</th><th>Current</th><th>PnL</th></tr></thead><tbody>';
    for (const p of pos) {
      const pnl = p.unrealizedPnl || 0;
      html += `<tr><td class="side-${p.side}">${p.side.toUpperCase()}</td><td>${p.quantity.toFixed(4)}</td><td>$${p.entryPrice.toFixed(4)}</td><td>$${price.toFixed(4)}</td><td style="color:${pnl >= 0 ? 'var(--accent-green)' : 'var(--accent-red)'}">${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}</td></tr>`;
    }
    container.innerHTML = html + '</tbody></table>';
  }

  _addTrade(trade) {
    this.portfolio.trades.unshift(trade);
    if (this.portfolio.trades.length > 100) this.portfolio.trades.pop();
    if (!this.headless) this._renderTrades();
  }

  /**
   * Re-render the recent-trades table applying the active sort.
   * Sort state: this.tradeSort = { key: 'time'|'pnl', dir: 1|-1 }.
   * Entries with no realized PnL (pnl === null) always sink to the bottom.
   */
  _renderTrades() {
    if (this.headless) return;
    const body = document.getElementById('tradesBody');
    if (!body) return;
    const trades = this.portfolio.trades;
    const s = this.tradeSort;

    // Update header indicators
    document.querySelectorAll('.trades-table th.sortable .sort-ind').forEach(el => { el.textContent = ''; });
    const activeTh = document.querySelector(`.trades-table th[data-sort-key="${s.key}"] .sort-ind`);
    if (activeTh) activeTh.textContent = s.dir === -1 ? '▼' : '▲';

    if (!trades.length) {
      body.innerHTML = '<tr><td colspan="7" class="positions-empty">No trades yet</td></tr>';
      return;
    }

    const sorted = trades.slice().sort((a, b) => {
      if (s.key === 'pnl') {
        const aHas = a.pnl !== null && a.pnl !== undefined;
        const bHas = b.pnl !== null && b.pnl !== undefined;
        if (aHas && bHas) return (a.pnl - b.pnl) * s.dir;
        if (aHas) return -1; // realized PnL rows first
        if (bHas) return 1;
        return 0;
      }
      return (a.timestamp - b.timestamp) * s.dir;
    });

    let html = '';
    for (const t of sorted) {
      const typeCls = t.type === 'entry' ? 'entry' : t.type === 'exit' ? 'exit' : 'rejected';
      const pnlCell = (t.pnl === null || t.pnl === undefined)
        ? '<td class="trade-pnl">—</td>'
        : `<td class="trade-pnl ${t.pnl >= 0 ? 'pos' : 'neg'}">${t.pnl >= 0 ? '+' : ''}${t.pnl.toFixed(2)}</td>`;
      html += `<tr>
        <td><span class="trade-side ${typeCls}">${t.type}</span></td>
        <td>${t.side ? t.side.toUpperCase() : ''}</td>
        <td class="trade-time">${this._fmtTime(t.timestamp)}</td>
        <td>${t.quantity ? t.quantity.toFixed(4) : ''}</td>
        <td>${t.price ? '$' + t.price.toFixed(4) : ''}</td>
        ${pnlCell}
        <td>${t.strategy || ''}</td>
      </tr>`;
    }
    body.innerHTML = html;
  }

  /** Cycle sort: same column toggles direction, new column becomes primary. */
  toggleTradeSort(key) {
    if (this.tradeSort.key === key) {
      this.tradeSort.dir *= -1;
    } else {
      this.tradeSort = { key, dir: -1 };
    }
    this._renderTrades();
  }

  _formatVolume(val) {
    if (val >= 1e6) return (val / 1e6).toFixed(2) + 'M';
    if (val >= 1e3) return (val / 1e3).toFixed(2) + 'K';
    return val.toFixed(0);
  }

  _formatUptime(s) {
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = Math.floor(s % 60);
    if (h > 0) return `${h}h ${m}m`;
    if (m > 0) return `${m}m ${sec}s`;
    return `${sec}s`;
  }

  /** Enable/disable the realism layer (GARCH vol, momentum, volume coupling). */
  setRealismMode(enabled) {
    this.market.setRealism(enabled);
  }

  /** Enable/disable regime randomization on each reset. */
  setRandomizeRegime(enabled) {
    this.market.randomizeOnReset = enabled;
  }

  /**
   * Select which strategies drive trading.
   * @param {string} choice  'breakout_hunter' | 'rsi_reversion' | 'buy_and_hold' | 'all'
   */
  setStrategy(choice) {
    if (choice === 'all') {
      this.activeStrategies = [...TRADING_STRATEGY_IDS];
    } else if (STRATEGY_REGISTRY[choice]) {
      this.activeStrategies = [choice];
    }
    this._pendingSignals = {};
    this._buildEvaluators();
  }

  /**
   * Run a full simulation synchronously with zero DOM access.
   * NOTE: replaces this.market/this.portfolio — use on a throwaway engine
   * (e.g. `new SimulationEngine().runHeadless(...)`), never on the live one.
   * @param {object} opts  { seed, ticks, strategy, realism, randomize }
   * @returns {object} stats { seed, ticks, strategy, realism, randomize,
   *   equity, returnPct, trades, winRate, maxDrawdownPct, sortino,
   *   unfilledSignals, feesPaid }
   */
  runHeadless({ seed = 1, ticks = 20000, strategy = 'buy_and_hold', realism = false, randomize = false } = {}) {
    this.headless = true;
    try {
      this.market = new SyntheticMarket(100, 0.02, 0.0004, { enabled: realism }, seed);
      // Skip the UI-only 24h window tracking — batch runs only need candles.
      this.market.batchMode = true;
      // Domain randomization: redraw drift/GARCH/momentum before the first
      // tick. randomizeParams() draws from the seeded _rng, so the regime is
      // deterministic per seed — two runs with the same seed and randomize
      // flag consume the same first draws and get IDENTICAL regimes, which is
      // what keeps same-seed baseline-vs-strategy comparisons apples-to-apples.
      if (randomize) this.market.randomizeParams();
      this.portfolio = new Portfolio(10000, TRADING_COSTS.feeRate, TRADING_COSTS.slippageBps);
      this.candlesGenerated = 0;
      this.preSeedDone = false;
      this._chartDataLoaded = false;
      this.tradeSort = { key: 'time', dir: -1 };
      // Per-run signal queue — MUST be cleared here, not just in reset().
      // runBatchBacktest() reuses ONE engine across all seeds and strategies,
      // and evaluations fire every 5 ticks, so the final tick of a run
      // (20000 % 5 === 0) can queue a signal that has no next tick to fill it
      // within that run. Leftover signals must not survive into the next
      // runHeadless() call: _fillPendingSignals() has no activeStrategies
      // filter, so a stale signal from a previous seed/strategy would be
      // filled on tick 1 of the NEW run against the NEW market — injecting a
      // phantom trade (fees, PnL, winRate, returnPct) into a run it has
      // nothing to do with, and making results depend on call order instead
      // of the seed. Same fix reset() already applies for the live path.
      this._pendingSignals = {};
      this.activeStrategies = [strategy];
      this._buildEvaluators();
      this.preSeed(500);

      // Risk-adjusted stats from the per-tick equity series. Derive the
      // starting balance from the portfolio instead of a hardcoded literal —
      // peakEquity and returnPct stay correct even if Portfolio is ever
      // constructed with a different initial cash.
      const initialCash = this.portfolio.initialCash;
      let peakEquity = initialCash;
      let maxDrawdown = 0;
      const equitySeries = [];
      for (let i = 0; i < ticks; i++) {
        this._step();
        const eq = this.portfolio.totalEquity(this.market.price);
        equitySeries.push(eq);
        if (eq > peakEquity) peakEquity = eq;
        const dd = (peakEquity - eq) / peakEquity;
        if (dd > maxDrawdown) maxDrawdown = dd;
      }

      // Sortino ratio on per-tick returns with a 0% target: mean return
      // divided by DOWNSIDE deviation (only losing ticks punished, unlike
      // Sharpe which treats upside and downside volatility alike). Ticks are
      // a relative time axis, so the ratio is comparable across strategies on
      // the same cadence — it is NOT annualized, and is 0 when a run never
      // had a down tick (degenerate, effectively monotone-up).
      let sortino = 0;
      if (equitySeries.length > 1) {
        const returns = [];
        for (let i = 1; i < equitySeries.length; i++) {
          const prev = equitySeries[i - 1];
          returns.push(prev > 0 ? (equitySeries[i] - prev) / prev : 0);
        }
        const meanReturn = returns.reduce((s, r) => s + r, 0) / returns.length;
        const downsideSq = returns.reduce((s, r) => s + (r < 0 ? r * r : 0), 0);
        const downsideDev = Math.sqrt(downsideSq / returns.length);
        if (downsideDev > 0) sortino = meanReturn / downsideDev;
      }

      const equity = this.portfolio.totalEquity(this.market.price);
      // Discard any signal queued by the final eval tick — with ticks
      // divisible by the 5-tick cadence, the last evaluation fires on the
      // last tick and has no next tick to fill it. This is EXPECTED, not a
      // bug: count it for visibility, then clear the queue so nothing leaks
      // into the next runHeadless() call on this engine. (The start-of-run
      // reset above is the primary guard; this makes the invariant local.)
      const unfilledSignals = Object.keys(this._pendingSignals).length;
      this._pendingSignals = {};
      return {
        seed, ticks, strategy, realism, randomize,
        equity,
        returnPct: ((equity - initialCash) / initialCash) * 100,
        trades: this.portfolio.totalTrades,
        // winRate from running counters, NOT a filter over the capped trades
        // display array (which truncates to 100 entries and would silently
        // skew the stat on any run with >50 round trips).
        winRate: this.portfolio.closedTradesCount
          ? (this.portfolio.winningTradesCount / this.portfolio.closedTradesCount) * 100
          : 0,
        maxDrawdownPct: maxDrawdown * 100,
        sortino,
        unfilledSignals,
        feesPaid: this.portfolio.totalFeesPaid,
      };
    } finally {
      this.headless = false;
    }
  }

  /**
   * Buy-and-hold baseline return for the live run, computed incrementally in
   * O(1) — no re-simulation. Mirrors exactly what _processSignal +
   * openPosition would do for a confidence-1 signal at the fill tick:
   * 15% of initial cash sized against the quote price, filled at the
   * slippage-adjusted price (volume-aware, using the fill candle's volume),
   * fee charged, then marked to the current price. This stays bit-identical
   * to the headless runHeadless buy_and_hold path because both derive from
   * the same sizing/fill math and the same seed.
   */
  _refreshBaseline() {
    const entryPrice = this._baselineEntryPrice;
    const entryVolume = this._baselineEntryVolume;
    if (entryPrice === null || entryPrice === undefined) return;
    const portfolio = this.portfolio;
    // buy_and_hold always reports confidence 1 (sizes at 15% of initial
    // cash). The baseline represents an independent account holding only
    // this position, so cap equity is its own initial cash — the live
    // portfolio's current equity is irrelevant to it.
    const qty = portfolio.computeEntrySize(entryPrice, entryVolume, 1, portfolio.initialCash);
    if (qty <= 0) return;
    // Long entry fills adverse: quote + slippage (same path as openPosition)
    const orderNotional = qty * entryPrice;
    const fillPrice = portfolio._slippedPrice(entryPrice, 'long', true, orderNotional, entryVolume);
    const fee = portfolio.feeRate * qty * fillPrice;
    const cashAfter = portfolio.initialCash - qty * fillPrice - fee;
    const equity = cashAfter + qty * this.market.price;
    this._baselineReturnPct = ((equity - portfolio.initialCash) / portfolio.initialCash) * 100;
  }

  /**
   * Build a plain-data summary of the run for the Stop-button popup. Pure
   * logic — no DOM — so it can be unit-tested headlessly. Uses the running
   * counters (closedTradesCount / winningTradesCount / totalRealizedPnl /
   * strategyStats), NOT the 100-entry UI-capped trades array, so the numbers
   * stay exact on runs with more than ~50 round trips.
   * @returns {object} { equity, returnPct, totalTrades, closedTrades,
   *   winRate, netPnl, feesPaid, openPositions, unrealizedPnl, byStrategy }
   */
  _buildTradeSummary() {
    const p = this.portfolio;
    const initialCash = p.initialCash;
    const equity = p.totalEquity(this.market.price);
    const unrealizedPnl = p.positions.reduce((s, pos) => s + (pos.unrealizedPnl || 0), 0);
    const byStrategy = Object.entries(p.strategyStats)
      .map(([strategy, st]) => ({
        strategy,
        entries: st.entries,
        exits: st.exits,
        closed: st.closed,
        wins: st.wins,
        winRate: st.closed ? (st.wins / st.closed) * 100 : 0,
        pnl: st.pnl,
      }))
      .sort((a, b) => b.pnl - a.pnl);
    return {
      equity,
      returnPct: ((equity - initialCash) / initialCash) * 100,
      totalTrades: p.totalTrades,
      closedTrades: p.closedTradesCount,
      winRate: p.closedTradesCount
        ? (p.winningTradesCount / p.closedTradesCount) * 100
        : 0,
      netPnl: p.totalRealizedPnl,
      feesPaid: p.totalFeesPaid,
      openPositions: p.positions.length,
      unrealizedPnl,
      byStrategy,
    };
  }

/**
   * Show the trade-summary popup (live UI only). Builds a modal overlay with
   * the summary from _buildTradeSummary(); closes via the ✕ button, clicking
   * the dimmed backdrop, or the Escape key. No-op when the DOM isn't present
   * (stubless Node require / headless batch runs).
   * Only one summary modal can be open at a time — subsequent calls replace it.
   */
  showTradeSummary() {
    if (this.headless || typeof document === 'undefined' || !document.getElementById) return;
    // Remove any existing summary overlay and its keydown listener
    const existingOverlay = document.querySelector('.summary-overlay');
    if (existingOverlay) {
      existingOverlay.remove();
    }
    if (this._summaryKeyHandler) {
      document.removeEventListener('keydown', this._summaryKeyHandler);
      this._summaryKeyHandler = null;
    }

    const s = this._buildTradeSummary();
    const fmtMoney = (n) => (n >= 0 ? '+' : '') + n.toFixed(2);
    const cls = (n) => (n >= 0 ? 'pos' : 'neg');
    const esc = (str) => String(str).replace(/[&<>"']/g, (c) => ({
       '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
    }[c]));

    const strategyRows = s.byStrategy.length
      ? s.byStrategy.map(row => `
        <tr>
          <td>${esc(row.strategy)}</td>
          <td>${row.entries}</td>
          <td>${row.exits}</td>
          <td>${row.closed}</td>
          <td>${row.winRate.toFixed(1)}%</td>
          <td class="trade-pnl ${cls(row.pnl)}">${fmtMoney(row.pnl)}</td>
        </tr>`).join('')
      : '<tr><td colspan="6" class="positions-empty">No closed trades yet</td></tr>';

    const overlay = document.createElement('div');
    overlay.className = 'summary-overlay';
    overlay.innerHTML = `
      <div class="summary-modal" role="dialog" aria-label="Trade Summary">
        <div class="summary-header">
          <span class="panel-title">Trade Summary</span>
          <button class="summary-close" id="summaryCloseBtn" title="Close (Esc)">✕</button>
        </div>
        <div class="summary-body">
          <div class="stat-grid">
            <div class="stat-item"><span class="stat-label">Equity</span><span class="stat-value">$${s.equity.toFixed(2)}</span></div>
            <div class="stat-item"><span class="stat-label">Return</span><span class="stat-value ${cls(s.returnPct)}">${fmtMoney(s.returnPct)}%</span></div>
            <div class="stat-item"><span class="stat-label">Total Trades</span><span class="stat-value">${s.totalTrades}</span></div>
            <div class="stat-item"><span class="stat-label">Closed</span><span class="stat-value">${s.closedTrades}</span></div>
            <div class="stat-item"><span class="stat-label">Win Rate</span><span class="stat-value">${s.winRate.toFixed(1)}%</span></div>
            <div class="stat-item"><span class="stat-label">Net PnL</span><span class="stat-value ${cls(s.netPnl)}">${fmtMoney(s.netPnl)}</span></div>
            <div class="stat-item"><span class="stat-label">Unrealized</span><span class="stat-value ${cls(s.unrealizedPnl)}">${fmtMoney(s.unrealizedPnl)}</span></div>
            <div class="stat-item"><span class="stat-label">Fees Paid</span><span class="stat-value">$${s.feesPaid.toFixed(2)}</span></div>
          </div>
          <div class="section-title">By Strategy</div>
          <table class="summary-table">
            <thead><tr><th>Strategy</th><th>Entries</th><th>Exits</th><th>Closed</th><th>Win Rate</th><th>Net PnL</th></tr></thead>
            <tbody>${strategyRows}</tbody>
          </table>
        </div>
      </div>`;

    const startBtn = document.getElementById('btnStart');
    const close = () => {
      overlay.remove();
      document.removeEventListener('keydown', this._summaryKeyHandler);
      this._summaryKeyHandler = null;
      // Re-enable Start button if engine isn't running
      if (startBtn && !this.running) {
        startBtn.disabled = false;
      }
    };
    const onKey = (e) => { if (e.key === 'Escape') close(); };
    this._summaryKeyHandler = onKey;
    overlay.querySelector('#summaryCloseBtn').addEventListener('click', close);
    // Click on the dimmed backdrop (outside the modal) also closes.
    overlay.addEventListener('click', (e) => { if (e.target === overlay) close(); });
    document.addEventListener('keydown', onKey);
    document.body.appendChild(overlay);

    // Disable Start button while modal is open to prevent new run while viewing stale summary
    if (startBtn && !this.running) {
      startBtn.disabled = true;
    }
  }

  /** Format a JS millisecond timestamp as HH:MM:SS */
  _fmtTime(ts) {
    const d = new Date(ts);
    return String(d.getHours()).padStart(2, '0') + ':' +
           String(d.getMinutes()).padStart(2, '0') + ':' +
           String(d.getSeconds()).padStart(2, '0');
  }
}

// =============================================================================
// Browser-only bootstrapping (chart, controls, visibility handler).
// Everything below touches the DOM or LightweightCharts and is guarded so that
// require('./simulation.js') under Node — which backtest.js does — loads the
// file cleanly without a ReferenceError, while the browser still wires up the
// full UI. Mirrors the guard pattern already used in backtest.js's btnBatch
// wiring. The module.exports block at the end is intentionally OUTSIDE this
// guard so headless runs get the classes they need.
// =============================================================================

if (typeof document !== 'undefined' && document.getElementById) {
  // =========================================================================
  // Page-visibility handler
  // =========================================================================

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden && window.engine && window.engine.running) {
      window.engine.lastTickTime = performance.now();
    }
  });

  // =========================================================================
  // App setup
  // =========================================================================

  const engine = new SimulationEngine();
  window.engine = engine;

  const chart = LightweightCharts.createChart(document.getElementById('chart-container'), {
    layout: { background: { color: '#1a1b1e' }, textColor: '#a1a1aa' },
    grid: { vertLines: { color: '#2c2e33' }, horzLines: { color: '#2c2e33' } },
    crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
    rightPriceScale: { borderColor: '#3f3f46', scaleMargins: { top: 0.05, bottom: 0.2 } },
    timeScale: { borderColor: '#3f3f46', timeVisible: true, secondsVisible: true },
    watermark: { visible: true, text: 'FRED/USDT · SIMULATED', color: 'rgba(255,255,255,0.04)', fontSize: 28, horzAlign: 'center', vertAlign: 'center' },
  });
  chart.applyOptions({ handleScroll: { vertTouchDrag: false } });

  // v5.2.0 API: chart.addSeries(type, options) — addCandlestickSeries is removed.
  const candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
    upColor: '#22c55e', downColor: '#ef4444', borderUpColor: '#22c55e', borderDownColor: '#ef4444', wickUpColor: '#22c55e', wickDownColor: '#ef4444',
  });
  const volumeSeries = chart.addSeries(LightweightCharts.HistogramSeries, {
    priceFormat: { type: 'volume' }, priceScaleId: 'volume', color: 'rgba(59,130,246,0.3)',
  });
  volumeSeries.priceScale().applyOptions({ scaleMargins: { top: 0.85, bottom: 0 }, visible: false });

  window.candleSeries = candleSeries;
  window.volumeSeries = volumeSeries;

  // Resize
  const chartContainer = document.getElementById('chart-container');
  function resizeChart() {
    const r = chartContainer.getBoundingClientRect();
    chart.applyOptions({ width: r.width, height: r.height });
  }
  new ResizeObserver(resizeChart).observe(chartContainer);
  window.addEventListener('resize', resizeChart);

  // Controls
  document.getElementById('btnStart').addEventListener('click', () => engine.start());
  document.getElementById('btnStop').addEventListener('click', () => {
    engine.stop();
    engine.showTradeSummary();
  });
  document.getElementById('btnReset').addEventListener('click', () => {
    if (!confirm('Reset simulation — clear all portfolio data?')) return;
    engine.reset();
    candleSeries.setData([]);
    volumeSeries.setData([]);
    engine.resetUI();
  });

  // Speed buttons
  document.querySelectorAll('.btn-speed').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.btn-speed').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      engine.speed = parseInt(btn.dataset.speed);
    });
  });

  // Realism toggles (applied from the next tick / reset onward)
  document.getElementById('chkRealism').addEventListener('change', e => {
    engine.setRealismMode(e.target.checked);
    if (!engine.running) {
      // Fully regenerate history under the new regime on the next start:
      // reset() rewinds price/buffers/timestamps so preSeed() re-builds the
      // chart from a clean slate, instead of appending new-regime candles on
      // top of old-regime history. Symmetric for check and uncheck — both
      // change the regime, so both must force a fresh chart.
      engine.market.reset();
      engine.preSeedDone = false;
    }
  });

  document.getElementById('chkRandomize').addEventListener('change', e => {
    engine.setRandomizeRegime(e.target.checked);
  });

  // Strategy selector
  document.getElementById('strategySelect').addEventListener('change', e => {
    engine.setStrategy(e.target.value);
  });

  // Trade-table sortable headers
  document.querySelectorAll('.trades-table th.sortable').forEach(th => {
    th.addEventListener('click', () => engine.toggleTradeSort(th.dataset.sortKey));
  });
  // Paint the default sort indicator (time ▼) on first load
  engine._renderTrades();

  console.log('Simulation frontend ready — fully client-side');
} // end browser-only bootstrap guard

// ---- Node export (for headless backtest validation in CI/CLI) ----
if (typeof module !== 'undefined' && module.exports) {
  module.exports = { SyntheticMarket, Portfolio, SimulationEngine, STRATEGY_REGISTRY, mulberry32 };
}

