const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadComputeVWAP() {
  const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'charts.js'), 'utf8');
  const start = source.indexOf('function computeVWAP(data) {');
  const end = source.indexOf('function computeStochRSI');
  const snippet = source.slice(start, end);
  const context = vm.createContext({ console, Date, Number, currentTimeframe: '1d' });
  vm.runInContext(snippet, context);
  return context.computeVWAP;
}

test('computeVWAP accumulates across daily bars instead of resetting every bar', () => {
  const computeVWAP = loadComputeVWAP();
  const data = [
    { time: '2024-01-01', high: 100, low: 100, close: 100, value: 1 },
    { time: '2024-01-02', high: 200, low: 200, close: 200, value: 1 },
  ];

  const result = computeVWAP(data);
  assert.equal(result[0].value, 100);
  assert.equal(result[1].value, 150);
});
