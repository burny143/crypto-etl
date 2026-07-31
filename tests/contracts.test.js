const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadContractsModule() {
  const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'contracts.js'), 'utf8');
  const sanitized = source
    .replace(/export\s+/g, '')
    .replace(/\nexport type \{[\s\S]*?\};?\n?/g, '\n');
  const context = vm.createContext({
    console,
    Date,
    Math,
    Number,
    String,
    Object,
    Array,
    RegExp,
    Map,
    Set,
    JSON,
    Error,
    Infinity,
    NaN,
    isNaN,
    parseFloat,
    parseInt,
  });
  vm.runInContext(sanitized, context);
  return context;
}

test('contract helpers support LONG/SHORT PnL validation and favorable execution fills', () => {
  const context = loadContractsModule();
  const { Signal, BacktestTrade, ExecutableSignal, PnLBreakdown } = context;

  const longTrade = new BacktestTrade('t1', 'BTC/USDT', 'LONG', 1000, 1100, 100, 110, 1, 'test');
  const longPnl = longTrade.calculatePnL();
  assert.equal(longPnl instanceof PnLBreakdown, true);
  assert.equal(longPnl.validateCalculation(), true);

  const shortTrade = new BacktestTrade('t2', 'BTC/USDT', 'SHORT', 1000, 1100, 100, 90, 1, 'test');
  const shortPnl = shortTrade.calculatePnL();
  assert.equal(shortPnl instanceof PnLBreakdown, true);
  assert.equal(shortPnl.validateCalculation(), true);

  assert.doesNotThrow(() => BacktestTrade.calculatePositionSize(10000, 0.01, 100, 105, 'SHORT'));

  const signal = new Signal(1000, 'BTC/USDT', 'test', 'BUY', 0.8, 100, {});
  const executable = new ExecutableSignal(1000, 'BTC/USDT', 'test', 'BUY', 0.8, 100, {}, 99, 0.1);
  executable.markAsExecuted(99, 0.1);
  assert.equal(executable.calculateExecutionPnL(1) > 0, true);
  assert.equal(executable.isPending(), false);
});
