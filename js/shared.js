// shared.js — Supabase client, indicator computation, and utilities
// Shared across charts.html and research.html

// ── Supabase Init ──
const SUPABASE_URL = "https://ymnlqggxeeyqvrojsrzh.supabase.co";
const SUPABASE_ANON_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InltbmxxZ2d4ZWV5cXZyb2pzcnpoIiwicm9sZSI6ImFub24iLCJpYXQiOjE3ODM3NjQ2NDQsImV4cCI6MjA5OTM0MDY0NH0.wsO53Ninsb_9Mxt0Me5q3vYuQMr5XFUASYgdBzeHfbQ";
const { createClient } = supabase;
const supabaseClient = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);

// ── Data Helpers ──
function getClose(data) { return data.map(d => d.close); }
function getHigh(data) { return data.map(d => d.high); }
function getLow(data) { return data.map(d => d.low); }
function getVolume(data) { return data.map(d => d.value); }
function getTime(data) { return data.map(d => d.time); }

// ── Indicator Computation ──
        function computeSMA(data, period) {
            period = Math.floor(Number(period));
            if (!Number.isFinite(period) || period < 1) return [];
            const close = getClose(data), times = getTime(data);
            const result = [];
            for (let i = period - 1; i < close.length; i++) {
                let sum = 0;
                for (let j = 0; j < period; j++) sum += close[i - j];
                result.push({ time: times[i], value: sum / period });
            }
            return result;
        }

        function computeEMA(data, period) {
            period = Math.floor(Number(period));
            if (!Number.isFinite(period) || period < 1) return [];
            const close = getClose(data), times = getTime(data);
            const k = 2 / (period + 1);
            const result = [];
            for (let i = 0; i < close.length; i++) {
                if (i < period - 1) continue;
                if (i === period - 1) {
                    const ema = close.slice(0, period).reduce((a, b) => a + b, 0) / period;
                    result.push({ time: times[i], value: ema });
                } else {
                    const prev = result[result.length - 1].value;
                    result.push({ time: times[i], value: close[i] * k + prev * (1 - k) });
                }
            }
            return result;
        }

        function computeRSI(data, period) {
            period = Math.floor(Number(period));
            if (!Number.isFinite(period) || period < 2) return [];
            const close = getClose(data), times = getTime(data);
            if (close.length < period + 1) return [];
            const deltas = [];
            for (let i = 1; i < close.length; i++) deltas.push(close[i] - close[i - 1]);
            let avgGain = 0, avgLoss = 0;
            // First SMA of gains/losses over the initial `period` deltas
            for (let i = 0; i < period; i++) {
                if (deltas[i] > 0) avgGain += deltas[i]; else avgLoss -= deltas[i];
            }
            avgGain /= period; avgLoss /= period;
            // First RSI value uses the SMA directly
            const result = [];
            if (avgLoss === 0 && avgGain === 0) {
                result.push({ time: times[period], value: 50 });
            } else if (avgLoss === 0) {
                result.push({ time: times[period], value: 100 });
            } else {
                const rs0 = avgGain / avgLoss;
                result.push({ time: times[period], value: 100 - 100 / (1 + rs0) });
            }
            // Subsequent values use Wilder smoothing (start at period+1 to avoid re-using deltas[period-1])
            for (let i = period + 1; i < close.length; i++) {
                const diff = close[i] - close[i - 1];
                avgGain = ((avgGain * (period - 1)) + (diff > 0 ? diff : 0)) / period;
                avgLoss = ((avgLoss * (period - 1)) + (diff < 0 ? -diff : 0)) / period;
                if (avgLoss === 0 && avgGain === 0) {
                    result.push({ time: times[i], value: 50 });
                } else if (avgLoss === 0) {
                    result.push({ time: times[i], value: 100 });
                } else {
                    const rs = avgGain / avgLoss;
                    result.push({ time: times[i], value: 100 - 100 / (1 + rs) });
                }
            }
            return result;
        }

        function computeBB(data, period, std) {
            period = Math.floor(Number(period));
            std = Number(std);
            if (!Number.isFinite(period) || period < 1 || !Number.isFinite(std)) return { upper: [], mid: [], lower: [] };
            const close = getClose(data), times = getTime(data);
            if (close.length < period) return { upper: [], mid: [], lower: [] };
            const mid = computeSMA(data, period);
            const upper = [], lower = [];
            for (let i = period - 1; i < close.length; i++) {
                const m = mid[i - (period - 1)].value;
                let sqSum = 0;
                for (let j = 0; j < period; j++) sqSum += (close[i - j] - m) ** 2;
                const s = Math.sqrt(sqSum / period);
                upper.push({ time: times[i], value: m + std * s });
                lower.push({ time: times[i], value: m - std * s });
            }
            return { upper, mid, lower };
        }

        function computeTR(high, low, close) {
            const tr = [0];
            for (let i = 1; i < high.length; i++) {
                const hl = high[i] - low[i];
                const hc = Math.abs(high[i] - close[i - 1]);
                const lc = Math.abs(low[i] - close[i - 1]);
                tr.push(Math.max(hl, hc, lc));
            }
            return tr;
        }

        function computeATR(data, period) {
            period = Math.floor(Number(period));
            if (!Number.isFinite(period) || period < 1) return [];
            const high = getHigh(data), low = getLow(data), close = getClose(data), times = getTime(data);
            if (close.length < period + 1) return [];
            const tr = computeTR(high, low, close);
            // Wilder smoothing
            let atr = tr.slice(1, period + 1).reduce((a, b) => a + b, 0) / period;
            const result = [{ time: times[period], value: atr }];
            for (let i = period + 1; i < tr.length; i++) {
                atr = (atr * (period - 1) + tr[i]) / period;
                result.push({ time: times[i], value: atr });
            }
            return result;
        }

        function computeADX(data, period) {
            period = Math.floor(Number(period));
            if (!Number.isFinite(period) || period < 1) return [];
            const high = getHigh(data), low = getLow(data), close = getClose(data), times = getTime(data);
            if (close.length < period * 2) return [];
            // True Range
            const tr = computeTR(high, low, close);
            // +DM / -DM
            const plusDM = [0], minusDM = [0];
            for (let i = 1; i < high.length; i++) {
                const up = high[i] - high[i - 1];
                const down = low[i - 1] - low[i];
                plusDM.push((up > down && up > 0) ? up : 0);
                minusDM.push((down > up && down > 0) ? down : 0);
            }
            // Wilder smooth
            const smooth = (arr, p) => {
                let val = arr.slice(1, p + 1).reduce((a, b) => a + b, 0) / p;
                const res = [val];
                for (let i = p + 1; i < arr.length; i++) {
                    val = (val * (p - 1) + arr[i]) / p;
                    res.push(val);
                }
                return res;
            };
            const sTR = smooth(tr, period);
            const sPDM = smooth(plusDM, period);
            const sMDM = smooth(minusDM, period);
            // +DI / -DI
            const pDI = sPDM.map((v, i) => 100 * v / (sTR[i] || 0.001));
            const mDI = sMDM.map((v, i) => 100 * v / (sTR[i] || 0.001));
            // DX → ADX
            const dx = pDI.map((v, i) => 100 * Math.abs(v - mDI[i]) / ((v + mDI[i]) || 0.001));
            const result = [{ time: times[period * 2 - 1], value: dx.slice(0, period).reduce((a, b) => a + b, 0) / period }];
            let adx = result[0].value;
            for (let i = period; i < dx.length; i++) {
                adx = (adx * (period - 1) + dx[i]) / period;
                result.push({ time: times[period + i], value: adx });
            }
            return result;
        }

        function computeOBV(data) {
            const close = getClose(data), volume = getVolume(data), times = getTime(data);
            let obv = 0;
            const result = [{ time: times[0], value: 0 }];
            for (let i = 1; i < close.length; i++) {
                obv += Math.sign(close[i] - close[i - 1]) * volume[i];
                result.push({ time: times[i], value: obv });
            }
            return result;
        }

        function computeKC(data, period, mult) {
            period = Math.floor(Number(period));
            mult = Number(mult);
            if (!Number.isFinite(period) || period < 1 || !Number.isFinite(mult)) return { upper: [], mid: [], lower: [] };
            const close = getClose(data);
            if (close.length < period + 1) return { upper: [], mid: [], lower: [] };
            const mid = computeEMA(data, period);
            const atr = computeATR(data, period);
            // Index atr by time for alignment (mid starts one bar earlier than atr)
            const atrByTime = new Map(atr.map(p => [p.time, p.value]));
            const upper = [], lower = [];
            for (const p of mid) {
                const atrVal = atrByTime.get(p.time);
                if (atrVal == null) continue;
                upper.push({ time: p.time, value: p.value + mult * atrVal });
                lower.push({ time: p.time, value: p.value - mult * atrVal });
            }
            return { upper, mid: mid.filter(p => atrByTime.has(p.time)), lower };
        }

// ── Utility ──
        function escapeHtml(str) {
            if (str == null) return '';
            var d = document.createElement('div');
            d.appendChild(document.createTextNode(String(str)));
            return d.innerHTML;
        }
