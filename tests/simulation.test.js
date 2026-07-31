const test = require('node:test');
const assert = require('node:assert/strict');
const { SimulationEngine } = require('../js/simulation.js');

test('setStrategy clears pending signals so deselected strategy cannot fill after switch', () => {
  const engine = new SimulationEngine();
  engine._pendingSignals = { breakout_hunter: { action: 'enter_long', strategy: 'breakout_hunter' } };

  engine.setStrategy('rsi_reversion');

  assert.deepEqual(engine._pendingSignals, {});
  assert.deepEqual(engine.activeStrategies, ['rsi_reversion']);
});
