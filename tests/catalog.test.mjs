import { test } from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import vm from "node:vm";

const context = { window: {} };
vm.runInNewContext(readFileSync(new URL("../camera-catalog.js", import.meta.url), "utf8"), context);
const resorts = JSON.parse(JSON.stringify(context.window.powderlineResortCatalog));
const cameras = JSON.parse(JSON.stringify(context.window.powderlineCameraCatalog));
const registry = JSON.parse(readFileSync(new URL("../source-registry.json", import.meta.url)));
const html = readFileSync(new URL("../index.html", import.meta.url), "utf8");
const csp = html.match(/Content-Security-Policy" content="([^"]+)"/)[1];
const expectedResorts = ["Arapahoe Basin", "Aspen Highlands", "Aspen Mountain", "Beaver Creek", "Breckenridge", "Buttermilk", "Chapman Hill", "Copper Mountain", "Cranor Hill", "Crested Butte", "Cuchara Mountain Park", "Echo Mountain", "Eldora", "Granby Ranch", "Hesperus", "Hoedown Hill", "Howelsen Hill", "Kendall Mountain", "Keystone", "Lake City Ski Hill", "Lee's Ski Hill", "Loveland", "Monarch Mountain", "Powderhorn", "Purgatory", "Silverton Mountain", "Ski Cooper", "Snowmass", "Steamboat", "Sunlight Mountain", "Telluride", "Vail", "Winter Park", "Wolf Creek"];

function httpsURL(value) {
  const url = new URL(value);
  assert.equal(url.protocol, "https:", value);
  assert.equal(url.username, "", value);
  assert.equal(url.password, "", value);
  assert.ok(!url.hostname.includes("undefined"), value);
  return url;
}
function allowed(value, directive) {
  const url = httpsURL(value);
  const entries = csp.split(";").map((entry) => entry.trim().split(/\s+/));
  const hosts = entries.find((entry) => entry[0] === directive).slice(1);
  assert.ok(hosts.some((host) => {
    if (!host.startsWith("https://")) return false;
    const permitted = new URL(host.replace("*.", "wildcard."));
    return host.includes("*.")
      ? url.hostname.endsWith(permitted.hostname.slice("wildcard".length)) && url.port === permitted.port
      : url.origin === permitted.origin;
  }), `${directive} blocks ${value}`);
}

test("all 34 Colorado alpine ski areas appear once, including areas without public feeds", () => {
  assert.deepEqual(resorts.map((resort) => resort.name).sort(), expectedResorts.sort());
  for (const resort of resorts) {
    assert.ok(resort.region);
    assert.match(resort.reviewedOn, /^\d{4}-\d{2}-\d{2}$/);
    httpsURL(resort.source);
  }
});
test("camera IDs, resort assignments, providers, and source URLs are valid", () => {
  assert.equal(new Set(cameras.map((camera) => camera.id)).size, cameras.length);
  assert.equal(new Set(cameras.map((camera) => `${camera.resort}/${camera.name}`)).size, cameras.length);
  for (const camera of cameras) {
    assert.ok(resorts.some((resort) => resort.name === camera.resort), camera.resort);
    assert.ok(["image", "brownrice", "iframe", "link"].includes(camera.provider));
    assert.ok(camera.name && camera.kind && camera.id);
    for (const field of ["src", "source", "previewSrc", "playerUrl", "configUrl"]) {
      if (camera[field]) httpsURL(camera[field]);
    }
    if (camera.provider === "link") assert.ok(camera.note, camera.id);
  }
});
test("CSP permits every catalog image and embedded player, including redirect hosts", () => {
  for (const camera of cameras) {
    if (camera.provider === "image") allowed(camera.src, "img-src");
    if (camera.previewSrc) allowed(camera.previewSrc, "img-src");
    if (["brownrice", "iframe"].includes(camera.provider)) allowed(camera.src, "frame-src");
  }
  allowed("https://storage4.roundshot.com/latest.jpg", "img-src");
  allowed("https://assets12.webcam.io/latest.jpg", "img-src");
});
test("published source registry exactly matches both runtime catalogs", () => {
  assert.deepEqual(registry.resorts, resorts);
  assert.deepEqual(registry.cameras, cameras);
});
test("restricted and maintenance-only sources remain explicitly accessible", () => {
  assert.ok(cameras.some((camera) => camera.resort === "Winter Park" && camera.provider === "link"));
  assert.ok(cameras.some((camera) => camera.resort === "Steamboat"));
  assert.match(resorts.find((resort) => resort.name === "Eldora").note, /maintenance/);
  assert.ok(!cameras.some((camera) => camera.resort === "Eldora"));
});

test("every changed browser asset shares the current cache version", () => {
  const versions = [...html.matchAll(/(?:src|href)="\.\/(?:camera-catalog\.js|app\.js|styles\.css|snapshot-state\.js|snapshot-manifest\.js)\?v=([^"\s]+)"/g)].map((match) => match[1]);
  assert.equal(versions.length, 5);
  assert.equal(new Set(versions).size, 1);
});
