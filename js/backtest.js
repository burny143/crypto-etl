// =============================================================================
// Headless Batch Backtester
// Runs each strategy across N seeded markets and compares every result against
// the SAME-seed buy-and-hold baseline — so "alpha" is measured net of the
// market's own drift, tick-by-tick, not against a fixed 0% benchmark.
// No DOM dependency: works in the browser UI and in plain Node.
// =============================================================================

/**
 * Aggregate helper: mean / median / stddev / percentiles / % positive.
 * Percentiles (p10/p25/p75/p90) expose the shape of the distribution — under
 * heavy right-skew from compounding, the mean can be dragged far above the
 * "typical" seed, so mean alone is misleading.
 */
function _aggregate(values) {
  const empty = {
    mean: 0, median: 0, stddev: 0, pctPositive: 0,
    min: 0, max: 0, p10: 0, p25: 0, p75: 0, p90: 0,
  };
  if (!values.length) return empty;
  const sorted = values.slice().sort((a, b) => a - b);
  const mean = sorted.reduce((s, v) => s + v, 0) / sorted.length;
  const mid = Math.floor(sorted.length / 2);
  const median = sorted.length % 2 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  const variance = sorted.reduce((s, v) => s + (v - mean) ** 2, 0) / sorted.length;
  // Linear-interpolated percentile: index = p/100 * (n-1).
  const pct = (p) => {
    const idx = (p / 100) * (sorted.length - 1);
    const lo = Math.floor(idx);
    const hi = Math.ceil(idx);
    if (lo === hi) return sorted[lo];
    return sorted[lo] + (sorted[hi] - sorted[lo]) * (idx - lo);
  };
  return {
    mean,
    median,
    stddev: Math.sqrt(variance),
    pctPositive: (sorted.filter(v => v > 0).length / sorted.length) * 100,
    min: sorted[0],
    max: sorted[sorted.length - 1],
    p10: pct(10),
    p25: pct(25),
    p75: pct(75),
    p90: pct(90),
  };
}

/**
 * Run a multi-seed batch backtest.
 * @param {object} opts
 *   seeds       number of seeds (default 50)
 *   ticks       simulated ticks per run (default 20000)
 *   strategies  strategy ids to test (default trading strategies, excludes
 *               buy_and_hold which is used as the baseline; any buy_and_hold
 *               passed here is filtered out with a warning)
 *   realism     enable the realism layer (GARCH/momentum/volume coupling)
 *   randomize   domain-randomize the regime per seed (drift/GARCH/momentum).
 *               Defaults to `realism` — randomization is part of the realism
 *               layer's purpose; pass false explicitly to pin one regime.
 * @returns {{seeds, ticks, realism, randomize, bySeed: Array,
 *            strategies: Object<string,Object>}}
 *   bySeed: one row per seed: { seed, baseline, strategy, stratReturn, alpha }
 *   strategies: per-strategy aggregates of return and alpha
 */
function runBatchBacktest({ seeds = 50, ticks = 20000, strategies = ['breakout_hunter', 'rsi_reversion'], realism = false, randomize = null } = {}) {
  // buy_and_hold is the baseline, not a strategy under test — comparing it
  // against itself produces a meaningless ~0 alpha row. Filter it out with a
  // warning rather than silently reporting a degenerate "edge".
  let strategyList = strategies;
  if (strategyList.includes('buy_and_hold')) {
    if (typeof console !== 'undefined' && console.warn) {
      console.warn('[backtest] buy_and_hold is the baseline and was removed from the tested strategies.');
    }
    strategyList = strategyList.filter(id => id !== 'buy_and_hold');
  }

  // Same-seed baseline and strategy runs MUST use identical regime params.
  // runHeadless constructs a fresh seeded market per call and randomizeParams
  // draws from that seed's RNG, so both runs for a seed get the same regime
  // when the flag is passed through — never re-randomized between them.
  const useRandomize = (randomize === null) ? realism : !!randomize;

  const engine = new SimulationEngine();
  const bySeed = [];
  const perStrategy = {};
  for (const id of strategyList) perStrategy[id] = [];

  for (let s = 1; s <= seeds; s++) {
    // Same-seed baseline: buy-and-hold on the identical seeded market.
    const baseline = engine.runHeadless({ seed: s, ticks, strategy: 'buy_and_hold', realism, randomize: useRandomize });

    for (const stratId of strategyList) {
      const run = engine.runHeadless({ seed: s, ticks, strategy: stratId, realism, randomize: useRandomize });
      const alpha = run.returnPct - baseline.returnPct;
      bySeed.push({
        seed: s,
        baseline: baseline.returnPct,
        baselineSortino: baseline.sortino,
        strategy: stratId,
        stratReturn: run.returnPct,
        alpha,
        trades: run.trades,
        winRate: run.winRate,
        maxDrawdown: run.maxDrawdownPct,
        sortino: run.sortino,
      });
      perStrategy[stratId].push(alpha);
    }
  }

  const strategiesOut = {};
  for (const id of strategyList) {
    const rows = perStrategy[id];
    strategiesOut[id] = {
      alpha: _aggregate(rows),
      pctBeatsBaseline: (rows.filter(a => a > 0).length / rows.length) * 100,
    };
    // Sortino is a per-run ratio; aggregate its distribution across seeds
    // the same way alpha is (mean/median/percentiles).
    const sortinoRows = bySeed.filter(r => r.strategy === id).map(r => r.sortino);
    if (sortinoRows.length) strategiesOut[id].sortino = _aggregate(sortinoRows);
  }
  return { seeds, ticks, realism, randomize: useRandomize, bySeed, strategies: strategiesOut };
}

/** Format a batch result as a readable text report. */
function formatBatchReport(result) {
  const stratIds = Object.keys(result.strategies);
  if (stratIds.length === 0) {
    return 'No strategies to report.';
  }
  const lines = [];
  lines.push(`Batch backtest — ${result.seeds} seeds × ${result.ticks} ticks, realism: ${result.realism ? 'ON' : 'OFF'}, randomization: ${result.randomize ? 'ON' : 'OFF'}`);
  lines.push('Each strategy vs the SAME-seed buy-and-hold baseline (alpha = strategy return − baseline return).');
  lines.push('Percentiles (p10/p25/p75/p90) show the distribution shape — under heavy right-skew');
  lines.push('from compounding, the mean is pulled up by a few extreme seeds and overstates the "typical" run.');
  lines.push('p10 is the CVaR-style tail figure: the return of the 10% worst seeds — plan around it, not the mean.');
  lines.push('Sortino = mean per-tick return ÷ downside deviation (0% target); comparable across strategies, NOT annualized.');
  lines.push('');
  lines.push('Strategy            mean α   median α   σ α     p10      p25      p75      p90    Sortino  %α>0   beats B&H');
  for (const id of stratIds) {
    const a = result.strategies[id].alpha;
    const s = result.strategies[id].sortino;
    const sortinoStr = s ? s.mean.toFixed(3) : '  n/a';
    lines.push(
      `${id.padEnd(18)} ${a.mean.toFixed(2).padStart(7)}%  ${a.median.toFixed(2).padStart(8)}%  ${a.stddev.toFixed(2).padStart(5)}%  ${a.p10.toFixed(2).padStart(7)}%  ${a.p25.toFixed(2).padStart(7)}%  ${a.p75.toFixed(2).padStart(7)}%  ${a.p90.toFixed(2).padStart(7)}%  ${sortinoStr.padStart(8)}  ${a.pctPositive.toFixed(1).padStart(5)}%   ${result.strategies[id].pctBeatsBaseline.toFixed(1).padStart(5)}%`,
    );
  }
  lines.push('');
  lines.push('Tail risk (CVaR-style): the 10% worst seeds — what a run can realistically lose:');
  for (const id of stratIds) {
    const a = result.strategies[id].alpha;
    lines.push(`  ${id.padEnd(18)} p10 α ${a.p10.toFixed(2).padStart(7)}%   (median ${a.median.toFixed(2)}%, mean ${a.mean.toFixed(2)}%)`);
  }
  lines.push('');
  const baselineRows = result.bySeed.filter(r => r.strategy === stratIds[0]);
  const baselineAgg = _aggregate(baselineRows.map(r => r.baseline));
  const baselineSortino = _aggregate(baselineRows.map(r => r.baselineSortino));
  lines.push(`Baseline (B&H) mean return: ${baselineAgg.mean.toFixed(2)}%  (median ${baselineAgg.median.toFixed(2)}%, p10 ${baselineAgg.p10.toFixed(2)}%, p90 ${baselineAgg.p90.toFixed(2)}%)  — mean Sortino ${baselineSortino.mean.toFixed(3)}`);
  return lines.join('\n');
}

// ---- browser UI wiring (no-op in Node) ----
if (typeof document !== 'undefined' && document.getElementById) {
  const btn = document.getElementById('btnBatch');
  if (btn) {
    btn.addEventListener('click', () => {
      const resultsEl = document.getElementById('batchResults');
      btn.disabled = true;
      resultsEl.textContent = 'Running…';
      // Yield a frame so the UI paints before the synchronous batch runs.
      setTimeout(() => {
        try {
          const realism = document.getElementById('chkRealism') ? document.getElementById('chkRealism').checked : false;
          // Mirror the "Randomize regime" checkbox when present.
          const randomizeEl = document.getElementById('chkRandomize');
          const randomize = randomizeEl ? randomizeEl.checked : null;
          const report = formatBatchReport(runBatchBacktest({ seeds: 50, ticks: 20000, realism, randomize }));
          resultsEl.textContent = report;
          resultsEl.className = 'batch-results';
        } catch (err) {
          resultsEl.textContent = 'Batch failed: ' + err.message;
        } finally {
          btn.disabled = false;
        }
      }, 50);
    });
  }
}

// ---- Node export (for CI/CLI validation) ----
if (typeof module !== 'undefined' && module.exports) {
  // simulation.js exports its classes when loaded under Node.
  const { SimulationEngine } = require('./simulation.js');
  if (typeof global !== 'undefined') global.SimulationEngine = SimulationEngine;
  module.exports = { runBatchBacktest, formatBatchReport, _aggregate };
}
