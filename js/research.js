// research.js — Research dashboard UI logic
// Depends on shared.js (must be loaded first)

// ── Dependency Guard ──
(function() {
  const required = {
    supabaseClient: 'object',
    escapeHtml: 'function',
    getClose: 'function',
    getHigh: 'function',
    getLow: 'function',
    getVolume: 'function',
    getTime: 'function',
    computeSMA: 'function',
    computeEMA: 'function',
    computeRSI: 'function',
    computeATR: 'function',
    computeADX: 'function',
    computeOBV: 'function',
    computeBB: 'function',
    computeKC: 'function'
  };
  const missing = [];
  for (const [name, type] of Object.entries(required)) {
    if (typeof window[name] !== type) missing.push(name);
  }
  if (missing.length) {
    const msg = `research.js: missing shared.js dependencies → ${missing.join(', ')}`;
    console.error(msg);
    const tbody = document.getElementById('tableBody');
    if (tbody) tbody.innerHTML = `<tr><td colspan="9"><div class="empty-state"><h3>Dependency Error</h3><p>${escapeHtml ? escapeHtml(msg) : msg}</p></div></td></tr>`;
    throw new Error(msg);
  }
})();

// ── State ──
  let aggregated = [];
  let expandedSymbol = null;
  let watchlistData = [];
  let priceChanges = {};       // { symbol: { d1, w1, m1, y1 } }
  let changeTf = 'd1';         // 'd1', 'w1', 'm1', 'y1'
  let researchInProgress = false;  // concurrency guard for batchGenerateResearch
  let retryPending = false;       // if batchGenerateResearch is called while busy, retry once after

  // ── Sort State ──
  let sortColumn = 'change';
  let sortDir = 'desc';
  window.setSort = function(col) {
    if (sortColumn === col) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortColumn = col;
      const descDefaults = ['change', 'confidence', 'winRate', 'entries'];
      sortDir = descDefaults.includes(col) ? 'desc' : 'asc';
    }
    applyFilters();
  };

  // ── Price-Momentum Values (separate from research-derived sentiment/confidence) ──
  function deriveMomentumValues() {
    for (const a of aggregated) {
      const pc = priceChanges[a.symbol] || {};
      const ch = pc[changeTf];
      if (ch != null) {
        // Sentiment from direction (>1% up = bullish, >1% down = bearish)
        if (ch > 1) a.priceMomentumSentiment = 'bullish';
        else if (ch < -1) a.priceMomentumSentiment = 'bearish';
        else a.priceMomentumSentiment = 'neutral';
        // Confidence from magnitude: bigger move → higher conviction.
        // Tiered so small differences stay visible across timeframes.
        const absCh = Math.abs(ch);
        if (absCh < 0.5) a.priceMomentumConfidence = 0.08;
        else if (absCh < 1) a.priceMomentumConfidence = 0.15;
        else if (absCh < 2) a.priceMomentumConfidence = 0.28;
        else if (absCh < 5) a.priceMomentumConfidence = 0.45;
        else if (absCh < 10) a.priceMomentumConfidence = 0.60;
        else if (absCh < 20) a.priceMomentumConfidence = 0.75;
        else a.priceMomentumConfidence = 0.85;
      } else {
        // No price data for this timeframe — only null out momentum fields
        a.priceMomentumSentiment = null;
        a.priceMomentumConfidence = null;
      }
    }
  }

  // ── Helpers ──
  function normalizeSymbol(s) {
    return (s || '').replace(/-USDT$/i, '-USD').trim().toUpperCase();
  }

  function symbolVariantsFor(sym) {
    // Build a set of symbol variants to try when querying crypto_historical
    const variants = new Set([sym]);
    if (sym.endsWith('-USD')) {
      variants.add(sym.replace('-USD', '-USDT'));
    } else if (sym.endsWith('-USDT')) {
      // Already fine, keep as-is
    } else {
      variants.add(sym + '-USDT');
      variants.add(sym + '-USD');
    }
    return variants;
  }

  function effectiveSentiment(a) {
    // Display sentiment: price momentum when available, research consensus as fallback
    return a.priceMomentumSentiment ?? a.sentiment;
  }

  function effectiveConfidence(a) {
    // Display confidence: price-momentum confidence when available, research consensus as fallback
    return a.priceMomentumConfidence ?? a.confidence;
  }


  function timeAgo(dateStr) {
    const ms = Date.now() - new Date(dateStr).getTime();
    const mins = Math.floor(ms / 60000);
    if (mins < 1) return 'just now';
    if (mins < 60) return `${mins}m ago`;
    const hrs = Math.floor(mins / 60);
    if (hrs < 24) return `${hrs}h ago`;
    const days = Math.floor(hrs / 24);
    if (days < 30) return `${days}d ago`;
    return new Date(dateStr).toLocaleDateString();
  }

  function sentimentBadge(s) {
    const label = escapeHtml((s || 'neutral').toLowerCase());
    return `<span class="badge badge-${label}">${label.toUpperCase()}</span>`;
  }

  // ── Indicator Helpers (ported from charts.html) ──


  // ── Insight Generators (3 tiers: OHLCV → strategy → price) ──
  function createStrategyInsight(symbol, price, strategies) {
    const best = strategies.length > 0
      ? strategies.reduce((b, s) => (s.sharpe_ratio || 0) > (b.sharpe_ratio || 0) ? s : b, strategies[0])
      : null;
    if (!best || best.sharpe_ratio == null) return null;

    const sh = best.sharpe_ratio;
    const wr = best.win_rate || 0;
    const ret = best.total_return_pct || 0;
    const name = (best.strategy_name || '?').replace(/_/g, ' ');
    const tf = best.timeframe || '—';

    let sentiment, confidence;
    // Tier 2 is a history report, not a market-direction signal.
    // "Best of N backtests" is structurally optimistic (selection bias);
    // deriving market sentiment from it would produce a false bullish skew.
    // Always neutral — let Tier 1 (live OHLCV analysis) own directional calls.
    sentiment = 'neutral'; confidence = 0.2;

    return {
      symbol,
      report_type: 'strategy_review',
      title: `${symbol} Strategy Overview — ${name}`,
      summary: `${symbol}: ${sentiment.toUpperCase()} ${Math.round(confidence * 100)}% conf. Best backtest: ${name} (${tf}) — Sharpe ${sh.toFixed(2)}, WR ${wr.toFixed(1)}%, Return ${ret >= 0 ? '+' : ''}${ret.toFixed(1)}%.`,
      details: {
        best_strategy: { name, timeframe: tf, sharpe: Math.round(sh * 100) / 100, win_rate: Math.round(wr * 10) / 10, return_pct: Math.round(ret * 10) / 10 },
        price_at_analysis: price,
        data_sources: ['strategy_results'],
      },
      sentiment,
      confidence: Math.round(confidence * 100) / 100,
      source: 'signal_engine',
    };
  }

  function createPriceInsight(symbol, price) {
    const sentiment = 'neutral';
    const confidence = 0.2;
    return {
      symbol,
      report_type: 'market_snapshot',
      title: `${symbol} Market Snapshot`,
      summary: `${symbol} tracked at ${price != null ? '$' + Number(price).toLocaleString(undefined, {minimumFractionDigits: 2}) : '—'}. Limited OHLCV and backtest data available. Low-confidence neutral stance until more data is collected.`,
      details: {
        current_price: price,
        data_quality: 'price_only',
        note: 'Insufficient historical data for technical analysis. Entry will improve as data accumulates.',
      },
      sentiment,
      confidence,
      source: 'signal_engine',
    };
  }

  function computeResearchEntry(symbol, bars) {
    const close = getClose(bars), high = getHigh(bars), low = getLow(bars);
    if (close.length < 30) return null;

    const cur = close[close.length - 1];
    const sma20 = computeSMA(bars, 20);
    const e12 = computeEMA(bars, 12);
    const e26 = computeEMA(bars, 26);
    const rsi = computeRSI(bars, 14);
    const adx = computeADX(bars, 14);
    const atr = computeATR(bars, 14);
    const obv = computeOBV(bars);
    const bb = computeBB(bars, 20, 2);
    const kc = computeKC(bars, 20, 1.5);

    const lRSI = rsi.length > 0 ? rsi[rsi.length - 1].value : 50;
    const lADX = adx.length > 0 ? adx[adx.length - 1].value : 0;
    const lATR = atr.length > 0 ? atr[atr.length - 1].value : cur * 0.02;
    const lSMA20 = sma20.length > 0 ? sma20[sma20.length - 1].value : cur;
    const lEF = e12.length > 0 ? e12[e12.length - 1].value : cur;
    const lES = e26.length > 0 ? e26[e26.length - 1].value : cur;

    const obvV = obv.map(p => p.value).filter(v => v != null);
    const obvT = obvV.length > 10 && obvV[obvV.length - 1] > obvV[obvV.length - 10] ? 'rising' : 'falling';

    const bbU = bb.upper.length > 0 ? bb.upper[bb.upper.length - 1].value : cur;
    const bbL = bb.lower.length > 0 ? bb.lower[bb.lower.length - 1].value : cur;
    const bbW = (bbU - bbL) / (lSMA20 || 0.001);
    const squeeze = bbW < 0.05 ? 'squeeze' : 'normal';

    const kcU = kc.upper.length > 0 ? kc.upper[kc.upper.length - 1].value : cur;
    const kcL = kc.lower.length > 0 ? kc.lower[kc.lower.length - 1].value : cur;
    const kcB = cur > kcU ? 'upper' : cur < kcL ? 'lower' : 'none';

    const tBull = lEF > lES && lADX > 25;
    const tBear = lEF < lES && lADX > 25;

    let score = 0;
    if (lRSI < 30) score += 2;
    if (lRSI > 70) score -= 2;
    if (tBull) score += 3;
    if (tBear) score -= 3;
    if (kcB === 'upper') score += 2;
    if (kcB === 'lower') score -= 2;

    let sentiment, confidence;
    if (score > 2) { sentiment = 'bullish'; confidence = Math.min(0.5 + Math.abs(score) * 0.06, 0.9); }
    else if (score < -2) { sentiment = 'bearish'; confidence = Math.min(0.5 + Math.abs(score) * 0.06, 0.9); }
    else { sentiment = 'neutral'; confidence = 0.3; }
    if (lADX > 30) confidence = Math.min(confidence + 0.1, 0.95);
    else if (lADX < 20) confidence = Math.max(confidence - 0.1, 0.1);

    const volPct = lATR / cur;
    const volL = volPct > 0.03 ? 'high' : volPct > 0.015 ? 'moderate' : 'low';
    const trend = tBull ? 'bullish' : tBear ? 'bearish' : 'neutral';

    return {
      symbol,
      report_type: 'market_analysis',
      title: `${symbol} Technical Analysis — ${trend.charAt(0).toUpperCase() + trend.slice(1)}`,
      summary: `${symbol}: ${sentiment.toUpperCase()} ${Math.round(confidence * 100)}% conf. RSI ${lRSI.toFixed(1)}, ADX ${lADX.toFixed(1)}.`,
      details: {
        trend, volatility: volL,
        indicators: {
          rsi: Math.round(lRSI * 10) / 10,
          adx: Math.round(lADX * 10) / 10,
          atr_pct: Math.round(volPct * 10000) / 100,
          bb_width: Math.round(bbW * 1000) / 1000,
          keltner_breakout: kcB,
          obv_trend: obvT,
          squeeze_detected: squeeze === 'squeeze',
          ema_cross: lEF > lES ? 'bullish' : 'bearish',
        },
      },
      sentiment,
      confidence: Math.round(confidence * 100) / 100,
      source: 'signal_engine',
    };
  }

  async function batchGenerateResearch() {
    if (researchInProgress) {
      // Don't silently discard — schedule a retry after the current run finishes
      retryPending = true;
      return;
    }
    researchInProgress = true;
    const status = document.getElementById('researchStatus');
    const label = status.querySelector('.rs-label');
    status.style.display = 'flex';
    status.querySelector('.rs-spinner').style.display = 'inline-block';

    const allSymbols = aggregated.map(a => a.symbol).filter(s => s && s !== 'UNKNOWN');
    if (allSymbols.length === 0) {
      label.textContent = 'No symbols to research';
      status.querySelector('.rs-spinner').style.display = 'none';
      setTimeout(() => { status.style.display = 'none'; }, 3000);
      researchInProgress = false;
      return;
    }

    // Check which symbols already have today's research.
    // Use UTC day boundary so behaviour is deterministic across timezones.
    const todayUtc = new Date().toISOString().slice(0, 10) + 'T00:00:00.000Z';
    // Fetch ALL already-researched symbols today with pagination
    const done = new Set();
    {
      let offset = 0; const PAGE = 1000;
      while (true) {
        const { data: page } = await supabaseClient.from('crypto_research')
          .select('symbol').gte('created_at', todayUtc).order('created_at', { ascending: true }).range(offset, offset + PAGE - 1);
        if (!page || page.length === 0) break;
        page.forEach(r => done.add(normalizeSymbol(r.symbol)));
        if (page.length < PAGE) break;
        offset += PAGE;
      }
    }

    const need = allSymbols.filter(s => !done.has(s));
    if (need.length === 0) {
      label.textContent = 'All symbols researched today ✓';
      setTimeout(() => { status.style.display = 'none'; }, 4000);
      researchInProgress = false;
      return;
    }

    try {
    label.textContent = `Fetching data for ${need.length} symbols…`;
    let completed = 0;

    // Fetch OHLCV in parallel with concurrency limit of 6
    const TIMEFRAMES = ['1d', '1h', '4h'];
    const chunk = (arr, sz) => { const r = []; for (let i = 0; i < arr.length; i += sz) r.push(arr.slice(i, i + sz)); return r; };
    const entries = [];
    for (const batch of chunk(need, 6)) {
      const results = await Promise.allSettled(batch.map(async (symbol) => {
        // Try timeframes in order (1d → 1h → 4h), use first with enough data
        // Also try symbol variants (-USD, -USDT, bare) since crypto_historical may use different format
        let bars = null;
        const variants = symbolVariantsFor(symbol);
        for (const tf of TIMEFRAMES) {
          for (const sv of variants) {
            const { data, error } = await supabaseClient.from('crypto_historical')
              .select('datetime, open, high, low, close, volume')
              .eq('symbol', sv).eq('timeframe', tf)
              .order('datetime', { ascending: false }).limit(250);
            if (!error && data && data.length >= 30) {
              data.reverse();
              bars = data.map(d => ({ time: d.datetime, open: d.open, high: d.high, low: d.low, close: d.close, value: d.volume }));
              break;
            }
          }
          if (bars) break;
        }
        completed++;
        if (bars) {
          // Tier 1: full OHLCV-based technical analysis
          const entry = computeResearchEntry(symbol, bars);
          if (entry) { label.textContent = `Researched ${completed}/${need.length} (${symbol})…`; return entry; }
        }
        // Tier 2: strategy-based insight (use aggregated data from loadAll)
        const symData = aggregated.find(a => a.symbol === symbol);
        const strategies = symData?.strategies || [];
        const price = symData?.latestPrice || null;
        const stratEntry = createStrategyInsight(symbol, price, strategies);
        if (stratEntry) { label.textContent = `Researched ${completed}/${need.length} (${symbol}: strategy)…`; return stratEntry; }
        // Tier 3: price-only snapshot
        label.textContent = `Researched ${completed}/${need.length} (${symbol}: price only)…`;
        return createPriceInsight(symbol, price);
      }));
      for (const r of results) { if (r.status === 'fulfilled' && r.value) entries.push(r.value); }
    }

    if (entries.length === 0) {
      label.textContent = 'No research could be generated (insufficient data)';
      setTimeout(() => { status.style.display = 'none'; }, 5000);
      return;
    }

    label.textContent = `Saving ${entries.length} entries…`;
    const { error } = await supabaseClient.from('crypto_research').insert(entries);
    if (error) {
      console.warn('Batch insert error:', error);
      label.textContent = `DB error: ${error.message}`;
    } else {
      label.textContent = `${entries.length} entries saved ✓`;
    }
    status.querySelector('.rs-spinner').style.display = 'none';

    // Refresh dashboard
    await loadAll();
    } finally {
      researchInProgress = false;
      if (retryPending) {
        retryPending = false;
        batchGenerateResearch().catch(e => console.warn('Retry research error:', e));
      }
    }
    setTimeout(() => { status.style.display = 'none'; }, 6000);
  }

  // ── Price Change Loader ──
  async function loadPriceChanges() {
    const symbols = aggregated.map(a => a.symbol).filter(s => s && s !== 'UNKNOWN');
    if (symbols.length === 0) return;
    const TIMEFRAMES = ['1d', '1h', '4h'];
    const chunk = (arr, sz) => { const r = []; for (let i = 0; i < arr.length; i += sz) r.push(arr.slice(i, i + sz)); return r; };
    const result = {};
    for (const batch of chunk(symbols, 6)) {
      await Promise.allSettled(batch.map(async (symbol) => {
        // crypto_historical stores symbols in -USDT format, but aggregated
        // symbols come from crypto_data (mixed -USD/-USDT, or bare symbol names).
        // Use the shared helper to build variants.
        const symbolVariants = symbolVariantsFor(symbol);
        let foundAny = false;
        for (const tf of TIMEFRAMES) {
          let data = null;
          for (const sv of symbolVariants) {
            const resp = await supabaseClient.from('crypto_historical')
              .select('close, datetime')
              .eq('symbol', sv).eq('timeframe', tf)
              .order('datetime', { ascending: false }).limit(tf === '1d' ? 370 : tf === '1h' ? 720 : 180);
            if (resp.data && resp.data.length >= 2) { data = resp.data; break; }
          }
          if (!data) continue;
          const cur = data[0].close;
          const findClosest = (targetTs) => {
            const target = Date.parse(targetTs);
            for (const d of data) {
              const t = Date.parse(d.datetime);
              if (t <= target) return d.close;
            }
            return null;
          };
          const now = Date.now();
          const day = 86400000;
          const ch = {};
          if (data.length >= 2) {
            const prev = data.find(d => Date.parse(d.datetime) <= now - day) || data[data.length - 1];
            ch.d1 = prev ? (cur - prev.close) / prev.close * 100 : null;
          }
          if (tf === '1d' && data.length >= 7) {
            const w = findClosest(new Date(now - 7 * day).toISOString());
            ch.w1 = w ? (cur - w) / w * 100 : null;
          } else if (tf !== '1d' && data.length >= 170) {
            const w = findClosest(new Date(now - 7 * day).toISOString());
            ch.w1 = w ? (cur - w) / w * 100 : null;
          }
          if (tf === '1d' && data.length >= 30) {
            const m = findClosest(new Date(now - 30 * day).toISOString());
            ch.m1 = m ? (cur - m) / m * 100 : null;
          }
          if (tf === '1d' && data.length >= 365) {
            const y = findClosest(new Date(now - 365 * day).toISOString());
            ch.y1 = y ? (cur - y) / y * 100 : null;
          }
          if (ch.d1 != null) { result[symbol] = ch; foundAny = true; return; }
        }
        if (!result[symbol]) {
          result[symbol] = {};
          if (!foundAny) console.warn('loadPriceChanges: no price data found for symbol', symbol, '(variants tried:', [...symbolVariants], ')');
        }
      }));
    }
    priceChanges = result;
    deriveMomentumValues();
    applyFilters();
  }

  // ── Load ──
  async function loadAll() {
    try {
      document.getElementById('tableBody').innerHTML =
        '<tr><td colspan="9"><div class="loading">Loading research data…</div></td></tr>';

      let sessionId = null;
      try { sessionId = localStorage.getItem('paperSessionId'); } catch(e) { /* privacy mode — ignore */ }
      // First get latest research run_id to scope strategy_results
      const runResp = await supabaseClient
        .from('research_runs')
        .select('run_id')
        .order('run_timestamp', { ascending: false })
        .limit(1)
        .maybeSingle();

      let latestRunId = runResp.data?.run_id || null;
      if (runResp.error) console.warn('research_runs query:', runResp.error);

      const [researchResp, stratsResp, watchResp, posResp] = await Promise.all([
        (async () => {
          const PAGE = 1000;
          let offset = 0;
          let all = [];
          while (true) {
            const { data: page, error } = await supabaseClient
              .from('crypto_research')
              .select('*')
              .order('created_at', { ascending: false })
              .range(offset, offset + PAGE - 1);
            if (error) { console.warn('research query (page):', error); break; }
            if (!page || page.length === 0) break;
            all.push(...page);
            if (page.length < PAGE) break;
            offset += PAGE;
          }
          return { data: all, error: null };
        })(),
        // Filter strategy_results to latest run_id only to avoid duplicate / stale results
        latestRunId
          ? supabaseClient.from('strategy_results').select('strategy_name, symbol, timeframe, sharpe_ratio, win_rate, total_return_pct, trade_count').gte('trade_count', 30).eq('run_id', latestRunId).order('sharpe_ratio', { ascending: false })
          : supabaseClient.from('strategy_results').select('strategy_name, symbol, timeframe, sharpe_ratio, win_rate, total_return_pct, trade_count').gte('trade_count', 30).order('sharpe_ratio', { ascending: false }),
        supabaseClient.from('crypto_data').select('symbol, current_price').order('updated_at', { ascending: false }),
        supabaseClient.from('paper_positions').select('symbol, side, quantity, entry_price').eq('session_id', sessionId ?? '__none__'),
      ]);

      // Log any Supabase-level errors (returned in response, not thrown)
      if (researchResp.error) console.warn('research query:', researchResp.error);
      if (stratsResp.error) console.warn('strategy_results query:', stratsResp.error);
      if (watchResp.error) console.warn('crypto_data query:', watchResp.error);
      if (posResp.error) console.warn('paper_positions query:', posResp.error);

      const researchData = researchResp.data || [];

      // Normalize all symbols to a canonical form (-USD) so cross-table matching works
      researchData.forEach(r => { r.symbol = normalizeSymbol(r.symbol); });
      const strategyData = (stratsResp.data || []).map(s => ({
        ...s,
        symbol: normalizeSymbol(s.symbol)
      }));
      watchlistData = (watchResp.data || []).map(w => ({
        ...w,
        symbol: normalizeSymbol(w.symbol)
      }));
      const positionsData = (posResp.data || []).map(p => ({
        ...p,
        symbol: normalizeSymbol(p.symbol)
      }));

      // Group research by symbol
      const symbolMap = {};
      for (const r of researchData) {
        const sym = r.symbol || 'UNKNOWN';
        if (!symbolMap[sym]) symbolMap[sym] = { symbol: sym, entries: [], sentiments: [], confidences: [] };
        symbolMap[sym].entries.push(r);
        if (r.sentiment) symbolMap[sym].sentiments.push(r.sentiment);
        if (r.confidence != null) symbolMap[sym].confidences.push(r.confidence);
      }

      // All known symbols from all sources
      const allSymbols = [...new Set([
        ...Object.keys(symbolMap),
        ...strategyData.map(s => s.symbol).filter(Boolean),
        ...watchlistData.map(w => w.symbol).filter(Boolean)
      ])].sort();

      for (const sym of allSymbols) {
        if (!symbolMap[sym]) symbolMap[sym] = { symbol: sym, entries: [], sentiments: [], confidences: [] };
      }

      aggregated = allSymbols.map(sym => {
        const g = symbolMap[sym];
        const latest = g.entries[0] || null;
        const sentiments = g.sentiments;
        const confidences = g.confidences;

        const bullCount = sentiments.filter(s => s === 'bullish').length;
        const bearCount = sentiments.filter(s => s === 'bearish').length;
        const neutCount = sentiments.filter(s => s === 'neutral').length;
        let aggSentiment = 'neutral';
        if (bullCount > bearCount && bullCount > neutCount) aggSentiment = 'bullish';
        else if (bearCount > bullCount && bearCount > neutCount) aggSentiment = 'bearish';
        // Tie: when bullCount === bearCount (or both < neutCount), falls through to neutral.
        // This is a deliberate conservative default — no false signal on split consensus.

        const avgConfidence = confidences.length > 0
          ? confidences.reduce((a, b) => a + b, 0) / confidences.length
          : null;

        const symStrats = strategyData.filter(s => s.symbol === sym);
        let bestStrat = null;
        if (symStrats.length > 0) {
          bestStrat = symStrats.reduce((b, s) => (s.sharpe_ratio || 0) > (b.sharpe_ratio || 0) ? s : b, symStrats[0]);
        }

        const latestPrice = watchlistData.find(w => w.symbol === sym)?.current_price ?? null;
        const openPos = positionsData.find(p => p.symbol === sym);

        return {
          symbol: sym,
          latestEntry: latest,
          entryCount: g.entries.length,
          sentiment: aggSentiment,
          confidence: avgConfidence,
          bestStrat,
          bestStratWinRate: bestStrat ? bestStrat.win_rate : null,
          latestPrice,
          openPos,
          entries: g.entries,
          strategies: symStrats.slice(0, 10),
          bullCount, bearCount, neutCount,
        };
      });

      // Load price changes for all symbols (from OHLCV data).
      // applyFilters() is called inside loadPriceChanges after price data is ready,
      // so we skip calling it here to avoid a flash of incorrectly sorted rows.
      await loadPriceChanges();
      // Auto-trigger batch research for symbols that don't have today's research yet.
      const todayUtcAuto = new Date().toISOString().slice(0, 10) + 'T00:00:00.000Z';
      const autoDone = new Set(
        researchData
          .filter(r => r.created_at >= todayUtcAuto)
          .map(r => normalizeSymbol(r.symbol))
      );
      const autoNeed = aggregated.map(a => a.symbol).filter(s => s && s !== 'UNKNOWN' && !autoDone.has(s));
      if (autoNeed.length > 0) {
        setTimeout(() => { batchGenerateResearch().catch(e => console.warn('Batch research error:', e)); }, 300);
      }
    } catch(e) {
      console.error('Load error:', e);
      document.getElementById('tableBody').innerHTML =
        `<tr><td colspan="9"><div class="empty-state">
          <h3>Failed to load data</h3>
          <p>${escapeHtml(e.message)}</p>
        </div></td></tr>`;
    }
  }

  // ── Filter + Sort + Render ──
  function applyFilters() {
    const search = document.getElementById('searchInput').value.toLowerCase().trim();
    const sentFilter = document.getElementById('sentimentFilter').value;

    let filtered = aggregated.filter(a => {
      if (search && !a.symbol.toLowerCase().includes(search)) return false;
      if (sentFilter !== 'all' && effectiveSentiment(a) !== sentFilter) return false;
      return true;
    });

    filtered.sort((a, b) => {
      let cmp = 0;
      switch (sortColumn) {
        case 'symbol': cmp = a.symbol.localeCompare(b.symbol); break;
        case 'change': {
          const ca = priceChanges[a.symbol]?.[changeTf];
          const cb = priceChanges[b.symbol]?.[changeTf];
          // Entries with no data sort to the end regardless of direction
          if (ca == null && cb == null) cmp = 0;
          else if (ca == null) cmp = 1;
          else if (cb == null) cmp = -1;
          else {
            // Sort by sentiment category first, then by value within category
            // bullish (>1) = 2, neutral (-1..1) = 1, bearish (<-1) = 0
            const sa = ca > 1 ? 2 : ca < -1 ? 0 : 1;
            const sb = cb > 1 ? 2 : cb < -1 ? 0 : 1;
            cmp = sa - sb;
            // Within same category, sort by actual value
            if (cmp === 0) cmp = ca - cb;
          }
          break;
        }
        case 'sentiment': {
          const order = { bullish: 2, neutral: 1, bearish: 0 };
          cmp = (order[effectiveSentiment(a)] ?? 1) - (order[effectiveSentiment(b)] ?? 1);
          break;
        }
        case 'confidence': {
          const ca = effectiveConfidence(a);
          const cb = effectiveConfidence(b);
          if (ca == null && cb == null) cmp = 0;
          else if (ca == null) cmp = 1;
          else if (cb == null) cmp = -1;
          else cmp = ca - cb;
          break;
        }
        case 'bestStrat': {
          const na = (a.bestStrat?.strategy_name || '').replace(/_/g, ' ');
          const nb = (b.bestStrat?.strategy_name || '').replace(/_/g, ' ');
          cmp = na.localeCompare(nb);
          break;
        }
        case 'winRate': cmp = (a.bestStratWinRate || 0) - (b.bestStratWinRate || 0); break;
        case 'lastResearch': {
          const aT = a.latestEntry ? new Date(a.latestEntry.created_at).getTime() : 0;
          const bT = b.latestEntry ? new Date(b.latestEntry.created_at).getTime() : 0;
          cmp = aT - bT;
          break;
        }
        case 'entries': cmp = a.entryCount - b.entryCount; break;
      }
      return sortDir === 'desc' ? -cmp : cmp;
    });

    renderTable(filtered);
    updateSortArrows();
    updateStats(filtered);
  }

  // ── Render Table ──
  function renderTable(rows) {
    const tbody = document.getElementById('tableBody');

    if (rows.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9"><div class="empty-state">
        <h3>No results</h3>
        <p>Try adjusting your filters</p>
      </div></td></tr>`;
      return;
    }

    tbody.innerHTML = rows.map(a => {
      const open = expandedSymbol === a.symbol;
      const confStr = effectiveConfidence(a) != null ? Math.round(effectiveConfidence(a) * 100) + '%' : '—';
      const bestName = a.bestStrat
        ? (a.bestStrat.strategy_name || 'Unknown').replace(/_/g, ' ')
        : '—';
      const winRateStr = a.bestStratWinRate != null ? a.bestStratWinRate.toFixed(1) + '%' : '—';
      const lastTime = a.latestEntry ? timeAgo(a.latestEntry.created_at) : '—';
      const priceStr = a.latestPrice != null
        ? '$' + Number(a.latestPrice).toLocaleString(undefined, { minimumFractionDigits: 2 })
        : '';
      const posIcon = a.openPos ? (a.openPos.side === 'long' ? '🟢' : '🔴') : '';

      // Price change for selected timeframe
      const pc = priceChanges[a.symbol] || {};
      const chVal = pc[changeTf];
      let chStr = '—', chCls = '';
      if (chVal != null) {
        chStr = (chVal >= 0 ? '+' : '') + chVal.toFixed(2) + '%';
        chCls = chVal > 0 ? 'pos' : chVal < 0 ? 'neg' : '';
      }

      return `
        <tr class="clickable ${open ? 'expanded' : ''}" data-symbol="${escapeHtml(a.symbol)}">
          <td><span class="expand-icon ${open ? 'open' : ''}">▶</span></td>
          <td><strong>${escapeHtml(a.symbol)}</strong> ${posIcon}
            ${priceStr ? `<span style="font-size:11px;color:var(--text-muted);margin-left:4px;">${priceStr}</span>` : ''}
          </td>
          <td class="num ${chCls}" style="font-size:12px;font-weight:500;">${chStr}</td>
          <td>${sentimentBadge(effectiveSentiment(a))}</td>
          <td class="num">${confStr}</td>
          <td class="num" style="font-size:11px;">${escapeHtml(bestName)}</td>
          <td class="num ${a.bestStratWinRate == null ? '' : a.bestStratWinRate > 50 ? 'pos' : a.bestStratWinRate < 50 ? 'neg' : ''}">${winRateStr}</td>
          <td style="font-size:11px;color:var(--text-muted);">${lastTime}</td>
          <td class="num">${a.entryCount}</td>
        </tr>
        <tr class="detail-row ${open ? '' : 'hidden'}">
          <td colspan="9">
            <div class="detail-content">${detailHTML(a)}</div>
          </td>
        </tr>
      `;
    }).join('');
  }

  function detailHTML(a) {
    const t = a.bullCount + a.bearCount + a.neutCount;
    // Round first two with Math.round, set third so they always sum to 100%
    const bullP = t > 0 ? Math.round(100 * a.bullCount / t) : 0;
    const bearP = t > 0 ? Math.round(100 * a.bearCount / t) : 0;
    let neutP = 100 - bullP - bearP;
    if (neutP < 0) neutP = 0;

    // Research history (latest 8)
    const rItems = (a.entries || []).slice(0, 8).map(e => `
      <div class="research-item">
        <div class="meta">${timeAgo(e.created_at)} · ${sentimentBadge(e.sentiment)} ${e.confidence ? Math.round(e.confidence * 100) + '%' : ''}</div>
        <div>${escapeHtml(e.title || 'Analysis')}</div>
        <div style="font-size:11px;color:var(--text-muted);margin-top:2px;">${escapeHtml((e.summary || '').slice(0, 140))}</div>
      </div>
    `).join('') || '<div style="font-size:12px;color:var(--text-muted);padding:4px 0;">No research entries.</div>';

    // Top 5 strategies
    const strats = (a.strategies || []).slice(0, 5).map(s => {
      const sh = s.sharpe_ratio != null ? s.sharpe_ratio.toFixed(2) : '—';
      const wr = s.win_rate != null ? s.win_rate.toFixed(1) + '%' : '—';
      const ret = s.total_return_pct != null ? (s.total_return_pct >= 0 ? '+' : '') + s.total_return_pct.toFixed(1) + '%' : '—';
      const tf = s.timeframe || '—';
      const name = (s.strategy_name || '?').replace(/_/g, ' ');
      return `<div class="strat-row">
        <span><strong>${escapeHtml(name)}</strong> <span style="color:var(--text-muted);font-size:11px;">${tf}</span></span>
        <span style="display:flex;gap:12px;">
          <span class="num">Sharpe: ${sh}</span>
          <span class="num ${s.win_rate == null ? '' : s.win_rate > 50 ? 'pos' : s.win_rate < 50 ? 'neg' : ''}">WR: ${wr}</span>
          <span class="num ${s.total_return_pct == null ? '' : s.total_return_pct > 0 ? 'pos' : s.total_return_pct < 0 ? 'neg' : ''}">Ret: ${ret}</span>
        </span>
      </div>`;
    }).join('') || '<div style="font-size:12px;color:var(--text-muted);padding:4px 0;">No strategy results for this pair.</div>';

    const posHtml = a.openPos
      ? (() => {
          const qty = a.openPos.quantity != null ? Number(a.openPos.quantity) : null;
          const entry = a.openPos.entry_price != null ? Number(a.openPos.entry_price) : null;
          return `<div style="font-size:12px;">
            ${a.openPos.side === 'long' ? '🟢' : '🔴'} ${a.openPos.side.toUpperCase()} ${qty != null ? qty.toFixed(4) : '—'}
            <span style="color:var(--text-muted);margin-left:8px;">Entry: ${entry != null ? '$' + entry.toFixed(2) : '—'}</span>
          </div>`;
        })()
      : '<div style="font-size:12px;color:var(--text-muted);padding:4px 0;">No open position.</div>';

    return `
      <div class="detail-section full">
        <h4>Consensus</h4>
        <div style="display:flex;gap:16px;font-size:13px;">
          <span>🟢 Bullish: <strong>${a.bullCount}</strong> (${bullP}%)</span>
          <span>🔴 Bearish: <strong>${a.bearCount}</strong> (${bearP}%)</span>
          <span>⚪ Neutral: <strong>${a.neutCount}</strong> (${neutP}%)</span>
        </div>
        ${t > 0 ? `<div class="consensus-bar"><div class="bull" style="width:${bullP}%"></div><div class="neut" style="width:${neutP}%"></div><div class="bear" style="width:${bearP}%"></div></div>` : ''}
      </div>
      <div class="detail-section">
        <h4>Research History (${a.entryCount}${a.entryCount !== t ? `, ${t} with sentiment` : ''})</h4>
        ${rItems}
      </div>
      <div class="detail-section">
        <h4>Top Strategies</h4>
        ${strats}
      </div>
      <div class="detail-section">
        <h4>Paper Position</h4>
        ${posHtml}
      </div>
      <div class="detail-section">
        <h4>Quick Facts</h4>
        <div style="font-size:12px;line-height:1.8;">
          <div>Research sentiment: ${sentimentBadge(a.sentiment)}</div>
          <div>Research avg confidence: <strong>${a.confidence != null ? Math.round(a.confidence * 100) + '%' : '—'}</strong></div>
          <div>Price: <strong>${a.latestPrice != null ? '$' + Number(a.latestPrice).toLocaleString(undefined, { minimumFractionDigits: 2 }) : '—'}</strong></div>
          ${a.bestStrat ? `<div>Best strat: <strong>${escapeHtml((a.bestStrat.strategy_name || '?').replace(/_/g, ' '))}</strong> on ${a.bestStrat.timeframe || '—'}</div>` : ''}
        </div>
      </div>
    `;
  }

  function updateStats(filteredRows) {
    const data = filteredRows || aggregated;
    document.getElementById('totalCount').innerText = `${data.length} pairs`;
    document.getElementById('bullCount').innerText = data.filter(a => effectiveSentiment(a) === 'bullish').length;
    document.getElementById('bearCount').innerText = data.filter(a => effectiveSentiment(a) === 'bearish').length;
    document.getElementById('neutCount').innerText = data.filter(a => effectiveSentiment(a) === 'neutral').length;
  }

  function updateSortArrows() {
    document.querySelectorAll('.sort-arrow').forEach(el => {
      const col = el.dataset.col;
      if (col === sortColumn) {
        el.textContent = sortDir === 'asc' ? ' ▲' : ' ▼';
        el.parentElement.classList.add('active-sort');
      } else {
        el.textContent = '';
        el.parentElement.classList.remove('active-sort');
      }
    });
  }

  // ── Change Timeframe Toggle ──
  const TF_LABELS = { d1: '1D', w1: '1W', m1: '1M', y1: '1Y' };
  window.setChangeTf = function(tf) {
    changeTf = tf;
    document.querySelectorAll('.tf-btn').forEach(b => {
      const isActive = b.dataset.tf === tf;
      b.style.color = isActive ? 'var(--text)' : 'var(--text-muted)';
      b.style.borderColor = isActive ? 'var(--accent)' : 'var(--border)';
    });
    document.getElementById('changeLabel').textContent = TF_LABELS[tf] || tf.toUpperCase();
    deriveMomentumValues();
    applyFilters();
  };

  // ── Expand / Collapse ──
  window.toggleExpand = function(symbol) {
    expandedSymbol = expandedSymbol === symbol ? null : symbol;
    applyFilters();
  };

  // Event delegation for row expansion (replaces XSS-vulnerable inline onclick)
  document.getElementById('tableBody').addEventListener('click', (e) => {
    const row = e.target.closest('tr.clickable');
    if (!row) return;
    const symbol = row.dataset.symbol;
    if (symbol) toggleExpand(symbol);
  });

  // ── Events ──
  document.getElementById('searchInput').addEventListener('input', applyFilters);
  document.getElementById('sentimentFilter').addEventListener('change', applyFilters);

  // ── Start ──
  loadAll();
