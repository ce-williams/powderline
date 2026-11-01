import { test } from 'node:test';
import assert from 'node:assert/strict';
import '../snow-report-state.js';
const tools = globalThis.powderlineSnowTools;
const now = Date.parse('2026-11-01T12:00:00Z');
test('report metrics distinguish missing, measured zero, stale and expired reports', () => {
  const report = { reportedAt: '2026-11-01T05:00:00-07:00', snow24: 0, depth: 18 };
  assert.equal(tools.value(report, 'snow24', now), '0″');
  assert.equal(tools.value(report, 'snow48', now), '—');
  assert.equal(tools.value({ ...report, reportedAt: null }, 'depth', now), '—');
  assert.equal(tools.stale(report, now), false);
  assert.equal(tools.stale({ ...report, reportedAt: '2026-10-29T12:00:00Z' }, now), true);
  assert.equal(tools.value({ ...report, reportedAt: '2026-06-01T12:00:00Z' }, 'snow24', now), '—');
  assert.equal(tools.value({ ...report, reportedAt: '2027-06-01T12:00:00Z' }, 'depth', now), '—');
});
test('reject malformed refresh manifests and unsafe source links', () => {
  assert.equal(Boolean(tools.valid({ resorts: { Vail: { source: 'javascript:alert(1)' } } })), false);
  assert.equal(Boolean(tools.valid({ resorts: { Vail: { snow24: 'three' } } })), false);
  assert.equal(Boolean(tools.valid({ resorts: { Vail: { snow24: 0, source: 'https://www.vail.com/' } } })), true);
});
