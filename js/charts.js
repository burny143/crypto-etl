// charts.js — Trading terminal UI logic
// Depends on shared.js (must be loaded first)

// Indicator Definitions
        const INDICATOR_DEFS = [
            { name: "sma", label: "SMA", color: "#f59e0b", scale: "overlay", params: [{ key: "period", label: "Period", min: 2, max: 200, def: 20 }] },
            { name: "ema", label: "EMA", color: "#8b5cf6", scale: "overlay", params: [{ key: "period", label: "Period", min: 2, max: 200, def: 20 }] },
            { name: "rsi", label: "RSI", color: "#06b6d4", scale: "oscillator", params: [{ key: "period", label: "Period", min: 2, max: 50, def: 14 }] },
            { name: "macd", label: "MACD", color: "#3b82f6", scale: "oscillator", params: [
                { key: "fast", label: "Fast", min: 2, max: 100, def: 12 },
                { key: "slow", label: "Slow", min: 2, max: 200, def: 26 },
                { key: "signal", label: "Signal", min: 2, max: 50, def: 9 },
            ]},
            { name: "bb", label: "Bollinger", color: "#ec4899", scale: "overlay", params: [
                { key: "period", label: "Period", min: 2, max: 100, def: 20 },
                { key: "std", label: "Std", min: 0.5, max: 4, def: 2, step: 0.1 },
            ]},
            { name: "vwap", label: "VWAP", color: "#14b8a6", scale: "overlay", params: [] },
            { name: "adx", label: "ADX", color: "#f97316", scale: "oscillator", params: [{ key: "period", label: "Period", min: 2, max: 50, def: 14 }] },
            { name: "atr", label: "ATR", color: "#a78bfa", scale: "oscillator", params: [{ key: "period", label: "Period", min: 2, max: 50, def: 14 }] },
            { name: "obv", label: "OBV", color: "#22d3ee", scale: "oscillator", params: [] },
            { name: "stoch_rsi", label: "Stoch RSI", color: "#e879f9", scale: "oscillator", params: [
                { key: "period", label: "Period", min: 2, max: 50, def: 14 },
                { key: "smooth_k", label: "K", min: 1, max: 10, def: 3 },
                { key: "smooth_d", label: "D", min: 1, max: 10, def: 3 },
            ]},
            { name: "vol_ratio", label: "Vol Ratio", color: "#34d399", scale: "oscillator", params: [{ key: "period", label: "Period", min: 2, max: 100, def: 20 }] },
            { name: "kc", label: "Keltner", color: "#fb923c", scale: "overlay", params: [
                { key: "period", label: "Period", min: 2, max: 100, def: 20 },
                { key: "mult", label: "Mult", min: 0.5, max: 4, def: 2, step: 0.1 },
            ]},
        ];

        // State
        let currentSymbol = ""; // Will be set after watchlist loads to the first real symbol
        let loadRequestId = 0; // Incremented by each async loader; stale responses check and bail out
        let currentTimeframe = "1d";
        let chart, candleSeries, volumeSeries, candleMarkers;
        let activeIndicators = new Map(); // key -> { series, seriesKey }
        let historicalData = [];
        let signalConditions = [];
        let signalChartMarkers = [];
        // Cache of latest closes for each symbol (populated by loadChartData)
        let symbolPriceCache = {};

        // ── Indicator Computation (pure JS — no backend needed) ──

        function seriesFrom(arr, times) {
            return arr.map((v, i) => ({ time: times[i], value: v })).filter(p => p.value != null && !isNaN(p.value));
        }


        function computeMACD(data, fast, slow, signal) {
            fast = Math.floor(Number(fast));
            slow = Math.floor(Number(slow));
            signal = Math.floor(Number(signal));
            if (!Number.isFinite(fast) || !Number.isFinite(slow) || !Number.isFinite(signal) || fast < 1 || slow < 1 || signal < 1) {
                return { macd: [], signal: [], hist: [] };
            }
            if (fast >= slow) {
                console.warn('computeMACD: fast period must be less than slow period');
                return { macd: [], signal: [], hist: [] };
            }
            const close = getClose(data);
            if (close.length < slow + 1) return { macd: [], signal: [], hist: [] };
            const emaFast = computeEMA(data, fast);
            const emaSlow = computeEMA(data, slow);
            // Align lengths and compute macd line
            const offset = emaFast.length - emaSlow.length;
            const macdLine = [];
            for (let i = 0; i < emaSlow.length; i++) {
                macdLine.push(emaFast[i + offset].value - emaSlow[i].value);
            }
            const times = emaSlow.map(p => p.time);
            // Signal line = EMA of macd line
            const k = 2 / (signal + 1);
            let sigVal;
            const signalLine = [];
            for (let i = 0; i < macdLine.length; i++) {
                if (i < signal - 1) { signalLine.push(null); continue; }
                if (i === signal - 1) sigVal = macdLine.slice(0, signal).reduce((a, b) => a + b, 0) / signal;
                else sigVal = macdLine[i] * k + sigVal * (1 - k);
                signalLine.push({ time: times[i], value: sigVal });
            }
            const hist = [];
            for (let i = 0; i < macdLine.length; i++) {
                if (signalLine[i] === null) continue;
                hist.push({ time: times[i], value: macdLine[i] - signalLine[i].value });
            }
            return {
                macd: macdLine.map((v, i) => ({ time: times[i], value: v })).filter(p => p.value != null),
                signal: signalLine.filter(p => p !== null && p.value != null),
                hist: hist,
            };
        }


        function computeVWAP(data) {
            let cumPV = 0, cumV = 0;
            const result = [];
            let lastSession = null;
            for (const d of data) {
                const session = typeof d.time === 'number'
                    ? new Date(d.time * 1000).toISOString().split('T')[0]
                    : String(d.time).split('T')[0];

                // Intraday charts reset once per calendar day, but daily charts
                // use each bar as its own session by construction. To avoid
                // collapsing to typical price on 1d, accumulate across the full
                // visible series instead of resetting on every bar.
                const isDailyTimeframe = typeof d.time === 'string' && d.time.includes('-') && d.time.length === 10;
                if (!isDailyTimeframe && lastSession !== null && session !== lastSession) {
                    cumPV = 0;
                    cumV = 0;
                }
                lastSession = session;

                const tp = (d.high + d.low + d.close) / 3;
                cumPV += tp * d.value;
                cumV += d.value;
                result.push({ time: d.time, value: cumPV / (cumV || 0.001) });
            }
            return result;
        }


        function computeStochRSI(data, period, smoothK, smoothD) {
            period = Math.floor(Number(period));
            smoothK = Math.floor(Number(smoothK));
            smoothD = Math.floor(Number(smoothD));
            if (!Number.isFinite(period) || period < 1 || !Number.isFinite(smoothK) || smoothK < 1 || !Number.isFinite(smoothD) || smoothD < 1) {
                return { k: [], d: [] };
            }
            const rsi = computeRSI(data, period);
            if (rsi.length < period) return { k: [], d: [] };
            const vals = rsi.map(p => p.value);
            const times = rsi.map(p => p.time);
            const stoch = [];
            for (let i = period - 1; i < vals.length; i++) {
                const min = Math.min(...vals.slice(i - period + 1, i + 1));
                const max = Math.max(...vals.slice(i - period + 1, i + 1));
                stoch.push(100 * (vals[i] - min) / ((max - min) || 0.001));
            }
            const stochTimes = times.slice(period - 1);
            const k = [];
            for (let i = smoothK - 1; i < stoch.length; i++) {
                let sum = 0;
                for (let j = 0; j < smoothK; j++) sum += stoch[i - j];
                k.push({ time: stochTimes[i], value: sum / smoothK });
            }
            const d = [];
            for (let i = smoothD - 1; i < k.length; i++) {
                let sum = 0;
                for (let j = 0; j < smoothD; j++) sum += k[i - j].value;
                d.push({ time: k[i].time, value: sum / smoothD });
            }
            return { k, d };
        }

        function computeVolRatio(data, period) {
            period = Math.floor(Number(period));
            if (!Number.isFinite(period) || period < 1) return [];
            const volume = getVolume(data), times = getTime(data);
            if (volume.length < period) return [];
            const result = [];
            for (let i = period - 1; i < volume.length; i++) {
                let sum = 0;
                for (let j = 0; j < period; j++) sum += volume[i - j];
                const avg = sum / period;
                result.push({ time: times[i], value: volume[i] / (avg || 0.001) });
            }
            return result;
        }


        // ── Indicator dispatch ──
        const INDICATOR_COMPUTERS_JS = {
            sma: (data, p) => computeSMA(data, p.period || 20),
            ema: (data, p) => computeEMA(data, p.period || 20),
            rsi: (data, p) => computeRSI(data, p.period || 14),
            macd: (data, p) => computeMACD(data, p.fast || 12, p.slow || 26, p.signal || 9),
            bb: (data, p) => computeBB(data, p.period || 20, p.std || 2.0),
            vwap: (data, p) => computeVWAP(data),
            adx: (data, p) => computeADX(data, p.period || 14),
            atr: (data, p) => computeATR(data, p.period || 14),
            obv: (data, p) => computeOBV(data),
            stoch_rsi: (data, p) => computeStochRSI(data, p.period || 14, p.smooth_k || 3, p.smooth_d || 3),
            vol_ratio: (data, p) => computeVolRatio(data, p.period || 20),
            kc: (data, p) => computeKC(data, p.period || 20, p.mult || 2.0),
        };

        function computeIndicator(name, params) {
            const fn = INDICATOR_COMPUTERS_JS[name];
            if (!fn) return null;
            try { return fn(historicalData, params); } catch(e) { console.error(`Indicator ${name} error:`, e); return null; }
        }

        function extractSeries(result, valueKey) {
            if (!result) return null;
            if (Array.isArray(result)) return result;
            if (typeof result === 'object' && result !== null) {
                if (valueKey) {
                    if (result[valueKey]) return result[valueKey];
                    console.warn(`extractSeries: valueKey "${valueKey}" not found on result object; falling back to first array property`);
                }
                // Return first array property
                const keys = Object.keys(result);
                if (keys.length > 0 && Array.isArray(result[keys[0]])) return result[keys[0]];
            }
            return null;
        }

        // ── Initialize Indicator Dropdown ──
        function initIndicators() {
            const container = document.getElementById('indDropdown');
            container.innerHTML = '';
            INDICATOR_DEFS.forEach(def => {
                const wrapper = document.createElement('div');
                wrapper.className = 'ind-option';

                const cb = document.createElement('input');
                cb.type = 'checkbox';
                cb.value = def.name;
                cb.className = 'ind-cb';
                cb.dataset.name = def.name;

                const label = document.createElement('span');
                label.textContent = def.label;
                label.style.flex = '1';
                label.style.fontSize = '12px';

                wrapper.appendChild(cb);
                wrapper.appendChild(label);

                // Params display (small inline)
                if (def.params.length > 0) {
                    const paramsSpan = document.createElement('span');
                    paramsSpan.style.fontSize = '9px';
                    paramsSpan.style.color = 'var(--text-muted)';
                    paramsSpan.style.display = 'flex';
                    paramsSpan.style.gap = '4px';
                    paramsSpan.style.flexWrap = 'wrap';

                    def.params.forEach(p => {
                        const input = document.createElement('input');
                        input.type = 'number';
                        input.value = p.def;
                        input.min = p.min;
                        input.max = p.max;
                        if (p.step) input.step = p.step;
                        input.dataset.paramKey = p.key;
                        input.style.width = '36px';
                        input.style.background = 'var(--bg-base)';
                        input.style.border = '1px solid var(--border)';
                        input.style.borderRadius = '3px';
                        input.style.color = 'var(--text-main)';
                        input.style.padding = '1px 3px';
                        input.style.fontSize = '10px';
                        input.style.outline = 'none';
                        input.title = `${p.label} (${p.key})`;

                        // Re-compute indicator when params change
                        input.addEventListener('change', () => {
                            if (cb.checked) toggleIndicator(def.name, true);
                        });

                        paramsSpan.appendChild(input);
                    });
                    wrapper.appendChild(paramsSpan);
                }

                cb.addEventListener('change', () => {
                    toggleIndicator(def.name, cb.checked);
                });

                container.appendChild(wrapper);
            });
        }

        // Set pane stretch factors for the 3-pane layout:
        //   Pane 0 (candles+overlays): ~60%  (stretch 3)
        //   Pane 1 (volume):           ~15%  (stretch 0.75)
        //   Pane 2 (oscillators):      ~25%  (stretch 1.25)
        function setOscPaneLayout() {
            const panes = chart.panes();
            if (panes.length > 2) {
                // 3 panes: candles + volume + oscillators
                panes[0].setStretchFactor(4);
                panes[1].setStretchFactor(1);
                panes[2].setStretchFactor(1.67);
            } else if (panes.length > 1) {
                // 2 panes: candles + volume (no oscillators active)
                panes[0].setStretchFactor(4);
                panes[1].setStretchFactor(1);
            }
        }

        // ── Toggle indicator on/off via local computation ──
        // NOTE: All indicator computation is synchronous (computeSMA, computeRSI, ..., no awaits).
        // If any indicator computation is ever moved server-side, these callers will need a
        // request-token / AbortController pattern to prevent stale results from overwriting newer ones.
        function toggleIndicator(name, enabled, force) {
            const getCb = () => document.querySelector(`.ind-cb[value="${name}"]`);
            const getWrapper = () => document.querySelector(`.ind-cb[value="${name}"]`)?.closest('.ind-option');

            if (enabled) {
                const checked = document.querySelectorAll('.ind-cb:checked').length;
                if (checked > 3 && !force) {
                    const cb = getCb();
                    if (cb) cb.checked = false;
                    alert("Maximum 3 indicators allowed to prevent clutter.");
                    return;
                }
                document.getElementById('activeIndCount').innerText = checked;

                const wrapper = getWrapper();
                const paramInputs = wrapper ? wrapper.querySelectorAll('input[data-param-key]') : [];
                const def = INDICATOR_DEFS.find(d => d.name === name);
                const params = {};
                paramInputs.forEach(inp => {
                    let val = parseFloat(inp.value);
                    if (isNaN(val)) {
                        params[inp.dataset.paramKey] = (def ? (def.params.find(p => p.key === inp.dataset.paramKey)?.def ?? 0) : 0);
                    } else {
                        const pDef = def && def.params.find(p => p.key === inp.dataset.paramKey);
                        if (pDef) {
                            if (pDef.min != null) val = Math.max(val, Number(pDef.min));
                            if (pDef.max != null) val = Math.min(val, Number(pDef.max));
                        }
                        params[inp.dataset.paramKey] = val;
                    }
                });

                if (wrapper) {
                    wrapper.style.opacity = '0.5';
                    const oldErr = wrapper.querySelector('.ind-error');
                    if (oldErr) oldErr.remove();
                }
            
                    // Compute locally
                    const result = computeIndicator(name, params);
                    if (!result) {
                        if (wrapper) wrapper.style.opacity = '1';
                        const cb = getCb();
                        if (cb) cb.checked = false;
                        document.getElementById('activeIndCount').innerText = document.querySelectorAll('.ind-cb:checked').length;
                        if (wrapper && !wrapper.querySelector('.ind-error')) {
                            const eb = document.createElement('span');
                            eb.className = 'ind-error';
                            eb.textContent = '∅';
                            eb.title = `No data for ${name}`;
                            eb.style.cssText = 'color:var(--text-muted);font-size:11px;margin-left:4px;';
                            wrapper.appendChild(eb);
                        }
                        return;
                    }

                if (wrapper) wrapper.style.opacity = '1';

                const seriesKey = name + '-' + JSON.stringify(params);

                // Remove any existing series for this indicator name (regardless of prior params)
                // so re-enabling or editing a parameter replaces rather than stacks duplicate series.
                const staleKeys = [];
                activeIndicators.forEach((val, key) => {
                    if (key.startsWith(name + '-')) staleKeys.push(key);
                });
                for (const key of staleKeys) {
                    const val = activeIndicators.get(key);
                    if (val.isMulti) val.series.forEach(s => chart.removeSeries(s));
                    else chart.removeSeries(val.series);
                    activeIndicators.delete(key);
                }

                const isMultiValue = ['macd', 'bb', 'stoch_rsi', 'kc'].includes(name);
                if (isMultiValue) {
                    const subKeys = name === 'macd' ? ['macd', 'signal', 'hist']
                        : name === 'bb' || name === 'kc' ? ['upper', 'mid', 'lower']
                        : ['k', 'd'];
                    const colors = name === 'macd' ? ['#3b82f6', '#f59e0b', '#ec4899']
                        : name === 'bb' ? ['rgba(236,72,153,0.5)', '#ec4899', 'rgba(236,72,153,0.5)']
                        : name === 'kc' ? ['rgba(251,146,60,0.5)', '#fb923c', 'rgba(251,146,60,0.5)']
                        : ['#e879f9', '#a78bfa'];
                    const isOsc = def && def.scale === 'oscillator';
                    const subSeries = [];
                    subKeys.forEach((sk, idx) => {
                        const isHist = name === 'macd' && sk === 'hist';
                        const opts = {
                            color: isHist ? '#ec4899' : colors[idx % colors.length],
                            lastValueVisible: false, priceLineVisible: false,
                        };
                        if (isHist) {
                            opts.base = 0;
                            opts.priceFormat = { type: 'price', minMove: 0.01 };
                        } else {
                            opts.lineWidth = sk === 'mid' || sk === 'macd' ? 2 : 1;
                        }
                        if (isOsc) opts.priceScaleId = 'osc-' + name;
                        const seriesCtor = isHist ? LightweightCharts.HistogramSeries : LightweightCharts.LineSeries;
                        const s = chart.addSeries(seriesCtor, opts, isOsc ? 2 : undefined);
                        subSeries.push(s);
                        const data = (result[sk] || []).filter(p => p.value != null);
                        if (data.length > 0) s.setData(data);
                    });
                    if (isOsc) setOscPaneLayout();
                    activeIndicators.set(seriesKey, { series: subSeries, isMulti: true });
                } else {
                    const opts = {
                        color: def ? def.color : '#94a3b8',
                        lineWidth: 1, lastValueVisible: false, priceLineVisible: false,
                    };
                    if (def && def.scale === 'oscillator') opts.priceScaleId = 'osc-' + name;
                    const series = chart.addSeries(LightweightCharts.LineSeries, opts, (def && def.scale === 'oscillator') ? 2 : undefined);
                    const data = result.filter(p => p.value != null);
                    if (data.length > 0) series.setData(data);
                    if (def && def.scale === 'oscillator') setOscPaneLayout();
                    activeIndicators.set(seriesKey, { series, isMulti: false });
                }
            } else {
                activeIndicators.forEach((val, key) => {
                    if (key.startsWith(name + '-')) { // Changed from key.startswith(name) to avoid prefix collisions
                        if (val.isMulti) val.series.forEach(s => chart.removeSeries(s));
                        else chart.removeSeries(val.series);
                        activeIndicators.delete(key);
                    }
                });
                
                // Check if any oscillator indicators remain active after disabling 'name'
                const remainingOscillators = Array.from(activeIndicators.keys()).some(k => {
                    const oscName = k.split('-')[0];
                    const def = INDICATOR_DEFS.find(d => d.name === oscName);
                    return def && def.scale === 'oscillator';
                });
                if (!remainingOscillators) {
                    // Remove the oscillator pane (pane 2) when empty
                    const panes = chart.panes();
                    if (panes.length > 2) {
                        chart.removePane(2);
                    }
                }
                const checked = document.querySelectorAll('.ind-cb:checked').length;
                document.getElementById('activeIndCount').innerText = checked;
            }
        }

        // Initialize Lightweight Chart
        function initChart() {
            const container = document.getElementById('tvchart');
            chart = LightweightCharts.createChart(container, {
                layout: { textColor: '#D1D4DC', background: { type: 'solid', color: '#131722' } },
                grid: { vertLines: { color: '#2A2E39' }, horzLines: { color: '#2A2E39' } },
                crosshair: { mode: LightweightCharts.CrosshairMode.Normal },
                rightPriceScale: { borderColor: '#2A2E39' },
                timeScale: { borderColor: '#2A2E39', timeVisible: true }
            });

            // FIX: v5 replaced addCandlestickSeries()/addHistogramSeries()/
            // addLineSeries() with a single addSeries(SeriesType, options)
            // call. The series type constructors (CandlestickSeries,
            // HistogramSeries, LineSeries) live on the global
            // LightweightCharts namespace in the standalone build.
            candleSeries = chart.addSeries(LightweightCharts.CandlestickSeries, {
                upColor: '#089981', downColor: '#F23645', borderVisible: false,
                wickUpColor: '#089981', wickDownColor: '#F23645'
            });

            // v5: markers moved to a separate primitive
            candleMarkers = LightweightCharts.createSeriesMarkers(candleSeries, []);

            volumeSeries = chart.addSeries(LightweightCharts.HistogramSeries, {
                color: '#26a69a', priceFormat: { type: 'volume' },
            }, 1); // Pane 1: dedicated volume pane below candles
            setOscPaneLayout(); // Initial 2-pane layout (candles + volume)

            // Volume show/hide toggle — collapse/expand the volume pane
            document.getElementById('volumeToggle').addEventListener('change', (e) => {
                const show = e.target.checked;
                volumeSeries.applyOptions({ visible: show });
                const panes = chart.panes();
                // Pane 1 is always the volume pane
                if (panes.length > 1) {
                    panes[1].setStretchFactor(show ? 0.75 : 0);
                }
                chart.applyOptions({});
            });
            
            // Handle window resize
            window.addEventListener('resize', () => { chart.applyOptions({ width: container.clientWidth, height: container.clientHeight }); });
        }

        // Fetch & Render Pairs Dropdown
        let watchlistData = [];

        async function loadWatchlist() {
            const { data } = await supabaseClient.from("crypto_data").select("*");
            if (!data) return;
            watchlistData = data;

            // Determine correct initial symbol: if currentSymbol is still default, set to first real symbol
            if (!currentSymbol || currentSymbol === "") {
                currentSymbol = data[0]?.symbol || "";
            }
            // If currentSymbol doesn't match any real symbol, pick first available
            if (!watchlistData.find(x => x.symbol === currentSymbol) && watchlistData.length > 0) {
                currentSymbol = watchlistData[0].symbol;
            }

            const select = document.getElementById('pairSelect');
            select.innerHTML = watchlistData.map(c =>
                `<option value="${c.symbol}" ${c.symbol === currentSymbol ? 'selected' : ''}>${c.symbol}</option>`
            ).join("");

            // Now that currentSymbol is set correctly, trigger data loading and research
            updateSelectedPairInfo();
            loadChartData().catch(e => console.warn('loadChartData error:', e));
            loadResearch().catch(e => console.warn('loadResearch error:', e));
        }

        function updateSelectedPairInfo() {
            const c = watchlistData.find(x => x.symbol === currentSymbol);
            if (!c) return;
            const price = (typeof c.current_price === 'number' && !isNaN(c.current_price)) ? c.current_price : null;
            const prevClose = (typeof c.previous_close === 'number' && !isNaN(c.previous_close)) ? c.previous_close : null;
            const pct = (price !== null && prevClose !== null && prevClose !== 0)
                ? Number((((price - prevClose) / prevClose) * 100).toFixed(2))
                : 0;
            const cls = pct >= 0 ? "up" : "down";
            document.getElementById('selectedSym').innerText = c.symbol;
            document.getElementById('headerSymbol').innerText = c.symbol;
            document.getElementById('selectedPrice').innerText = price !== null
                ? `$${price.toLocaleString(undefined, {minimumFractionDigits: 2})}`
                : '–';
            const changeEl = document.getElementById('selectedChange');
            changeEl.innerText = `${pct >= 0 ? '+' : ''}${pct}%`;
            changeEl.className = `w-change ${cls}`;
            // Also update #headerChange
            document.getElementById('headerChange').innerText = `${pct >= 0 ? '+' : ''}${pct}%`;
            document.getElementById('headerChange').className = cls;
            updateTradePrice();
        }

        document.getElementById('pairSelect').addEventListener('change', (e) => {
            selectSymbol(e.target.value);
        });

        function selectSymbol(sym) {
            currentSymbol = sym;
            updateSelectedPairInfo();
            loadChartData().catch(e => console.warn('loadChartData error:', e));
            loadResearch().catch(e => console.warn('loadResearch error:', e));
        }

        // Indicator Math Functions
        // ── Signal Engine ──

        // HTML-escape a string for safe innerHTML interpolation (matches research.html helper)

        const SIGNAL_OPERATORS = [
            { value: 'gt', label: '>' },
            { value: 'lt', label: '<' },
            { value: 'cross_above', label: 'Cross ↑' },
            { value: 'cross_below', label: 'Cross ↓' },
        ];

        // Sensible default operator/value per indicator scale (avoids threshold mismatch on switch/add)
        const INDICATOR_DEFAULTS = {
            rsi:       { operator: 'lt', value: 30 },
            stoch_rsi: { operator: 'lt', value: 30 },
            adx:       { operator: 'gt', value: 25 },
            vol_ratio: { operator: 'gt', value: 1.5 },
            sma:       { operator: 'gt', value: null }, // computed dynamically from last SMA value
            ema:       { operator: 'gt', value: null },
            bb:        { operator: 'gt', value: null },
            vwap:      { operator: 'gt', value: null },
            kc:        { operator: 'gt', value: null },
        };
        function getDefaultCond(name, indicatorData) {
            const d = INDICATOR_DEFAULTS[name];
            if (d && d.value !== null) return { operator: d.operator, value: d.value };
            if (d && d.value === null && indicatorData) {
                // Use the indicator's last computed value as the default threshold
                const arr = Array.isArray(indicatorData) ? indicatorData
                    : indicatorData?.mid || indicatorData?.macd || null;
                if (arr && arr.length > 0) {
                    const last = arr[arr.length - 1];
                    return { operator: d.operator, value: last.value };
                }
            }
            // Unbounded/price-scale indicators default to cross_above (edge-triggered, not raw comparison)
            return { operator: 'cross_above', value: 0 };
        }

        function addSignalCondition(indicator, params, operator, value, side) {
            const def = INDICATOR_DEFS.find(d => d.name === indicator);
            const multiSeriesKeys = { macd: 'macd', bb: 'mid', kc: 'mid', stoch_rsi: 'k' };
            const indicatorData = (indicator && params) ? computeIndicator(indicator, params) : null;
            const dflt = getDefaultCond(indicator || 'rsi', indicatorData);
            signalConditions.push({
                indicator: indicator || 'rsi',
                params: params || { period: 14 },
                operator: operator || dflt.operator,
                value: value != null ? value : dflt.value,
                side: side || 'long',
                value_key: (def && multiSeriesKeys[def.name]) || null,
            });
            renderSignalConditions();
        }

        function removeSignalCondition(idx) {
            signalConditions.splice(idx, 1);
            renderSignalConditions();
        }

        function renderSignalConditions() {
            const container = document.getElementById('signalConditions');
            if (!container) return;
            
            if (signalConditions.length === 0) {
                container.innerHTML = '<div style="font-size:11px;color:var(--text-muted);text-align:center;padding:8px;">No conditions. Add one below.</div>';
                return;
            }

            container.innerHTML = signalConditions.map((cond, idx) => {
                const def = INDICATOR_DEFS.find(d => d.name === cond.indicator);
                const multiKeys = cond.indicator === 'macd' ? ['macd', 'signal', 'hist']
                    : cond.indicator === 'bb' || cond.indicator === 'kc' ? ['upper', 'mid', 'lower']
                    : cond.indicator === 'stoch_rsi' ? ['k', 'd']
                    : null;
                return `
                    <div class="signal-cond">
                        <div class="signal-cond-row">
                            <select onchange="updateCond(${idx},'indicator',this.value)" style="flex:1;">
                                ${INDICATOR_DEFS.map(d => `<option value="${d.name}" ${d.name === cond.indicator ? 'selected' : ''}>${d.label}</option>`).join('')}
                            </select>
                            ${multiKeys ? `
                            <select onchange="updateCond(${idx},'value_key',this.value)" style="font-size:10px;width:auto;">
                                ${multiKeys.map(k => `<option value="${k}" ${(cond.value_key || multiKeys[0]) === k ? 'selected' : ''}>${k}</option>`).join('')}
                            </select>
                            ` : ''}
                            <span class="s-remove" onclick="removeSignalCondition(${idx})" title="Remove">×</span>
                        </div>
                        <div class="signal-cond-row">
                            ${def && def.params.length > 0 ? def.params.map(p => `
                                <label style="font-size:10px;color:var(--text-muted);">
                                    ${p.label}:
                                    <input type="number" value="${cond.params[p.key] != null ? cond.params[p.key] : p.def}" min="${p.min}" max="${p.max}" ${p.step ? 'step="'+p.step+'"' : ''}
                                        onchange="updateCondParam(${idx},'${p.key}',this.value)"
                                        style="width:36px;">
                                </label>
                            `).join('') : ''}
                        </div>
                        <div class="signal-cond-row">
                            <select onchange="updateCond(${idx},'operator',this.value)">
                                ${SIGNAL_OPERATORS.map(op => `<option value="${op.value}" ${op.value === cond.operator ? 'selected' : ''}>${op.label}</option>`).join('')}
                            </select>
                            <input type="number" value="${cond.value}" onchange="updateCond(${idx},'value',parseFloat(this.value))" style="width:56px;">
                            <select onchange="updateCond(${idx},'side',this.value)" style="color:${cond.side === 'long' ? 'var(--up)' : 'var(--down)'};">
                                <option value="long" ${cond.side === 'long' ? 'selected' : ''}>LONG</option>
                                <option value="short" ${cond.side === 'short' ? 'selected' : ''}>SHORT</option>
                            </select>
                        </div>
                    </div>
                `;
            }).join('');
        }

        window.updateCond = function(idx, field, value) {
            if (field === 'indicator') {
                const def = INDICATOR_DEFS.find(d => d.name === value);
                const params = {};
                if (def) def.params.forEach(p => { params[p.key] = p.def; });
                signalConditions[idx].indicator = value;
                signalConditions[idx].params = params;
                // Reset operator, value, and value_key to sensible defaults for the new indicator
                const multiKeys = value === 'macd' ? ['macd', 'signal', 'hist']
                    : value === 'bb' || value === 'kc' ? ['upper', 'mid', 'lower']
                    : value === 'stoch_rsi' ? ['k', 'd']
                    : null;
                signalConditions[idx].value_key = multiKeys ? multiKeys[0] : null;
                const indicatorData = computeIndicator(value, params);
                const dflt = getDefaultCond(value, indicatorData);
                signalConditions[idx].operator = dflt.operator;
                signalConditions[idx].value = dflt.value;
                renderSignalConditions();
            } else if (field === 'value') {
                signalConditions[idx].value = value;
            } else if (field === 'operator') {
                signalConditions[idx].operator = value;
            } else if (field === 'side') {
                signalConditions[idx].side = value;
            } else if (field === 'value_key') {
                signalConditions[idx].value_key = value;
            }
        };

        window.updateCondParam = function(idx, key, value) {
            const cond = signalConditions[idx];
            if (!cond) return;
            const def = INDICATOR_DEFS.find(d => d.name === cond.indicator);
            let parsed = parseFloat(value);
            if (isNaN(parsed)) {
                // Fallback to the param definition default
                const pDef = def && def.params.find(p => p.key === key);
                parsed = pDef ? pDef.def : 1;
            } else if (def) {
                const pDef = def.params.find(p => p.key === key);
                if (pDef) {
                    if (pDef.min != null) parsed = Math.max(parsed, Number(pDef.min));
                    if (pDef.max != null) parsed = Math.min(parsed, Number(pDef.max));
                }
            }
            signalConditions[idx].params[key] = parsed;
        };

        async function runSignal() {
            if (signalConditions.length === 0) return;

            const btn = document.getElementById('runSignalBtn');
            btn.disabled = true;
            btn.textContent = 'Computing…';

            const resultDiv = document.getElementById('signalResult');
            resultDiv.innerHTML = '';

            // Compute each condition's indicator, evaluate, and build time→bool maps
            const longMaps = [];
            const shortMaps = [];
            const logic = document.getElementById('signalLogic').value;

            for (const cond of signalConditions) {
                const result = computeIndicator(cond.indicator, cond.params);
                const series = extractSeries(result, cond.value_key);
                if (!series || series.length === 0) continue;

                // Evaluate operator for each bar in this indicator's series
                const boolArr = series.map((p, i) => {
                    switch (cond.operator) {
                        case 'gt': return p.value > cond.value;
                        case 'lt': return p.value < cond.value;
                        case 'cross_above':
                        case 'cross_below': return false; // handled below
                        default: return false;
                    }
                });

                // Handle cross conditions (requires at least 2 bars)
                if ((cond.operator === 'cross_above' || cond.operator === 'cross_below') && series.length > 1) {
                    for (let i = 1; i < series.length; i++) {
                        const prev = series[i - 1].value;
                        const curr = series[i].value;
                        boolArr[i] = cond.operator === 'cross_above'
                            ? prev <= cond.value && curr > cond.value
                            : prev >= cond.value && curr < cond.value;
                    }
                }

                // Build time→bool map for this condition
                const boolMap = new Map();
                for (let i = 0; i < series.length; i++) {
                    boolMap.set(series[i].time, boolArr[i]);
                }

                if (cond.side === 'long') longMaps.push(boolMap);
                else shortMaps.push(boolMap);
            }

            // Combine using all times from historicalData (aligned by time, not index)
            const allTimes = historicalData.map(d => d.time);

            let signals = allTimes.map(time => {
                let long = false, short = false;

                const longVals = longMaps.map(m => m.get(time) === true);
                const shortVals = shortMaps.map(m => m.get(time) === true);

                if (logic === 'all') {
                    long = longMaps.length > 0 && longVals.every(v => v === true);
                    short = shortMaps.length > 0 && shortVals.every(v => v === true);
                } else {
                    long = longVals.some(v => v === true);
                    short = shortVals.some(v => v === true);
                }

                return { time, signal: long ? 1 : short ? -1 : 0 };
            }).filter(s => s.signal !== 0);

            // Collapse consecutive same-direction signals (same behavior as STRATEGY_SIGNAL_FNS)
            signals = enforceAlternating(signals);

            btn.disabled = false;
            btn.textContent = 'Run Signal';

            if (signals.length === 0) {
                resultDiv.innerHTML = '<div class="signal-result" style="color:var(--text-muted)">No signals generated.</div>';
                return;
            }

            const buys = signals.filter(s => s.signal === 1).length;
            const sells = signals.filter(s => s.signal === -1).length;
            const last = signals[signals.length - 1].signal;
            const lastLabel = last === 1 ? 'BUY' : 'SELL';

            resultDiv.innerHTML = `
                <div class="s-summary">
                    <span class="s-buy">Buy: ${buys}</span>
                    <span class="s-sell">Sell: ${sells}</span>
                </div>
                <div style="margin-top:4px;font-size:10px;">Last signal: <strong>${lastLabel}</strong></div>
                <button onclick="clearSignal()" style="margin-top:4px;background:transparent;border:1px solid var(--border);color:var(--text-muted);border-radius:3px;padding:2px 6px;cursor:pointer;font-size:10px;">Clear</button>
            `;

            // Render signal markers on chart
            signalChartMarkers = signals.map(s => {
                return s.signal === 1
                    ? { time: s.time, position: 'belowBar', shape: 'arrowUp', color: '#089981', text: 'B' }
                    : { time: s.time, position: 'aboveBar', shape: 'arrowDown', color: '#F23645', text: 'S' };
            });
            if (candleMarkers) candleMarkers.setMarkers(signalChartMarkers);
        }

        function clearSignal() {
            signalChartMarkers = [];
            if (candleMarkers) candleMarkers.setMarkers([]);
            document.getElementById('signalResult').innerHTML = '';
            // Also clear strategy overlay
            document.querySelectorAll('.strat-item.active').forEach(el => el.classList.remove('active'));
            // Hide bottom trades panel
            const chartBottom = document.getElementById('chartBottom');
            if (chartBottom) chartBottom.classList.remove('visible');
        }

        // ── Signal Helpers ──
        // Works for both unix-second numbers (intraday) and 'YYYY-MM-DD' strings (daily)
        function compareTime(a, b) {
            if (typeof a === 'number' && typeof b === 'number') return a - b;
            return a < b ? -1 : a > b ? 1 : 0;
        }

        // Drops consecutive same-direction signals so BUY/SELL always alternate.
        function enforceAlternating(signals) {
            const sorted = signals.slice().sort((a, b) => compareTime(a.time, b.time));
            const out = [];
            let lastSignal = 0;
            for (const s of sorted) {
                if (s.signal !== lastSignal) {
                    out.push(s);
                    lastSignal = s.signal;
                }
            }
            return out;
        }

        // ── Strategy Results Loader ──
        // Maps research strategy types to JS signal functions compatible with our indicator engine.
        // Each returns an array of {time, signal: 1|-1} signal points.
        const STRATEGY_SIGNAL_FNS = {
            rsi_reversion: (data, p) => {
                const period = p.period || 14;
                const oversold = p.oversold || 30;
                const overbought = p.overbought || 70;
                const rsi = computeRSI(data, period);
                const sig = [];
                for (let i = 1; i < rsi.length; i++) {
                    const prev = rsi[i-1].value, cur = rsi[i].value;
                    if (prev >= oversold && cur < oversold) sig.push({time: rsi[i].time, signal: 1});
                    if (prev <= overbought && cur > overbought) sig.push({time: rsi[i].time, signal: -1});
                }
                return enforceAlternating(sig);
            },
            macd_crossover: (data, p) => {
                const m = computeMACD(data, p.fast || 12, p.slow || 26, p.signal || 9);
                // signal array has leading warm-up nulls filtered out, so it's shorter than macd.
                // Align by time instead of index.
                const sigByTime = new Map(m.signal.map(pt => [pt.time, pt.value]));
                const sig = [];
                for (let i = 0; i < m.macd.length; i++) {
                    const curSig = sigByTime.get(m.macd[i].time);
                    if (curSig === undefined) continue; // signal not yet computed for this bar
                    if (i === 0) continue; // need a previous bar to detect cross
                    const prevSig = sigByTime.get(m.macd[i-1].time);
                    if (prevSig === undefined) continue;
                    if (m.macd[i-1].value <= prevSig && m.macd[i].value > curSig)
                        sig.push({time: m.macd[i].time, signal: 1});
                    if (m.macd[i-1].value >= prevSig && m.macd[i].value < curSig)
                        sig.push({time: m.macd[i].time, signal: -1});
                }
                return enforceAlternating(sig);
            },
            bb_reversion: (data, p) => {
                const bb = computeBB(data, p.period || 20, p.std || 2.0);
                const lowerByTime = new Map(bb.lower.map(pt => [pt.time, pt.value]));
                const upperByTime = new Map(bb.upper.map(pt => [pt.time, pt.value]));
                const sig = [];
                for (let i = 1; i < data.length; i++) {
                    const lower = lowerByTime.get(data[i].time), lowerPrev = lowerByTime.get(data[i-1].time);
                    const upper = upperByTime.get(data[i].time), upperPrev = upperByTime.get(data[i-1].time);
                    if (lower !== undefined && lowerPrev !== undefined && data[i-1].close >= lowerPrev && data[i].close < lower)
                        sig.push({time: data[i].time, signal: 1});
                    if (upper !== undefined && upperPrev !== undefined && data[i-1].close <= upperPrev && data[i].close > upper)
                        sig.push({time: data[i].time, signal: -1});
                }
                return enforceAlternating(sig);
            },
            ema_crossover: (data, p) => {
                const fast = computeEMA(data, p.fast || 12);
                const slow = computeEMA(data, p.slow || 26);
                const fastByTime = new Map(fast.map(pt => [pt.time, pt.value]));
                const slowByTime = new Map(slow.map(pt => [pt.time, pt.value]));
                const sig = [];
                for (let i = 1; i < data.length; i++) {
                    const f = fastByTime.get(data[i].time);
                    const s = slowByTime.get(data[i].time);
                    const f_prev = fastByTime.get(data[i-1].time);
                    const s_prev = slowByTime.get(data[i-1].time);
                    if (f !== undefined && s !== undefined && f_prev !== undefined && s_prev !== undefined) {
                        if (f_prev <= s_prev && f > s) sig.push({time: data[i].time, signal: 1});
                        if (f_prev >= s_prev && f < s) sig.push({time: data[i].time, signal: -1});
                    }
                }
                return enforceAlternating(sig);
            },
            stoch_rsi: (data, p) => {
                const oversold = p.oversold || 20;
                const overbought = p.overbought || 80;
                const sd = computeStochRSI(data, p.period || 14, p.smooth_k || 3, p.smooth_d || 3);
                const k = sd.k || sd;
                const d = sd.d || [];
                const dByTime = new Map(d.map(pt => [pt.time, pt.value]));
                const sig = [];
                for (let i = 1; i < k.length; i++) {
                    const dCur = dByTime.get(k[i].time);
                    const dPrev = dByTime.get(k[i-1].time);
                    if (dCur === undefined || dPrev === undefined) continue;
                    if (k[i].value < oversold && k[i-1].value <= dPrev && k[i].value > dCur)
                        sig.push({time: k[i].time, signal: 1});
                    if (k[i].value > overbought && k[i-1].value >= dPrev && k[i].value < dCur)
                        sig.push({time: k[i].time, signal: -1});
                }
                return enforceAlternating(sig);
            },
            kc_breakout: (data, p) => {
                const kc = computeKC(data, p.period || 20, p.mult || 2.0);
                const upperByTime = new Map(kc.upper.map(pt => [pt.time, pt.value]));
                const lowerByTime = new Map(kc.lower.map(pt => [pt.time, pt.value]));
                const sig = [];
                for (let i = 1; i < data.length; i++) {
                    const upper = upperByTime.get(data[i].time), upperPrev = upperByTime.get(data[i-1].time);
                    const lower = lowerByTime.get(data[i].time), lowerPrev = lowerByTime.get(data[i-1].time);
                    if (upper !== undefined && upperPrev !== undefined && data[i-1].close <= upperPrev && data[i].close > upper)
                        sig.push({time: data[i].time, signal: 1});
                    if (lower !== undefined && lowerPrev !== undefined && data[i-1].close >= lowerPrev && data[i].close < lower)
                        sig.push({time: data[i].time, signal: -1});
                }
                return enforceAlternating(sig);
            },
            rsi_adx_combo: (data, p) => {
                const rsi = computeRSI(data, p.rsi_period || 14);
                const adx = computeADX(data, p.adx_period || 14);
                const ema12 = computeEMA(data, 12);
                const ema26 = computeEMA(data, 26);
                const threshold = p.adx_threshold || 25;
                const oversold = p.rsi_oversold || 25;
                const overbought = p.rsi_overbought || 75;
                const rsiByTime = new Map(rsi.map(pt => [pt.time, pt.value]));
                const adxByTime = new Map(adx.map(pt => [pt.time, pt.value]));
                const ema12ByTime = new Map(ema12.map(pt => [pt.time, pt.value]));
                const ema26ByTime = new Map(ema26.map(pt => [pt.time, pt.value]));
                const sig = [];
                for (let i = 1; i < data.length; i++) {
                    const r = rsiByTime.get(data[i].time), rPrev = rsiByTime.get(data[i-1].time);
                    const a = adxByTime.get(data[i].time);
                    const e12 = ema12ByTime.get(data[i].time), e26 = ema26ByTime.get(data[i].time);
                    const e12Prev = ema12ByTime.get(data[i-1].time), e26Prev = ema26ByTime.get(data[i-1].time);
                    if (r === undefined || rPrev === undefined || a === undefined ||
                        e12 === undefined || e26 === undefined || e12Prev === undefined || e26Prev === undefined) continue;

                    if (a < threshold) {
                        // Low-trend regime: mean reversion, signal on RSI crossing the threshold
                        if (rPrev >= oversold && r < oversold) sig.push({time: data[i].time, signal: 1});
                        if (rPrev <= overbought && r > overbought) sig.push({time: data[i].time, signal: -1});
                    } else {
                        // High-trend regime: trend following, signal on EMA crossover
                        if (e12Prev <= e26Prev && e12 > e26) sig.push({time: data[i].time, signal: 1});
                        if (e12Prev >= e26Prev && e12 < e26) sig.push({time: data[i].time, signal: -1});
                    }
                }
                return enforceAlternating(sig);
            },
            rsi_vol_combo: (data, p) => {
                const rsi = computeRSI(data, p.rsi_period || 14);
                const vr = computeVolRatio(data, p.vol_period || 20);
                const oversold = p.rsi_oversold || 25;
                const overbought = p.rsi_overbought || 75;
                const volMult = p.vol_mult || 1.5;
                const rsiByTime = new Map(rsi.map(pt => [pt.time, pt.value]));
                const vrByTime = new Map(vr.map(pt => [pt.time, pt.value]));
                const sig = [];
                for (let i = 1; i < data.length; i++) {
                    const r = rsiByTime.get(data[i].time), rPrev = rsiByTime.get(data[i-1].time);
                    const v = vrByTime.get(data[i].time);
                    if (r === undefined || rPrev === undefined || v === undefined) continue;
                    if (v > volMult && rPrev >= oversold && r < oversold) sig.push({time: data[i].time, signal: 1});
                    if (v > volMult && rPrev <= overbought && r > overbought) sig.push({time: data[i].time, signal: -1});
                }
                return enforceAlternating(sig);
            },
            breakout_hunter: (data, p) => {
                // Port of bot/strategies/breakout_hunter.py — detects true/false breakouts
                // with volume confirmation, ATR filtering, and wick-based fakeout detection.
                const atrPeriod = p.atr_period || 14;
                const minVolRatio = p.min_volume_ratio || 1.2;
                const minBreakoutStr = p.min_breakout_strength || 0.5;
                const trendPeriod = p.trend_period || 20;
                const falseBreakoutWick = p.false_breakout_wick_ratio || 0.6;
                const lookback = atrPeriod + trendPeriod + 2;
                if (data.length < Math.max(atrPeriod + trendPeriod + 5, 60)) return [];
                const sig = [];
                for (let i = lookback; i < data.length; i++) {
                    const cur = data[i];
                    // Historical window before current candle (no lookahead) — `lookback` elements
                    const histCandles = data.slice(i - lookback, i);
                    // Find previous resistance/support, avg volume
                    let prevHigh = -Infinity, prevLow = Infinity, volSum = 0;
                    for (const c of histCandles) {
                        if (c.high > prevHigh) prevHigh = c.high;
                        if (c.low < prevLow) prevLow = c.low;
                        volSum += c.value || 0;
                    }
                    const avgVol = volSum / histCandles.length;
                    // Simple ATR on historical window (SMA of TR, matching Python breakout_hunter)
                    let trSum = 0, trCount = 0;
                    for (let j = 1; j < histCandles.length; j++) {
                        const hl = histCandles[j].high - histCandles[j].low;
                        const hc = Math.abs(histCandles[j].high - histCandles[j-1].close);
                        const lc = Math.abs(histCandles[j].low - histCandles[j-1].close);
                        trSum += Math.max(hl, hc, lc);
                        trCount++;
                    }
                    const atr = trCount > 0 ? trSum / Math.min(trCount, atrPeriod) : 0.001;
                    const atrSafe = atr > 0 ? atr : 0.001;
                    // Current candle metrics
                    const curClose = cur.close, curOpen = cur.open;
                    const curHigh = cur.high, curLow = cur.low;
                    const curVol = cur.value || 0;
                    const upperWick = curHigh - Math.max(curOpen, curClose);
                    const lowerWick = Math.min(curOpen, curClose) - curLow;
                    const totalRange = Math.max(curHigh - curLow, 0.001);
                    // --- Breakout above resistance (potential LONG) ---
                    if (curClose > prevHigh) {
                        const upperWickRatio = upperWick / totalRange;
                        const volRatio = curVol / (avgVol > 0 ? avgVol : 1.0);
                        const atrBreakout = (curClose - prevHigh) / atrSafe;
                        const isBullTrap = upperWickRatio >= falseBreakoutWick && volRatio >= minVolRatio;
                        if (isBullTrap) {
                            // False breakout → counter-trend SHORT
                            sig.push({time: cur.time, signal: -1});
                        } else if (volRatio >= minVolRatio && atrBreakout >= minBreakoutStr) {
                            // True breakout → LONG
                            sig.push({time: cur.time, signal: 1});
                        }
                    }
                    // --- Breakout below support (potential SHORT) ---
                    if (curClose < prevLow) {
                        const lowerWickRatio = lowerWick / totalRange;
                        const volRatio = curVol / (avgVol > 0 ? avgVol : 1.0);
                        const atrBreakout = (prevLow - curClose) / atrSafe;
                        const isBearTrap = lowerWickRatio >= falseBreakoutWick && volRatio >= minVolRatio;
                        if (isBearTrap) {
                            // False breakout → counter-trend LONG
                            sig.push({time: cur.time, signal: 1});
                        } else if (volRatio >= minVolRatio && atrBreakout >= minBreakoutStr) {
                            // True breakout → SHORT
                            sig.push({time: cur.time, signal: -1});
                        }
                    }
                }
                return enforceAlternating(sig);
            },
        };

        async function loadStrategyResults() {
            const requestId = loadRequestId; // shared batch ID, incremented by loadChartData
            const feed = document.getElementById('stratFeed');
            const countEl = document.getElementById('stratCount');
            feed.innerHTML = '<div class="strat-loading">Loading...</div>';
            countEl.textContent = '';

            // Hoisted outside try so Quick Backtest section can access it after error fall-through
            let resultsData = [];

            try {
                // Get latest research run_id to scope results (avoid stale/duplicate rows)
                const runResp = await supabaseClient
                    .from('research_runs')
                    .select('run_id')
                    .order('run_timestamp', { ascending: false })
                    .limit(1)
                    .maybeSingle();
                if (requestId !== loadRequestId) return;
                const latestRunId = runResp.data?.run_id || null;
                if (runResp.error) console.warn('research_runs query:', runResp.error);

                // The `validation` column (V6 migration) may not exist in Supabase yet.
                // The Python script stores _validation inside params JSONB as a fallback.
                // Query without column filter and handle OOS/IS in JS via params._validation.
                // ALSO: the database has mixed symbol formats (BTC-USD vs BTC-USDT).
                // strategy_results always uses -USDT, so normalize the symbol.
                const stratSymbol = currentSymbol.replace(/-USD$/, '-USDT');

                function buildStratQuery(q) {
                    q = q.select('strategy_name, symbol, timeframe, params, sharpe_ratio, total_return_pct, max_drawdown_pct, win_rate, profit_factor, trade_count')
                        .eq('symbol', stratSymbol)
                        .eq('timeframe', currentTimeframe)
                        .gte('trade_count', 5);
                    if (latestRunId) q = q.eq('run_id', latestRunId);
                    return q.order('sharpe_ratio', { ascending: false }).limit(20);
                }

                let { data, error } = await buildStratQuery(supabaseClient.from('strategy_results'));
                if (requestId !== loadRequestId) return;

                if (error) throw error;
                resultsData = data || [];
                if (resultsData.length === 0) {
                    // No results for this timeframe — try the closest alternative
                    const altTimeframe = currentTimeframe === '1h' ? '4h' : currentTimeframe === '1d' ? '4h' : '1d';

                    function buildAltQuery(q) {
                        q = q.select('strategy_name, symbol, timeframe, params, sharpe_ratio, total_return_pct, max_drawdown_pct, win_rate, profit_factor, trade_count')
                            .eq('symbol', stratSymbol)
                            .eq('timeframe', altTimeframe)
                            .gte('trade_count', 5);
                        if (latestRunId) q = q.eq('run_id', latestRunId);
                        return q.order('sharpe_ratio', { ascending: false }).limit(20);
                    }

                    const { data: altData, error: altErr } = await buildAltQuery(supabaseClient.from('strategy_results'));
                    if (requestId !== loadRequestId) return;
                    if (altErr) throw altErr;
                    resultsData = altData || [];
                }
                if (resultsData.length === 0) {
                    feed.innerHTML = '<div class="strat-loading">No strategies found for this pair.</div>';
                    countEl.textContent = '';
                    return;
                }

                // Separate OOS and IS results
                const oos = resultsData.filter(r => r.params && r.params._validation === 'out_of_sample').slice(0, 10);
                const isOnly = resultsData.filter(r => !r.params || r.params._validation !== 'out_of_sample').slice(0, 5);
                let results = oos.length > 0 ? oos : isOnly.map(r => ({...r, _fallback: true}));
                if (oos.length > 0 && isOnly.length > 0) {
                    // Label remaining IS entries as fallback
                    results = [...oos, ...isOnly.map(r => ({...r, _fallback: true}))];
                }

                countEl.textContent = `${results.length} results`;
                feed.innerHTML = results.map((r, idx) => {
                    const paramStr = Object.entries(r.params || {}).filter(([k]) => k !== '_validation').map(([k,v]) => `${k}=${v}`).join(', ');
                    const shp = r.sharpe_ratio || 0;
                    const shpCls = shp >= 2 ? 'good' : shp >= 1 ? 'ok' : 'bad';
                    const label = r.params && r.params._validation === 'out_of_sample' ? '(OOS)' : r._fallback ? '(IS)' : '' ;
                    const encoded = encodeURIComponent(JSON.stringify(r.params));
                    return `
                        <div class="strat-item" data-idx="${idx}" data-strategy="${encodeURIComponent(r.strategy_name)}"
                             data-params="${encoded}">
                            <div class="strat-head">
                                <span class="strat-name">${escapeHtml(r.strategy_name.replace(/_/g, ' '))}</span>
                                <span class="strat-sharpe ${shpCls}">S ${shp.toFixed(1)}</span>
                            </div>
                            <div class="strat-metrics">
                                <span>Ret: ${(r.total_return_pct || 0).toFixed(1)}%</span>
                                <span>DD: ${(r.max_drawdown_pct || 0).toFixed(1)}%</span>
                                <span>WR: ${(r.win_rate || 0).toFixed(0)}%</span>
                                <span>PF: ${r.profit_factor != null ? r.profit_factor.toFixed(2) : '∞'}</span>
                                <span>Trades: ${r.trade_count || 0}</span>
                                ${label ? `<span class="strat-oos">${label}</span>` : ''}
                            </div>
                            <div class="strat-params">${paramStr}</div>
                        </div>
                `;
            }).join('');
            } catch(e) {
                console.error('Strategy results error:', e);
                // fall through — append quick backtest strategies even on error
            }

            // Always append "Quick Backtest" section with all available JS signal strategies.
            // This lets the user run any strategy even if it hasn't been researched yet.
            const DEFAULT_PARAMS = {
                rsi_reversion: { period: 14, oversold: 30, overbought: 70 },
                macd_crossover: { fast: 12, slow: 26, signal: 9 },
                bb_reversion: { period: 20, std: 2.0 },
                ema_crossover: { fast: 12, slow: 26 },
                stoch_rsi: { period: 14, smooth_k: 3, smooth_d: 3, oversold: 20, overbought: 80 },
                kc_breakout: { period: 20, mult: 2.0 },
                rsi_adx_combo: { rsi_period: 14, adx_period: 14, adx_threshold: 25, rsi_oversold: 25, rsi_overbought: 75 },
                rsi_vol_combo: { rsi_period: 14, vol_period: 20, rsi_oversold: 25, rsi_overbought: 75, vol_mult: 1.5 },
                breakout_hunter: { atr_period: 14, min_volume_ratio: 1.2, min_breakout_strength: 0.5, trend_period: 20, false_breakout_wick_ratio: 0.6 },
            };
            const quickEntries = Object.keys(STRATEGY_SIGNAL_FNS).filter(name => {
                // Show only strategies not already present in Supabase results
                return !resultsData.some(r => r.strategy_name === name);
            }).map(name => {
                const params = DEFAULT_PARAMS[name] || {};
                const encoded = encodeURIComponent(JSON.stringify(params));
                return `
                    <div class="strat-item" data-strategy="${encodeURIComponent(name)}"
                         data-params="${encoded}" style="opacity:0.85;">
                        <div class="strat-head">
                            <span class="strat-name">${escapeHtml(name.replace(/_/g, ' '))}</span>
                            <span style="font-size:9px;color:var(--text-muted);padding:1px 4px;border:1px solid var(--border);border-radius:3px;">quick</span>
                        </div>
                        <div class="strat-metrics">
                            <span style="color:var(--text-muted);font-size:9px;">Click to backtest with defaults</span>
                        </div>
                    </div>
                `;
            }).join('');
            if (quickEntries) {
                feed.innerHTML += `
                    <div style="font-size:10px;color:var(--text-muted);padding:6px 0 4px;border-top:1px solid var(--border);margin-top:4px;">Quick Backtest</div>
                    ${quickEntries}
                `;
            }
        }

        function applyStrategySignals(strategyName, params) {
            const fn = STRATEGY_SIGNAL_FNS[strategyName];
            if (!fn || !historicalData || historicalData.length === 0) return;

            clearSignal(); // Wipe previous strategy's markers/state before drawing new ones

            // Show bottom trades panel when a strategy is active
            const chartBottom = document.getElementById('chartBottom');
            if (chartBottom) chartBottom.classList.add('visible');

            // Highlight this strategy card
            document.querySelectorAll('.strat-item.active').forEach(el => el.classList.remove('active'));
            const cards = document.querySelectorAll('.strat-item');
            for (const card of cards) {
                if (decodeURIComponent(card.dataset.strategy) === strategyName &&
                    decodeURIComponent(card.dataset.params) === JSON.stringify(params)) {
                    card.classList.add('active');
                }
            }

            // Generate signals and enforce ascending time order
            const signals = fn(historicalData, params);
            if (signals.length === 0) {
                document.getElementById('signalResult').innerHTML = '<div style="color:var(--text-muted);font-size:11px;padding:4px;">No signals generated.</div>';
                return;
            }

            // Render markers on chart
            signalChartMarkers = signals.map(s => {
                return s.signal === 1
                    ? { time: s.time, position: 'belowBar', shape: 'arrowUp', color: '#089981', text: 'B' }
                    : { time: s.time, position: 'aboveBar', shape: 'arrowDown', color: '#F23645', text: 'S' };
            });
            if (candleMarkers) candleMarkers.setMarkers(signalChartMarkers);

            // Show summary
            const buys = signals.filter(s => s.signal === 1).length;
            const sells = signals.filter(s => s.signal === -1).length;
            const last = signals[signals.length - 1].signal;

            // Signal Trade Log — last 10 signals with timestamp, type, entry price
            const priceByTime = new Map(historicalData.map(d => [d.time, d.close]));
            function formatSignalTime(t) {
                return typeof t === 'number' ? new Date(t * 1000).toLocaleString() : t;
            }
            const logEntries = signals.slice(-10).reverse();
            const logRows = logEntries.map(s => {
                const price = priceByTime.get(s.time);
                const priceStr = price !== undefined ? `$${price.toLocaleString(undefined, {minimumFractionDigits: 2})}` : '–';
                const typeStr = s.signal === 1 ? 'BUY' : 'SELL';
                const typeColor = s.signal === 1 ? 'var(--up)' : 'var(--down)';
                return `<tr>
                    <td style="padding:2px 4px;">${formatSignalTime(s.time)}</td>
                    <td style="padding:2px 4px;color:${typeColor};font-weight:600;">${typeStr}</td>
                    <td style="padding:2px 4px;text-align:right;">${priceStr}</td>
                </tr>`;
            }).join('');

            document.getElementById('signalResult').innerHTML = `
                <div style="font-size:11px;padding:4px;">
                    <span style="color:var(--up)">B: ${buys}</span>
                    <span style="color:var(--down);margin-left:8px;">S: ${sells}</span>
                    <span style="color:var(--text-muted);margin-left:8px;font-size:10px;">
                        Last: <strong>${last === 1 ? 'BUY' : 'SELL'}</strong>
                    </span>
                    <button onclick="clearSignal()" style="float:right;background:transparent;border:1px solid var(--border);color:var(--text-muted);border-radius:3px;padding:0 5px;cursor:pointer;font-size:10px;">X</button>
                </div>
                <div style="margin-top:6px;border-top:1px solid var(--border);padding-top:4px;">
                    <div style="font-size:10px;color:var(--text-muted);margin-bottom:2px;">Signal Trade Log (last ${logEntries.length})</div>
                    <table style="width:100%;font-size:10px;border-collapse:collapse;">
                        <thead>
                            <tr style="color:var(--text-muted);">
                                <th style="text-align:left;padding:2px 4px;">Time</th>
                                <th style="text-align:left;padding:2px 4px;">Type</th>
                                <th style="text-align:right;padding:2px 4px;">Price</th>
                            </tr>
                        </thead>
                        <tbody>${logRows}</tbody>
                    </table>
                </div>
            `;
        }

        // ── Research Generation (pure JS — computes locally, writes to Supabase) ──
        async function generateResearch() {
            const feed = document.getElementById('researchFeed');
            feed.innerHTML = '<div style="text-align:center;color:var(--text-muted);font-size:13px;padding:20px;">Analyzing…</div>';

            const data = historicalData;
            if (!data || data.length < 30) {
                feed.innerHTML = '<div style="text-align:center;color:var(--down);font-size:13px;padding:20px;">Need at least 30 bars of data.</div>';
                return;
            }

            const close = data.map(d => d.close);
            const high = data.map(d => d.high);
            const low = data.map(d => d.low);

            // Compute indicators
            const sma20 = computeSMA(data, 20);
            const sma50 = computeSMA(data, 50);
            const ema12 = computeEMA(data, 12);
            const ema26 = computeEMA(data, 26);
            const rsi = computeRSI(data, 14);
            const adx = computeADX(data, 14);
            const atr = computeATR(data, 14);
            const obv = computeOBV(data);

            // Get last values
            const currentPrice = close[close.length - 1];
            const lastSMA20 = sma20.length > 0 ? sma20[sma20.length - 1].value : currentPrice;
            const lastSMA50 = sma50.length > 0 ? sma50[sma50.length - 1].value : null;
            const lastRSI = rsi.length > 0 ? rsi[rsi.length - 1].value : 50;
            const lastADX = adx.length > 0 ? adx[adx.length - 1].value : 0;
            const lastATR = atr.length > 0 ? atr[atr.length - 1].value : currentPrice * 0.02;
            const lastEMAFast = ema12.length > 0 ? ema12[ema12.length - 1].value : currentPrice;
            const lastEMASlow = ema26.length > 0 ? ema26[ema26.length - 1].value : currentPrice;

            // OBV trend
            const obvVals = (Array.isArray(obv) ? obv : [obv]).map(p => p.value).filter(v => v != null);
            const obvTrend = obvVals.length > 10 && obvVals[obvVals.length - 1] > obvVals[obvVals.length - 10] ? 'rising' : 'falling';

            // Compute signal engines
            const last50Close = close.slice(-50);
            const last50RSI = rsi.slice(-50).map(p => p.value);

            // RSI signals
            const rsiBuy = last50RSI.filter(v => v < 30).length;
            const rsiSell = last50RSI.filter(v => v > 70).length;

            // Trend signals
            const trendBullish = lastEMAFast > lastEMASlow && lastADX > 25;
            const trendBearish = lastEMAFast < lastEMASlow && lastADX > 25;

            // Determine sentiment
            let sentiment, confidence;
            const score = (rsiBuy - rsiSell) / Math.max(last50RSI.length, 1) * 10 + (trendBullish ? 3 : trendBearish ? -3 : 0);

            if (score > 2) {
                sentiment = 'bullish';
                confidence = Math.min(0.5 + Math.abs(score) * 0.05, 0.9);
            } else if (score < -2) {
                sentiment = 'bearish';
                confidence = Math.min(0.5 + Math.abs(score) * 0.05, 0.9);
            } else {
                sentiment = 'neutral';
                confidence = 0.3;
            }

            if (lastADX > 30) confidence = Math.min(confidence + 0.1, 0.95);
            else if (lastADX < 20) confidence = Math.max(confidence - 0.1, 0.1);

            // Entry/exit
            const entryPrice = currentPrice;
            const atrVal = lastATR || currentPrice * 0.02;
            let stopLoss, takeProfit, rationale;

            if (sentiment === 'bullish') {
                stopLoss = entryPrice - 1.5 * atrVal;
                takeProfit = entryPrice + 3 * atrVal;
                rationale = `Bullish bias with ${Math.round(confidence * 100)}% confidence. ` +
                    `RSI: ${lastRSI.toFixed(1)}, ADX: ${lastADX.toFixed(1)}. ` +
                    `Entry: $${entryPrice.toLocaleString(undefined, {minimumFractionDigits: 2})}, stop: $${stopLoss.toLocaleString(undefined, {minimumFractionDigits: 2})}, target: $${takeProfit.toLocaleString(undefined, {minimumFractionDigits: 2})}.`;
            } else if (sentiment === 'bearish') {
                stopLoss = entryPrice + 1.5 * atrVal;
                takeProfit = entryPrice - 3 * atrVal;
                rationale = `Bearish bias with ${Math.round(confidence * 100)}% confidence. ` +
                    `RSI: ${lastRSI.toFixed(1)}, ADX: ${lastADX.toFixed(1)}. ` +
                    `Short entry: $${entryPrice.toLocaleString(undefined, {minimumFractionDigits: 2})}, stop: $${stopLoss.toLocaleString(undefined, {minimumFractionDigits: 2})}, target: $${takeProfit.toLocaleString(undefined, {minimumFractionDigits: 2})}.`;
            } else {
                stopLoss = null;
                takeProfit = null;
                rationale = `Neutral — no clear directional bias. RSI: ${lastRSI.toFixed(1)}, ADX: ${lastADX.toFixed(1)}.`;
            }

            const trend = trendBullish ? 'bullish' : trendBearish ? 'bearish' : 'neutral';
            const atrPct = (lastATR / currentPrice) * 100;
            const volatility = atrPct > 3 ? 'high' : atrPct > 1.5 ? 'moderate' : 'low';

            const details = {
                trend, volatility, volume_trend: obvTrend,
                indicators: {
                    sma_20: Math.round(lastSMA20 * 100) / 100,
                    sma_50: lastSMA50 ? Math.round(lastSMA50 * 100) / 100 : null,
                    rsi: Math.round(lastRSI * 10) / 10,
                    adx: Math.round(lastADX * 10) / 10,
                    atr: Math.round(lastATR * 100) / 100,
                    atr_pct: Math.round(atrPct * 100) / 100,
                },
                signals: { last_50_bars: { buy: rsiBuy, sell: rsiSell } },
                entry: stopLoss ? { price: entryPrice, stop_loss: stopLoss, take_profit: takeProfit } : null,
            };

            const entry = {
                symbol: currentSymbol,
                report_type: 'ai_analysis',
                title: `${currentSymbol} Technical Analysis — ${trend.charAt(0).toUpperCase() + trend.slice(1)}`,
                summary: rationale,
                details: details,
                sentiment: sentiment,
                confidence: Math.round(confidence * 100) / 100,
                source: 'signal_engine',
                created_at: new Date().toISOString(),
            };

            // Show in feed immediately (prepend)
            const sentimentLower = escapeHtml((entry.sentiment || 'neutral').toLowerCase());
            const card = `
                <div class="research-card" style="border-color:var(--accent);">
                    <div class="r-head">
                        <span style="font-size:11px;color:var(--text-muted)">Just now</span>
                        <span class="r-badge ${sentimentLower}">${sentimentLower.toUpperCase()} ${Math.round(confidence * 100)}%</span>
                    </div>
                    <div class="r-title">${escapeHtml(entry.title)}</div>
                    <div class="r-desc">${escapeHtml(entry.summary)}</div>
                </div>
            `;
            feed.innerHTML = card + feed.innerHTML;

            // Try to write to Supabase (INSERT is allowed by V3 RLS policy for anon)
            try {
                await supabaseClient.from('crypto_research').insert(entry);
            } catch(e) {
                console.warn('Could not save research to Supabase:', e);
            }

            // Background refresh from DB (may replace our card if insert succeeded)
            loadResearch();
        }

        // ── Paper Trading ──
        let tradeCash = 10000;

        // Per-browser session identifier for scoping paper trades (no auth)
        function getSessionId() {
            let sid = localStorage.getItem('paperSessionId');
            if (!sid) {
                sid = 'sess_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
                localStorage.setItem('paperSessionId', sid);
            }
            return sid;
        }

        function persistCash() {
            try { localStorage.setItem('paperTradeCash', String(tradeCash)); } catch(e) { /* quota exceeded — ignore */ }
        }

        // Shared helper: record paper_orders row for closing/reducing an opposite-side position,
        // update/delete the position row, and apply realized P&L to tradeCash.
        // Returns the realized PnL amount (caller should accumulate if multiple closes occur).
        async function recordOppositeClose(symbol, opp, closeQty, price, sessionId, note) {
            const oppNormEntry = Number(opp.entry_price);
            const realizedPnl = opp.side === 'long'
                ? (price - oppNormEntry) * closeQty
                : (oppNormEntry - price) * closeQty;
            await supabaseClient.from('paper_orders').insert({
                symbol, side: opp.side, order_type: 'market',
                quantity: closeQty, price, status: 'filled',
                session_id: sessionId, pnl: realizedPnl, notes: note,
                opened_at: new Date().toISOString(), filled_at: new Date().toISOString()
            });
            tradeCash += realizedPnl;
            persistCash();
            return realizedPnl;
        }

        // ── KNOWN RACE CONDITION ──
        // The entire netting flow below (SELECT→compute→INSERT/UPDATE/DELETE) is non-atomic.
        // Concurrent orders on the same symbol can race and corrupt quantity/entry_price.
        // Full fix requires server-side transaction (RPC/stored proc). Tracked in TODO-race-condition.
        // The button-disable below mitigates the most common trigger (accidental double-click)
        // but does NOT eliminate races from two separate browser tabs/sessions acting on the
        // same session_id simultaneously — the full fix still requires a server-side atomic
        // RPC/stored procedure.
        async function placeOrder() {
            const tradeBtn = document.querySelector('.trade-btn');
            tradeBtn.disabled = true;

            try {
                const qty = parseFloat(document.getElementById('tradeQtyBottom').value);
                if (!qty || qty <= 0) { alert('Enter a valid quantity.'); return; }
                const side = document.getElementById('tradeSideBottom').value;
                const priceInfo = getCurrentPrice();
                if (!priceInfo) { alert('No price data available.'); return; }
                if (!priceInfo.live) { alert('Price data is stale — cannot place a live trade until fresh price data is available.'); return; }
                const price = priceInfo.value;

                const sessionId = getSessionId();
                const order = {
                    symbol: currentSymbol,
                    side,
                    order_type: 'market',
                    quantity: qty,
                    price,
                    status: 'filled',
                    session_id: sessionId,
                    filled_at: new Date().toISOString(),
                    opened_at: new Date().toISOString()
                };
                // Insert order
                const { error: orderErr } = await supabaseClient.from('paper_orders').insert(order);
                if (orderErr) { console.error('Order insert error:', orderErr); alert('Failed to place order.'); return; }

                // Upsert position: fetch existing, then merge
                const { data: existing } = await supabaseClient
                    .from('paper_positions')
                    .select('*')
                    .eq('symbol', currentSymbol)
                    .eq('side', side)
                    .eq('session_id', sessionId)
                    .order('opened_at', { ascending: false })
                    .limit(1);

                // Decide on netting logic for opposite-side orders (long vs short)
                const oppositeSide = side === 'long' ? 'short' : 'long';
                const { data: oppositePos } = await supabaseClient
                    .from('paper_positions')
                    .select('*')
                    .eq('symbol', currentSymbol)
                    .eq('side', oppositeSide)
                    .eq('session_id', sessionId)
                    .order('opened_at', { ascending: false })
                    .limit(1);
                
                if (existing && existing.length > 0) {
                    // Net against opposite-side first if both coexist (race condition / leftover data)
                    let netQty = qty;
                    let totalPnl = 0;
                    const EPS = 1e-8;
                    if (oppositePos && oppositePos.length > 0) {
                        const opp = oppositePos[0];
                        const oppNormQty = Number(opp.quantity);
                        const oppNormEntry = Number(opp.entry_price);
                        const netRemaining = oppNormQty - netQty;
                        const oppCloseSide = opp.side;

                        // Helper: record opposite-side close order and return realized P&L
                        async function recordOppClose(closeQty, note) {
                            const realizedPnl = oppCloseSide === 'long'
                                ? (price - oppNormEntry) * closeQty
                                : (oppNormEntry - price) * closeQty;
                            await supabaseClient.from('paper_orders').insert({
                                symbol: currentSymbol, side: oppCloseSide, order_type: 'market',
                                quantity: closeQty, price, status: 'filled',
                                session_id: sessionId, pnl: realizedPnl, notes: note,
                                opened_at: new Date().toISOString(), filled_at: new Date().toISOString()
                            });
                            return realizedPnl;
                        }

                        if (netRemaining > EPS) {
                            // Partial close of opposite side
                            const pnl = await recordOppClose(netQty, `Reduced opposite-side position (qty: ${netQty})`);
                            await supabaseClient.from('paper_positions')
                                .update({ quantity: netRemaining, entry_price: oppNormEntry, updated_at: new Date().toISOString() })
                                .eq('id', opp.id).eq('session_id', sessionId);
                            totalPnl += pnl;
                            netQty = 0;
                        } else if (Math.abs(netRemaining) <= EPS) {
                            // Full close of opposite side
                            const pnl = await recordOppClose(oppNormQty, 'Closed opposite-side position (full)');
                            await supabaseClient.from('paper_positions').delete().eq('id', opp.id).eq('session_id', sessionId);
                            totalPnl += pnl;
                            netQty = 0;
                        } else {
                            // Overflow: close all of opposite side, remainder becomes new position quantity
                            const pnl = await recordOppClose(oppNormQty, 'Closed opposite-side position (full)');
                            await supabaseClient.from('paper_positions').delete().eq('id', opp.id).eq('session_id', sessionId);
                            totalPnl += pnl;
                            netQty = -netRemaining; // leftover to add to same-side
                        }
                    }

                    if (netQty > 0) {
                        // Merge remainder into same-side position
                        const pos = existing[0];
                        const normQty = Number(pos.quantity);
                        const normEntry = Number(pos.entry_price);
                        const totalQty = normQty + netQty;
                        const avgPrice = ((normEntry * normQty) + (price * netQty)) / totalQty;
                        const { error: updErr } = await supabaseClient
                            .from('paper_positions')
                            .update({ quantity: totalQty, entry_price: avgPrice, updated_at: new Date().toISOString() })
                            .eq('id', pos.id).eq('session_id', sessionId);
                        if (updErr) console.error('Position update error:', updErr);
                    }
                    if (totalPnl !== 0) { tradeCash += totalPnl; persistCash(); }
                } else {
                    // No existing same-side position → check for opposite-side position and net
                    const EPS = 1e-8;
                    if (oppositePos && oppositePos.length > 0) {
                        const opp = oppositePos[0];
                        const oppNormQty = Number(opp.quantity);
                        const oppNormEntry = Number(opp.entry_price);
                        const remainingQty = oppNormQty - qty;
                        
                        if (remainingQty > EPS) {
                            // Partial close: reduce opposite side by qty
                            const { error: oppUpdErr } = await supabaseClient
                                .from('paper_positions')
                                .update({ quantity: remainingQty, entry_price: oppNormEntry, updated_at: new Date().toISOString() })
                                .eq('id', opp.id).eq('session_id', sessionId);
                            if (!oppUpdErr) {
                                await recordOppositeClose(currentSymbol, opp, qty, price, sessionId,
                                    `Reduced opposite-side position (qty: ${qty})`);
                            }
                        } else if (Math.abs(remainingQty) <= EPS) {
                            // Full close: opposite side is exactly covered
                            await recordOppositeClose(currentSymbol, opp, oppNormQty, price, sessionId,
                                'Closed opposite-side position (full)');
                            await supabaseClient.from('paper_positions').delete().eq('id', opp.id).eq('session_id', sessionId);
                        } else {
                            // Overflow: close all of opposite side, remainder opens on new side
                            await recordOppositeClose(currentSymbol, opp, oppNormQty, price, sessionId,
                                'Closed opposite-side position (full)');
                            await supabaseClient.from('paper_positions').delete().eq('id', opp.id).eq('session_id', sessionId);
                        }
                    }
                    
                    // Insert new position if the opposite side was fully consumed (or didn't exist)
                    const oppRemaining = oppositePos && oppositePos.length > 0 ? Number(oppositePos[0].quantity) - qty : -1;
                    if (!(oppositePos && oppositePos.length > 0 && oppRemaining >= -EPS)) {
                        const netQty = oppositePos && oppositePos.length > 0 ? qty - Number(oppositePos[0].quantity) : qty;
                        if (netQty > EPS) {
                            const { error: insErr } = await supabaseClient
                                .from('paper_positions')
                                .insert({
                                    symbol: currentSymbol, side,
                                    quantity: netQty, entry_price: price, current_price: price,
                                    unrealized_pnl: 0, session_id: sessionId,
                                    opened_at: new Date().toISOString(), updated_at: new Date().toISOString()
                                });
                            if (insErr) console.error('Position insert error:', insErr);
                        }
                    }
                }

                refreshTradingUI();
            } catch(e) {
                console.error('Place order error:', e);
                alert('Order failed. See console.');
            } finally {
                tradeBtn.disabled = false;
            }
        }

        async function closePosition(id) {
            const sessionId = getSessionId();
            // Disable the Close button for this position to prevent double-clicks
            const closeBtn = document.querySelector(`.close-btn[data-id="${CSS.escape(id)}"]`);
            if (closeBtn) closeBtn.disabled = true;
            try {
                const { data: pos, error: fetchErr } = await supabaseClient
                    .from('paper_positions')
                    .select('*')
                    .eq('id', id)
                    .eq('session_id', sessionId)
                    .limit(1);
                if (fetchErr || !pos || pos.length === 0) return;

                const p = pos[0];
                const pInfo = getCurrentPrice(p.symbol);
                if (pInfo && !pInfo.live) {
                    if (!confirm('Price data for ' + p.symbol + ' is stale. Close anyway using the last known price?')) {
                        return;
                    }
                }
                const entryPrice = Number(p.entry_price);
                const qty = Number(p.quantity);
                const closePrice = pInfo ? pInfo.value : Number(p.current_price || entryPrice);
                const realizedPnl = p.side === 'long'
                    ? (closePrice - entryPrice) * qty
                    : (entryPrice - closePrice) * qty;

                // Record closing order
                await supabaseClient.from('paper_orders').insert({
                    symbol: p.symbol,
                    side: p.side,
                    order_type: 'market',
                    quantity: qty,
                    price: closePrice,
                    status: 'filled',
                    session_id: sessionId,
                    pnl: realizedPnl,
                    notes: 'Closed position',
                    opened_at: new Date().toISOString(),
                    filled_at: new Date().toISOString()
                });

                // Delete position
                await supabaseClient.from('paper_positions').delete().eq('id', id).eq('session_id', sessionId);

                // Add realizedP&L to cash balance (reflect cumulative realized outcome)
                tradeCash += realizedPnl;
                persistCash();

                refreshTradingUI();
            } catch(e) {
                console.error('Close position error:', e);
            } finally {
                if (closeBtn) closeBtn.disabled = false;
            }
        }

        function getCurrentPrice(symbol) {
            if (!symbol) symbol = currentSymbol;
            // Check cache first (updated by loadChartData)
            if (symbolPriceCache[symbol] !== undefined) {
                return { value: symbolPriceCache[symbol], live: true };
            }
            
            // Fallback to watchlist for other symbols
            const w = watchlistData.find(x => x.symbol === symbol);
            if (w && (typeof w.current_price === 'number' && !isNaN(w.current_price))) {
                return { value: w.current_price, live: true };
            }
            
            // Fallback to historicalData for current symbol (backwards compatibility)
            // ONLY for the currently-charted symbol - prevents cross-symbol contamination
            if (historicalData.length === 0) {
                return null;
            }
            if (symbol !== currentSymbol) {
                return null;
            }
            return { value: historicalData[historicalData.length - 1].close, live: false };
        }

        async function loadPositions() {
            const sessionId = getSessionId();
            const { data } = await supabaseClient
                .from('paper_positions')
                .select('*')
                .eq('session_id', sessionId)
                .order('opened_at', { ascending: false });
            return data || [];
        }

        async function loadOrders() {
            const sessionId = getSessionId();
            const { data } = await supabaseClient
                .from('paper_orders')
                .select('*')
                .eq('session_id', sessionId)
                .order('opened_at', { ascending: false })
                .limit(10);
            return data || [];
        }

        function renderPositions(positions) {
            const list = document.getElementById('positionsListBottom');
            if (positions.length === 0) {
                list.innerHTML = '<div style="text-align:center;padding:8px;font-size:11px;color:var(--text-muted);">No open positions.</div>';
                return;
            }

            let totalUnrealized = 0;
            list.innerHTML = positions.map(p => {
                // Defensive number normalization (PostgreSQL may return strings)
                const normQty = Number(p.quantity);
                const normEntry = Number(p.entry_price);
                const pInfo = getCurrentPrice(p.symbol);
                const priceLive = pInfo && pInfo.live;
                const cur = pInfo ? pInfo.value : Number(p.current_price || p.entry_price);
                let pnlHtml, pnlValue;
                if (priceLive) {
                    pnlValue = p.side === 'long'
                        ? (cur - normEntry) * normQty
                        : (normEntry - cur) * normQty;
                    const pnlClass = pnlValue >= 0 ? 'positive' : 'negative';
                    const pnlStr = (pnlValue >= 0 ? '+' : '') + pnlValue.toFixed(2);
                    pnlHtml = `<div class="pos-pnl ${pnlClass}">$${pnlStr}</div>`;
                } else {
                    pnlValue = 0;
                    pnlHtml = `<div class="pos-pnl" style="color:var(--text-muted);">PnL: N/A</div>`;
                }
                totalUnrealized += pnlValue;
                return `
                    <div class="pos-item">
                        <div>
                            <strong>${escapeHtml(p.symbol)}</strong> ${escapeHtml(p.side)} ${normQty.toFixed(4)}
                            <div style="font-size:9px;color:var(--text-muted);">Entry: $${normEntry.toFixed(2)}</div>
                        </div>
                        <div style="text-align:right;">
                            ${pnlHtml}
                            <button class="close-btn" data-id="${escapeHtml(p.id)}" onclick="closePosition('${escapeHtml(p.id)}')">Close</button>
                        </div>
                    </div>
                `;
            }).join('');

            // Update equity
            const equity = tradeCash + totalUnrealized;
            document.getElementById('accountEquityBottom').innerText = `$${equity.toFixed(2)}`;
        }

        function renderOrders(orders) {
            const list = document.getElementById('ordersListBottom');
            if (orders.length === 0) {
                list.innerHTML = '<div style="text-align:center;padding:8px;font-size:10px;color:var(--text-muted);">No orders yet.</div>';
                return;
            }

            list.innerHTML = orders.map(o => `
                <div class="order-item">
                    <div>
                        <span class="o-side ${escapeHtml(o.side)}">${escapeHtml(o.side.toUpperCase())}</span>
                        ${escapeHtml(o.symbol)} × ${Number(o.quantity).toFixed(4)}
                    </div>
                    <div>
                        ${o.price ? '$' + Number(o.price).toFixed(2) : '–'}
                        <span class="o-status ${escapeHtml(o.status)}">${escapeHtml(o.status)}</span>
                    </div>
                </div>
            `).join('');
        }

        function updateTradePrice() {
            const pInfo = getCurrentPrice();
            document.getElementById('tradePriceLabelBottom').innerText = !pInfo
                ? 'Price: –'
                : pInfo.live
                    ? `Price: $${pInfo.value.toFixed(2)}`
                    : 'Price: N/A (stale)';
        }

        async function refreshTradingUI() {
            updateTradePrice();
            const [positions, orders] = await Promise.all([loadPositions(), loadOrders()]);
            // Prefetch prices for any position symbols not currently charted (avoids stale ~$0 P&L)
            await refreshPriceCacheForPositions(positions);
            renderPositions(positions);
            renderOrders(orders);
        }

        async function refreshPriceCacheForPositions(positions) {
            const uncached = [...new Set(positions.map(p => p.symbol).filter(s => symbolPriceCache[s] === undefined))];
            if (uncached.length === 0) return;
            // Batch-fetch latest prices from Supabase
            for (const sym of uncached) {
                try {
                    const { data } = await supabaseClient
                        .from('crypto_data')
                        .select('current_price')
                        .eq('symbol', sym)
                        .order('updated_at', { ascending: false })
                        .limit(1);
                    if (data && data.length > 0 && data[0].current_price != null) {
                        symbolPriceCache[sym] = Number(data[0].current_price);
                    } else {
                        // Fallback: use historical data's last close
                        const { data: hist } = await supabaseClient
                            .from('crypto_historical')
                            .select('close')
                            .eq('symbol', sym)
                            .order('datetime', { ascending: false })
                            .limit(1);
                        if (hist && hist.length > 0) {
                            symbolPriceCache[sym] = Number(hist[0].close);
                        }
                    }
                } catch(e) {
                    console.warn(`Could not fetch price for ${sym}:`, e);
                }
            }
        }

        async function initTrading() {
            // 1) Try localStorage cache first
            const saved = localStorage.getItem('paperTradeCash');
            if (saved !== null) {
                tradeCash = parseFloat(saved);
                refreshTradingUI();
                return;
            }
            // 2) Derive from realized P&L history: start with $10k seed + all closed P&L
            try {
                const { data: orders } = await supabaseClient
                    .from('paper_orders')
                    .select('pnl')
                    .eq('session_id', getSessionId())
                    .not('pnl', 'is', null);
                const totalPnl = orders ? orders.reduce((sum, o) => sum + Number(o.pnl || 0), 0) : 0;
                tradeCash = 10000 + totalPnl;
            } catch(e) {
                console.warn('Could not load orders for cash derivation, using default $10,000:', e);
                tradeCash = 10000;
            }
            persistCash();
            refreshTradingUI();
        }

        function toChartTime(datetime) {
            // Lightweight Charts v5 expects Unix timestamp in seconds for intraday, string 'YYYY-MM-DD' for daily+
            if (['1h', '4h'].includes(currentTimeframe)) {
                return Math.floor(new Date(datetime).getTime() / 1000);
            }
            return datetime.split('T')[0];
        }

        // Convert a trade time (ISO string, unix number, or YYYY-MM-DD) to chart-series-compatible marker time.
        // For daily: YYYY-MM-DD string. For intraday: unix seconds number.
        function toMarkerTime(val, isDaily) {
            if (val == null) return null;
            if (isDaily) {
                // Extract YYYY-MM-DD from whatever format
                if (typeof val === 'string') return val.split('T')[0];
                // val is a number (unix seconds) — convert via Date
                return new Date(val * 1000).toISOString().split('T')[0];
            }
            // Intraday: must be unix seconds number
            if (typeof val === 'number') return Math.floor(val);
            // String ISO → unix seconds
            return Math.floor(new Date(val).getTime() / 1000);
        }

        // Timeframe Selector
        document.getElementById('timeframeSelector').addEventListener('click', (e) => {
            if (e.target.tagName !== 'BUTTON') return;
            document.querySelectorAll('#timeframeSelector button').forEach(b => b.classList.remove('active'));
            e.target.classList.add('active');
            currentTimeframe = e.target.getAttribute('data-tf');
            loadChartData();
        });

        // Fetch & Render Chart Data
        async function loadChartData() {
            const requestId = ++loadRequestId;
            // Clear any leftover strategy/signal markers before loading new chart data
            clearSignal();

            const { data } = await supabaseClient
                .from("crypto_historical")
                .select("*").eq("symbol", currentSymbol).eq("timeframe", currentTimeframe)
                .order("datetime", { ascending: true });
            if (requestId !== loadRequestId) return;

            if (!data || data.length === 0) {
                historicalData = [];
                candleSeries.setData([]);
                volumeSeries.setData([]);
                document.getElementById('headerPrice').innerText = '—';
                return;
            }

            // Rebuild the chart-ready OHLCV array — this was missing/recently removed
            historicalData = data.map(d => ({
                time: toChartTime(d.datetime),
                open: Number(d.open), high: Number(d.high), low: Number(d.low), close: Number(d.close),
                value: Number(d.volume) || 0,
                color: Number(d.close) >= Number(d.open)
                    ? 'rgba(8, 153, 129, 0.4)'  // up
                    : 'rgba(242, 54, 69, 0.4)'   // down
            })).filter(d => !isNaN(d.open) && !isNaN(d.high) && !isNaN(d.low) && !isNaN(d.close));

            // Populate price cache with current symbol's latest close
            if (historicalData.length > 0) {
                const lastHist = historicalData[historicalData.length - 1];
                symbolPriceCache[currentSymbol] = lastHist.close;
            }

            if(historicalData.length > 0) {
                const latest = historicalData[historicalData.length - 1];
                document.getElementById('headerPrice').innerText = `$${latest.close.toLocaleString(undefined, {minimumFractionDigits: 2})}`;
            }

            candleSeries.setData(historicalData);
            volumeSeries.setData(historicalData.map(d => ({ time: d.time, value: d.value, color: d.color })));

            // Clear existing active indicator series
            activeIndicators.forEach((val, key) => {
                if (val.isMulti) {
                    val.series.forEach(s => chart.removeSeries(s));
                } else {
                    chart.removeSeries(val.series);
                }
            });
            activeIndicators.clear();

            // Re-render active indicators (client-side)
            const checkedNames = [];
            document.querySelectorAll('.ind-cb:checked').forEach(cb => { checkedNames.push(cb.value); });
            checkedNames.forEach(name => toggleIndicator(name, true, true));
            refreshTradingUI().catch(e => console.warn('refreshTradingUI error:', e));
            loadStrategyResults().catch(e => console.warn('loadStrategyResults error:', e));
        }

        // Fetch AI Research
        async function loadResearch() {
            const requestId = loadRequestId; // shared batch ID
            const feed = document.getElementById('researchFeed');
            const { data } = await supabaseClient.from("crypto_research").select("*").eq("symbol", currentSymbol).order("created_at", { ascending: false }).limit(5);
            if (requestId !== loadRequestId) return;
            
            if (!data || data.length === 0) {
                feed.innerHTML = `<div style="text-align:center; color: var(--text-muted); font-size: 13px;">No recent insights.</div>`;
                return;
            }

            feed.innerHTML = data.map(r => {
                const sentiment = escapeHtml((r.sentiment || 'neutral').toLowerCase());
                return `
                    <div class="research-card">
                        <div class="r-head">
                            <span style="font-size: 11px; color: var(--text-muted)">${new Date(r.created_at).toLocaleDateString()}</span>
                            <span class="r-badge ${sentiment}">${sentiment.toUpperCase()}</span>
                        </div>
                        <div class="r-title">${escapeHtml(r.title || 'Market Update')}</div>
                        <div class="r-desc">${escapeHtml(r.summary || '')}</div>
                    </div>
                `;
            }).join("");
        }

        // ── Backtest Results ──

        let backtestMarkers = [];

        window.loadBacktestFile = function(event) {
            const file = event.target.files[0];
            if (!file) return;
            const reader = new FileReader();
            reader.onload = function(e) {
                try {
                    const data = JSON.parse(e.target.result);
                    renderBacktestResults(data);
                } catch (err) {
                    document.getElementById('backtestSummary').textContent = 'Error: ' + err.message;
                    document.getElementById('backtestSummary').style.display = 'block';
                    document.getElementById('backtestMetrics').style.display = 'none';
                }
            };
            reader.readAsText(file);
            event.target.value = ''; // allow re-selecting same file
        };

        window.renderBacktestResults = function(data) {
            const m = data.metrics || {};
            const trades = data.trades || [];

            // Update summary
            document.getElementById('backtestSummary').style.display = 'none';
            document.getElementById('backtestMetrics').style.display = 'block';

            // Format helpers
            const pct = (v) => (v * 100).toFixed(2) + '%';
            const num = (v) => v != null && isFinite(v) ? v.toFixed(2) : '—';

            document.getElementById('btReturn').textContent = pct(m.total_return_pct);
            document.getElementById('btReturn').style.color = m.total_return_pct >= 0 ? 'var(--up)' : 'var(--down)';
            document.getElementById('btSharpe').textContent = num(m.sharpe_ratio);
            document.getElementById('btDrawdown').textContent = pct(m.max_drawdown_pct);
            document.getElementById('btWinRate').textContent = pct(m.win_rate);
            document.getElementById('btTrades').textContent = m.total_trades || 0;

            const pf = m.profit_factor;
            document.getElementById('btProfitFactor').textContent = pf === Infinity ? '∞' : num(pf);
            document.getElementById('btStrategy').textContent = data.strategy_id || '—';
            document.getElementById('btSymbol').textContent = data.symbol || '—';
            document.getElementById('btTimeframe').textContent = data.timeframe || '—';

            // Render trade markers on chart
            clearBacktestMarkers();
            if (trades.length && typeof candleMarkers !== 'undefined' && candleMarkers) {
                const markers = [];
                const isDaily = currentTimeframe === '1d';
                trades.forEach(t => {
                    // Convert entry/exit to chart time format matching the series
                    const entryTime = t.entry_time ? toMarkerTime(t.entry_time, isDaily) : null;
                    const exitTime = t.exit_time ? toMarkerTime(t.exit_time, isDaily) : null;

                    if (entryTime) {
                        markers.push({
                            time: entryTime,
                            position: t.side === 'long' ? 'belowBar' : 'aboveBar',
                            color: t.side === 'long' ? '#089981' : '#f23645',
                            shape: 'arrowUp',
                            text: t.side === 'long' ? 'BT LONG' : 'BT SHORT',
                        });
                    }
                    if (exitTime) {
                        const isProfit = t.pnl != null && t.pnl > 0;
                        markers.push({
                            time: exitTime,
                            position: 'aboveBar',
                            color: isProfit ? '#089981' : '#f23645',
                            shape: 'arrowDown',
                            text: isProfit ? 'TP' : 'SL',
                        });
                    }
                });
                backtestMarkers = markers;
                const existing = candleMarkers._markers || [];
                // Keep signal markers (B/S) alongside new backtest markers
                const signalOnly = existing.filter(m => {
                    const text = m.text || '';
                    return text === 'B' || text === 'S';
                });
                candleMarkers.setMarkers([...signalOnly, ...markers]);
            }
        };

        window.clearBacktestMarkers = function() {
            if (typeof candleMarkers !== 'undefined' && candleMarkers) {
                const existing = candleMarkers._markers || [];
                // Filter out backtest markers (remove any we added)
                const nonBt = existing.filter(m => {
                    const text = m.text || '';
                    // Remove BT entry markers, TP/SL, and PnL percentage markers (e.g. '+2.8%', '-1.5%')
                    return !text.startsWith('BT ') && text !== 'TP' && text !== 'SL' && !/^[+-]\d+\.\d+%$/.test(text);
                });
                candleMarkers.setMarkers(nonBt);
            }
            backtestMarkers = [];
        };

        // ── End Backtest Results ──

        // ── Detailed Trade List Toggles ──

        window.toggleTradeList = function() {
            const body = document.getElementById('btTradeBody');
            const toggle = document.getElementById('btTradeToggle');
            const isVisible = body && body.style.display !== 'none';
            if (body) body.style.display = isVisible ? 'none' : 'block';
            if (toggle) toggle.textContent = isVisible ? '▶' : '▼';
        };

        window.toggleTradeDetail = function(idx) {
            const row = document.getElementById('btTradeDetail' + idx);
            if (row) row.style.display = row.style.display === 'none' ? 'table-row' : 'none';
        };

        // ── Client-Side Backtest Simulation ──

         function runBacktestOnStrategy(strategyName, params) {
             const fn = STRATEGY_SIGNAL_FNS[strategyName];
             if (!fn || !historicalData || historicalData.length < 30) return;

             // Show the bottom trades panel when a strategy is active
             showBottomPanel();

            // Highlight active card
            document.querySelectorAll('.strat-item.active').forEach(el => el.classList.remove('active'));
            for (const card of document.querySelectorAll('.strat-item')) {
                if (decodeURIComponent(card.dataset.strategy) === strategyName &&
                    decodeURIComponent(card.dataset.params) === JSON.stringify(params)) {
                    card.classList.add('active');
                }
            }

            // Generate signals (alternating buy/sell guaranteed by enforceAlternating)
            const signals = fn(historicalData, params);
            if (signals.length < 2) {
                document.getElementById('signalResult').innerHTML = '<div class="signal-result" style="color:var(--text-muted)">Not enough signals for backtest.</div>';
                return;
            }

            // Build price lookup
            const priceByTime = new Map(historicalData.map(d => [d.time, d.close]));

            // Simulate trades from alternating signals (BUY=1 / SELL=-1).
            // BUY when flat → enter long.  BUY when short → close short + enter long.
            // SELL when flat → enter short.  SELL when long → close long + enter short.
            const trades = [];
            let openTrade = null; // { entry_time, entry_price, side: 'long'|'short' }

            for (let i = 0; i < signals.length; i++) {
                const sig = signals[i];
                const price = priceByTime.get(sig.time);
                if (price === undefined) continue;

                if (sig.signal === 1) {
                    // BUY = enter long (or flip from short)
                    if (openTrade && openTrade.side === 'short') {
                        // Close short: PnL = (entry - exit) / entry
                        const pnl = (openTrade.entry_price - price) / openTrade.entry_price;
                        trades.push({
                            entry_time: openTrade.entry_time,
                            exit_time: sig.time,
                            side: 'short',
                            entry_price: openTrade.entry_price,
                            exit_price: price,
                            pnl: pnl,
                            pnl_pct: pnl * 100,
                        });
                        openTrade = null;
                    }
                    if (openTrade) {
                        // Already long — alternating guarantees this won't happen, but defend
                        continue;
                    }
                    openTrade = { entry_time: sig.time, entry_price: price, side: 'long' };
                } else {
                    // SELL = enter short (or flip from long)
                    if (openTrade && openTrade.side === 'long') {
                        // Close long: PnL = (exit - entry) / entry
                        const pnl = (price - openTrade.entry_price) / openTrade.entry_price;
                        trades.push({
                            entry_time: openTrade.entry_time,
                            exit_time: sig.time,
                            side: 'long',
                            entry_price: openTrade.entry_price,
                            exit_price: price,
                            pnl: pnl,
                            pnl_pct: pnl * 100,
                        });
                        openTrade = null;
                    }
                    if (openTrade) {
                        // Already short — alternating guarantees this won't happen, but defend
                        continue;
                    }
                    openTrade = { entry_time: sig.time, entry_price: price, side: 'short' };
                }
            }

            // Close any remaining position at last bar
            if (openTrade) {
                const lastBar = historicalData[historicalData.length - 1];
                const price = lastBar.close;
                const pnl = openTrade.side === 'long'
                    ? (price - openTrade.entry_price) / openTrade.entry_price
                    : (openTrade.entry_price - price) / openTrade.entry_price;
                trades.push({
                    entry_time: openTrade.entry_time,
                    exit_time: lastBar.time,
                    side: openTrade.side,
                    entry_price: openTrade.entry_price,
                    exit_price: price,
                    pnl: pnl,
                    pnl_pct: pnl * 100,
                });
            }

            if (trades.length === 0) {
                document.getElementById('signalResult').innerHTML = '<div class="signal-result" style="color:var(--text-muted)">No completed trades.</div>';
                return;
            }

            // ── Compute metrics ──
            const wins = trades.filter(t => t.pnl > 0);
            // Exactly-zero-PnL trades are treated as losses for gross-loss and
            // profit-factor purposes so scratch trades do not inflate the win rate.
            const losses = trades.filter(t => t.pnl <= 0);
            const winRate = trades.length > 0 ? wins.length / trades.length : 0;
            const grossProfit = wins.reduce((s, t) => s + t.pnl, 0);
            const grossLoss = Math.abs(losses.reduce((s, t) => s + t.pnl, 0));
            const profitFactor = grossLoss > 0 ? grossProfit / grossLoss : grossProfit > 0 ? Infinity : 0;

            // Equity curve for max drawdown and compounded headline return
            let equity = 1;
            let peak = 1;
            let maxDd = 0;
            const equityCurve = trades.map(t => {
                equity *= (1 + t.pnl);
                if (equity > peak) peak = equity;
                const dd = (peak - equity) / peak;
                if (dd > maxDd) maxDd = dd;
                return equity;
            });

            const totalReturn = equity - 1;

            // Simplified Sharpe (annualized using trade count as proxy)
            const tradeReturns = trades.map(t => t.pnl);
            const avgReturn = tradeReturns.reduce((s, r) => s + r, 0) / tradeReturns.length;
            const stdReturn = Math.sqrt(tradeReturns.reduce((s, r) => s + (r - avgReturn) ** 2, 0) / tradeReturns.length);
            const sharpe = stdReturn > 0 ? (avgReturn / stdReturn) * Math.sqrt(trades.length) : 0;

            // ── Update Backtest Results UI ──
            document.getElementById('backtestSummary').style.display = 'none';
            document.getElementById('backtestMetrics').style.display = 'block';

            const pct = (v) => (v * 100).toFixed(2) + '%';
            const num = (v) => v != null && isFinite(v) ? v.toFixed(2) : '—';

            document.getElementById('btReturn').textContent = pct(totalReturn);
            document.getElementById('btReturn').style.color = totalReturn >= 0 ? 'var(--up)' : 'var(--down)';
            document.getElementById('btSharpe').textContent = num(sharpe);
            document.getElementById('btDrawdown').textContent = pct(maxDd);
            document.getElementById('btWinRate').textContent = pct(winRate);
            document.getElementById('btTrades').textContent = trades.length;
            document.getElementById('btProfitFactor').textContent = profitFactor === Infinity ? '∞' : num(profitFactor);
            document.getElementById('btStrategy').textContent = strategyName.replace(/_/g, ' ');
            document.getElementById('btSymbol').textContent = currentSymbol;
            document.getElementById('btTimeframe').textContent = currentTimeframe;

            // ── Render detailed trade list ──
            document.getElementById('btTradeCount').textContent = trades.length;
            const tbody = document.getElementById('btTradeRows');
            tbody.innerHTML = trades.map((t, idx) => {
                const entryStr = typeof t.entry_time === 'number' ? new Date(t.entry_time * 1000).toLocaleString() : (t.entry_time || '—');
                const exitStr = typeof t.exit_time === 'number' ? new Date(t.exit_time * 1000).toLocaleString() : (t.exit_time || '—');
                const ep = t.entry_price != null ? `$${Number(t.entry_price).toFixed(2)}` : '—';
                const xp = t.exit_price != null ? `$${Number(t.exit_price).toFixed(2)}` : '—';
                const sideLabel = t.side === 'long' ? 'LONG' : 'SHORT';
                const sideColor = t.side === 'long' ? 'var(--up)' : 'var(--down)';
                const pnlColor = t.pnl >= 0 ? 'var(--up)' : 'var(--down)';
                const pnlStr = t.pnl >= 0 ? `+${(t.pnl_pct || 0).toFixed(2)}%` : `${(t.pnl_pct || 0).toFixed(2)}%`;
                const epNum = Number(t.entry_price);
                const xpNum = Number(t.exit_price);
                const formulaStr = t.side === 'long'
                    ? `($${xpNum.toFixed(2)} − $${epNum.toFixed(2)}) ÷ $${epNum.toFixed(2)}`
                    : `($${epNum.toFixed(2)} − $${xpNum.toFixed(2)}) ÷ $${epNum.toFixed(2)}`;
                return `<tr onclick="toggleTradeDetail(${idx})">
                    <td>${idx + 1}</td>
                    <td style="font-size:9px;">${entryStr}</td>
                    <td style="color:${sideColor};font-weight:600;">${sideLabel}</td>
                    <td class="num">${ep}</td>
                    <td class="num">${xp}</td>
                    <td class="num" style="color:${pnlColor};font-weight:600;">${pnlStr}</td>
                </tr>
                <tr id="btTradeDetail${idx}" class="bt-trade-detail" style="display:none;">
                    <td colspan="6" style="padding:4px 8px 6px;">
                        <strong>Side:</strong> ${sideLabel}<br>
                        <strong>Entry:</strong> ${entryStr} @ ${ep}<br>
                        <strong>Exit:</strong> ${exitStr} @ ${xp}<br>
                        <strong>PnL:</strong> ${pnlStr}<br>
                        <strong>Formula:</strong> ${formulaStr} = ${(t.pnl_pct || 0).toFixed(2)}%
                    </td>
                </tr>`;
            }).join('');

            // ── Render trade markers on chart ──
            clearBacktestMarkers();
            if (typeof candleMarkers !== 'undefined' && candleMarkers) {
                const markers = [];
                // Client-side backtest entry_time/exit_time are already in chart format
                // (string 'YYYY-MM-DD' for daily, number unix sec for intraday), so no conversion needed.
                trades.forEach(t => {
                    if (t.entry_time) {
                        const isLong = t.side === 'long';
                        markers.push({
                            time: t.entry_time,
                            position: isLong ? 'belowBar' : 'aboveBar',
                            color: isLong ? '#089981' : '#F23645',
                            shape: isLong ? 'arrowUp' : 'arrowDown',
                            text: isLong ? 'BT LONG' : 'BT SHORT',
                        });
                    }
                    if (t.exit_time) {
                        const isProfit = t.pnl > 0;
                        markers.push({
                            time: t.exit_time,
                            position: 'aboveBar',
                            color: isProfit ? '#089981' : '#f23645',
                            shape: 'arrowDown',
                            text: isProfit ? `+${(t.pnl_pct || 0).toFixed(1)}%` : `${(t.pnl_pct || 0).toFixed(1)}%`,
                        });
                    }
                });
                backtestMarkers = markers;
                const existing = candleMarkers._markers || [];
                // Also keep signal markers if any
                const signalOnly = existing.filter(m => {
                    const text = m.text || '';
                    return text === 'B' || text === 'S';
                });
                candleMarkers.setMarkers([...signalOnly, ...markers]);
            }

            // ── Signal result / trade log ──
            const logRows = trades.slice(-10).reverse().map(t => {
                const ts = typeof t.exit_time === 'number' ? new Date(t.exit_time * 1000).toLocaleString() : t.exit_time;
                const pnlColor = t.pnl >= 0 ? 'var(--up)' : 'var(--down)';
                const pnlStr = t.pnl >= 0 ? `+${(t.pnl_pct || 0).toFixed(2)}%` : `${(t.pnl_pct || 0).toFixed(2)}%`;
                return `<tr>
                    <td style="padding:2px 4px;font-size:10px;">${ts}</td>
                    <td style="padding:2px 4px;color:${pnlColor};font-weight:600;text-align:right;">${pnlStr}</td>
                </tr>`;
            }).join('');

            // Show backtest summary in signal result too
            document.getElementById('signalResult').innerHTML = `
                <div style="font-size:11px;padding:4px;">
                    <span style="color:var(--up)">W: ${wins.length}</span>
                    <span style="color:var(--down);margin-left:8px;">L: ${losses.length}</span>
                    <span style="color:var(--text-muted);margin-left:8px;">
                        Return: <strong style="color:${totalReturn >= 0 ? 'var(--up)' : 'var(--down)'}">${pct(totalReturn)}</strong>
                    </span>
                    <button onclick="clearBacktestMarkers();clearSignal();" style="float:right;background:transparent;border:1px solid var(--border);color:var(--text-muted);border-radius:3px;padding:0 5px;cursor:pointer;font-size:10px;">X</button>
                </div>
                <div style="margin-top:6px;border-top:1px solid var(--border);padding-top:4px;">
                    <div style="font-size:10px;color:var(--text-muted);margin-bottom:2px;">Trade Log (last ${Math.min(trades.length, 10)})</div>
                    <table style="width:100%;font-size:10px;border-collapse:collapse;">
                        <thead>
                            <tr style="color:var(--text-muted);">
                                <th style="text-align:left;padding:2px 4px;">Exit</th>
                                <th style="text-align:right;padding:2px 4px;">P&L</th>
                            </tr>
                        </thead>
                        <tbody>${logRows}</tbody>
                    </table>
                </div>
            `;
        }

        // ── Signal clear also clears backtest ──
        const _origClearSignal = clearSignal;
        clearSignal = function() {
            _origClearSignal();
            clearBacktestMarkers();
            document.getElementById('backtestMetrics').style.display = 'none';
            document.getElementById('backtestSummary').style.display = 'block';
        };

        function toggleBottomPanel() {
            const panel = document.getElementById('chartBottom');
            if (!panel) return;
            panel.classList.toggle('visible');
            const btn = document.getElementById('bottomPanelToggle');
            if (btn) btn.innerText = panel.classList.contains('visible') ? '▼ Collapse' : '▲ Expand';
        }

        function showBottomPanel() {
            const panel = document.getElementById('chartBottom');
            if (!panel) return;
            panel.classList.add('visible');
            const btn = document.getElementById('bottomPanelToggle');
            if (btn) btn.innerText = '▼ Collapse';
        }

        // Delegated click for strategy items — runs backtest instead of raw signals
        document.getElementById('stratFeed').addEventListener('click', (e) => {
            const item = e.target.closest('.strat-item');
            if (!item) return;
            const strategy = decodeURIComponent(item.dataset.strategy);
            const params = JSON.parse(decodeURIComponent(item.dataset.params));
            runBacktestOnStrategy(strategy, params);
        });

        // Boot
        initChart();
        initIndicators();
        addSignalCondition('rsi', { period: 14 }, 'lt', 30, 'long');
        addSignalCondition('rsi', { period: 14 }, 'gt', 70, 'short');
        loadWatchlist();
        initTrading(); // fire-and-forget (async, updates UI when ready)
