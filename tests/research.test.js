const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

function loadSafePctChange() {
  const source = fs.readFileSync(path.join(__dirname, '..', 'js', 'research.js'), 'utf8');
  const start = source.indexOf('function safePctChange');
  assert.notEqual(start, -1, 'safePctChange helper should exist');
  const end = source.indexOf('function symbolVariantsFor');
  const snippet = source.slice(start, end);
  const context = vm.createContext({ Number, Math, console, window: {} });
  vm.runInContext(snippet, context);
  return context.window.safePctChange;
}

test('safePctChange returns null for zero or non-finite bases and finite values otherwise', () => {
  const safePctChange = loadSafePctChange();
  assert.equal(safePctChange(110, 100), 10);
  assert.equal(safePctChange(90, 100), -10);
  assert.equal(safePctChange(100, 0), null);
  assert.equal(safePctChange(100, Number.NaN), null);
  assert.equal(safePctChange(Number.NaN, 100), null);
});
