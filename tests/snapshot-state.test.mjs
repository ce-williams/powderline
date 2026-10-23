import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";
const context = { window: {}, URL };
vm.runInNewContext(readFileSync(new URL("../snapshot-state.js", import.meta.url), "utf8"), context);
const tools = context.window.powderlineSnapshotTools;
const entry = {file:"snapshots/test-cam.jpg",fetchedAt:"2026-10-21T10:00:00Z",sha256:"abc",status:"ok"};
const at = (time) => Date.parse(`2026-10-21T${time}:00Z`);

test("snapshot paths and dates must match the expected camera", () => {
  assert.ok(tools.valid("test-cam", entry));
  assert.ok(!tools.valid("other-cam", entry));
  assert.ok(!tools.valid("test-cam", {...entry,file:"https://example.com/tracker.jpg"}));
  assert.ok(!tools.valid("test-cam", {...entry,fetchedAt:"not a date"}));
});
test("age labels expose minutes, hours, days, and tolerate small clock skew", () => {
  assert.equal(tools.age(entry.fetchedAt, at("10:30")), "Fetched 30m ago");
  assert.equal(tools.age(entry.fetchedAt, at("11:00")), "Fetched 1h ago");
  assert.equal(tools.age(entry.fetchedAt, Date.parse("2026-10-23T10:00:00Z")), "Fetched 2d ago");
  assert.equal(tools.age(entry.fetchedAt, at("09:59")), "Fetched just now");
});
test("retained or overdue snapshots are marked stale without changing their age", () => {
  assert.equal(tools.stale(entry, at("11:00")), false);
  assert.equal(tools.stale(entry, at("12:01")), true);
  assert.equal(tools.stale({...entry,status:"retained"}, at("11:00")), true);
});
test("snapshot requests stay under the GitHub Pages repository path", () => {
  assert.equal(tools.url(entry,"https://example.github.io/powderline/"), "https://example.github.io/powderline/snapshots/test-cam.jpg?v=abc");
});

test("overdue batches and unchanged images are not presented as current conditions", () => {
  assert.equal(tools.batchDelayed({generatedAt:entry.fetchedAt}, at("11:00")), false);
  assert.equal(tools.batchDelayed({generatedAt:entry.fetchedAt}, at("11:31")), true);
  assert.equal(tools.batchDelayed({}, at("11:00")), true);
  assert.equal(tools.unchanged({...entry,changedAt:entry.fetchedAt},at("13:00")), "");
  assert.equal(tools.unchanged({...entry,fetchedAt:"2026-10-21T13:00:00Z",changedAt:entry.fetchedAt},at("13:00")), "Source unchanged for 3h");
});
