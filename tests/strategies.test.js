const test = require('node:test');
const assert = require('node:assert/strict');
const { calcRSI, calcHighest, calcLowest, calcATR, evaluateRSI, evaluateBreakout } = require('../js/strategies.js');

function expectedRsi(closes, period) {
  const changes = closes.slice(1).map((close, index) => close - closes[index]);
  let avgGain = 0;
  let avgLoss = 0;

  for (let i = 0; i < period; i += 1) {
    const change = changes[i];
    if (change >= 0) avgGain += change;
    else avgLoss += -change;
  }

  avgGain /= period;
  avgLoss /= period;

  if (avgGain === 0 && avgLoss === 0) return 50;
  if (avgLoss === 0) return 100;

  for (let i = period; i < changes.length; i += 1) {
    const change = changes[i];
    avgGain = ((avgGain * (period - 1)) + (change > 0 ? change : 0)) / period;
    avgLoss = ((avgLoss * (period - 1)) + (change < 0 ? -change : 0)) / period;
  }

  const rs = avgGain / avgLoss;
  return 100 - 100 / (1 + rs);
}

test('calcRSI uses Wilder smoothing', () => {
  const closes = [100, 102, 101, 103, 102, 104, 103, 105];
  const expected = expectedRsi(closes, 2);
  assert.equal(calcRSI(closes, 2), expected);
});

test('calcHighest and calcLowest return NaN for empty arrays', () => {
  assert.ok(Number.isNaN(calcHighest([], 3)));
  assert.ok(Number.isNaN(calcLowest([], 3)));
});

test('calcATR returns null for invalid volatility input', () => {
  const candles = [
    { high: 10, low: 9, close: 9.5 },
    { high: NaN, low: NaN, close: NaN },
  ];

  assert.equal(calcATR(candles, 1), null);
});

test('evaluateRSI returns null for invalid candle data', () => {
  const candles = Array.from({ length: 25 }, (_, i) => ({
    open: 100 + i,
    high: 101 + i,
    low: 99 + i,
    close: 100 + i,
    volume: 100,
  }));
  candles[24] = { open: 'bad', high: 101, low: 99, close: 100, volume: 100 };

  assert.equal(evaluateRSI(candles), null);
});

test('evaluateBreakout returns null for malformed candles', () => {
  const candles = Array.from({ length: 25 }, () => ({
    open: 100,
    high: 120,
    low: 80,
    close: 100,
    volume: 100,
  }));
  candles[24] = { open: 100, high: null, low: 80, close: 100, volume: 100 };

  assert.equal(evaluateBreakout(candles), null);
});
