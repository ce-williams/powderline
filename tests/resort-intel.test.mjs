import test from 'node:test';
import assert from 'node:assert/strict';
import '../resort-intel.js';
const tools = globalThis.powderlineIntelTools;
test('shared geographic windows stay within their source image', () => {
  assert.equal(tools.validView([0.2, 0.1, 0.6, 0.8]), true);
  for (const view of [[-0.1, 0, 1, 1], [0.6, 0, 0.6, 1], [0, 0, 0, 1], [NaN, 0, 1, 1], [0, 0, 1]]) assert.equal(tools.validView(view), false);
  assert.equal(tools.imagePath('satellite/region-abcdef1234.webp'), true);
});
test('satellite paths and dates reject traversal, remote substitutions and old captures', () => {
  const now = Date.now();
  const row = {image: 'satellite/copper-mountain.jpg', source: 'https://example.com', capturedAt: new Date(now).toISOString()};
  assert.equal(tools.usableImage(row, now), true);
  for (const image of ['satellite/../key.jpg', 'https://evil.example/image.jpg', 'satellite/a.jpg?x=y']) assert.equal(tools.usableImage({...row, image}, now), false);
  assert.equal(tools.usableImage({...row, capturedAt: new Date(now-31*86400000).toISOString()}, now), false);
});
test('briefs expire with their evidence, not just their generation time', () => {
  const now = Date.now(), stamp = new Date(now).toISOString();
  const row = {summary: 'A dated report.', generatedAt: stamp, sources: [{url: 'https://example.com', kind: 'reported', reportedAt: stamp}]};
  assert.equal(tools.usableRead(row, now), true);
  assert.equal(tools.usableRead({...row, sources: [{...row.sources[0], reportedAt: new Date(now-73*3600000).toISOString()}]}, now), false);
  assert.equal(tools.usableRead({...row, sources: []}, now), false);
  assert.equal(tools.usableRead({...row, generatedAt: new Date(now+3600000).toISOString()}, now), false);
});
