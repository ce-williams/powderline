const cameraCatalog = window.powderlineCameraCatalog || [];
const regions = [
  { name: "Summit County", resorts: ["Arapahoe Basin", "Keystone", "Breckenridge", "Copper Mountain"] },
  { name: "Eagle County", resorts: ["Vail", "Beaver Creek"] },
  { name: "Clear Creek County", resorts: ["Loveland"] },
  { name: "Grand County", resorts: ["Winter Park"] },
  { name: "Gunnison County", resorts: ["Crested Butte"] },
];
const resortOrder = regions.flatMap((region) => region.resorts);
const orderedCameras = [...cameraCatalog].sort((a, b) => {
  return resortOrder.indexOf(a.resort) - resortOrder.indexOf(b.resort);
});
const cameraWall = document.querySelector("#camera-wall");
const resortFilter = document.querySelector("#resort-filter");
const cameraOnlyButton = document.querySelector("#camera-only");
const cameraCards = [];
const cameraRegions = new Map();
let activeResort = "all";

const clockFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Denver",
  hour: "numeric",
  minute: "2-digit",
});
const dateFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Denver",
  weekday: "short",
  month: "short",
  day: "numeric",
  year: "numeric",
});
const shortTimeFmt = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Denver",
  hour: "numeric",
  minute: "2-digit",
});

function makeElement(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined) element.textContent = text;
  return element;
}

function makeExternalLink(url, label) {
  const link = makeElement("a", "", label);
  link.href = url;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  return link;
}

function loadPlayer(frame, camera) {
  const player = makeElement("iframe");
  player.title = `${camera.resort} ${camera.name} camera`;
  player.src = camera.src;
  player.allow = "fullscreen; picture-in-picture";
  player.allowFullscreen = true;
  player.referrerPolicy = "strict-origin-when-cross-origin";
  frame.classList.remove("player-pending");
  frame.querySelector(".player-entry")?.remove();
  frame.prepend(player);
  frame.querySelector(".expand-button").hidden = false;
}

function createCameraCard(camera, index) {
  const card = makeElement("article", "camera-panel");
  card.dataset.resort = camera.resort;
  card.dataset.cameraId = camera.id;

  const frame = makeElement("div", `camera-frame${camera.provider === "image" ? " image-frame" : ""}`);
  if (camera.provider === "image") {
    const image = makeElement("img", "live-image");
    image.src = camera.src;
    image.dataset.source = camera.src;
    image.alt = `${camera.resort} ${camera.name} camera view`;
    image.loading = "lazy";
    image.referrerPolicy = "strict-origin-when-cross-origin";
    frame.append(image);
  } else if (window.location.protocol === "file:") {
    // A file:// page has an opaque origin. Many camera providers reject its
    // embedded player even when the same URL works as a top-level page.
    frame.classList.add("embed-placeholder");
    const message = makeElement("div", "embed-placeholder-copy");
    message.append(
      makeElement("span", "embed-placeholder-kicker", "HTTPS EMBED PREVIEW"),
      makeElement("strong", "", "Open this camera directly"),
      makeElement("span", "", "Camera providers may reject embeds opened from a local file.")
    );
    const openPlayer = makeExternalLink(camera.src, "OPEN LIVE PLAYER ↗");
    openPlayer.className = "embed-placeholder-link";
    frame.append(message, openPlayer);
  } else {
    frame.classList.add("player-pending");
    const entry = makeElement("div", "player-entry");
    entry.append(makeElement("span", "player-entry-label", "LIVE PLAYER · ON REQUEST"));
    const load = makeElement("button", "load-player", "Load camera →");
    load.type = "button";
    load.setAttribute("aria-label", `Load ${camera.resort} ${camera.name} camera`);
    load.addEventListener("click", () => loadPlayer(frame, camera), { once: true });
    entry.append(load);
    frame.append(entry);
  }

  frame.append(makeElement("span", "frame-index", `CAM ${String(index + 1).padStart(2, "0")} / ${cameraCatalog.length}`));
  const expand = makeElement("button", "expand-button", "⛶");
  expand.type = "button";
  expand.setAttribute("aria-label", `Expand ${camera.resort} ${camera.name} camera`);
  if (camera.provider !== "image") expand.hidden = true;
  frame.append(expand, makeElement("span", "frame-category", camera.kind));
  if (camera.refreshNote) frame.append(makeElement("span", "image-refresh-note", camera.refreshNote));
  card.append(frame);

  const caption = makeElement("div", "camera-caption");
  const description = makeElement("div");
  const resortName = makeElement("div", "camera-resort", camera.resort.toUpperCase());
  resortName.append(makeElement("span", "", "COLORADO"));
  description.append(resortName);
  const cameraName = makeElement("div", "camera-name", camera.name);
  if (camera.elevation) cameraName.append(makeElement("span", "elevation", camera.elevation));
  description.append(cameraName);
  caption.append(description);

  const source = makeElement("div", "camera-source");
  source.append(makeElement("span", "source-dot"));
  const sourceDetails = makeElement("span");
  if (camera.provider === "image") {
    sourceDetails.append(document.createTextNode("IMAGE CHECKED "), makeElement("time", "image-checked", "—"), document.createElement("br"));
  }
  sourceDetails.append(makeExternalLink(camera.playerUrl || (camera.provider === "image" ? camera.source : camera.src), camera.provider === "image" ? "OPEN CAM ↗" : "OPEN PLAYER ↗"));
  sourceDetails.append(document.createElement("br"), makeExternalLink(camera.source, "RESORT CAMS ↗"));
  source.append(sourceDetails);
  caption.append(source);
  card.append(caption);
  return card;
}

function populateResortFilter() {
  const counts = new Map();
  orderedCameras.forEach((camera) => counts.set(camera.resort, (counts.get(camera.resort) || 0) + 1));
  const allOption = makeElement("option", "", `All resorts · ${cameraCatalog.length} cameras`);
  allOption.value = "all";
  resortFilter.append(allOption);
  counts.forEach((count, resort) => {
    const option = makeElement("option", "", `${resort} · ${count} cameras`);
    option.value = resort;
    resortFilter.append(option);
  });
}

regions.forEach((region) => {
  const section = makeElement("section", "camera-region");
  section.setAttribute("aria-label", `${region.name} cameras`);
  const heading = makeElement("div", "region-heading");
  heading.append(makeElement("span", "region-name", region.name.toUpperCase()));
  const grid = makeElement("div", "camera-group-grid");
  section.append(heading, grid);
  cameraWall.append(section);
  cameraRegions.set(region.name, { section, grid });
});

orderedCameras.forEach((camera, index) => {
  const card = createCameraCard(camera, index);
  card.dataset.ready = "false";
  card.dataset.unavailable = "false";
  cameraCards.push(card);
  const region = regions.find((entry) => entry.resorts.includes(camera.resort));
  cameraRegions.get(region.name).grid.append(card);
});

const resortCount = new Set(cameraCatalog.map((camera) => camera.resort)).size;
document.querySelector("#camera-summary").textContent = `${cameraCatalog.length} CAMERAS · ${resortCount} COLORADO RESORTS`;
document.querySelector("#brief-lead").textContent = `${cameraCatalog.length} resort cameras across ${resortCount} Colorado resorts. Direct views from the official sources. No invented snow totals.`;
document.querySelector("#report-summary").textContent = `${resortCount} RESORTS · MEASUREMENTS`;

function updateRegionVisibility() {
  cameraRegions.forEach(({ section }) => {
    section.hidden = !section.querySelector(".camera-panel:not([hidden])");
  });
}

function paintClock() {
  const now = new Date();
  document.querySelector("#mountain-time").textContent = clockFmt.format(now);
  document.querySelector("#mountain-date").textContent = dateFmt.format(now).toUpperCase();
}

function updateFeedCount() {
  const eligible = cameraCards.filter((card) => card.dataset.unavailable !== "true" && (activeResort === "all" || card.dataset.resort === activeResort));
  const imageReady = eligible.filter((card) => card.querySelector("img.live-image") && card.dataset.ready === "true" && card.dataset.unavailable !== "true").length;
  document.querySelector("#feed-count").textContent = `${eligible.length} CAMERAS LISTED`;
  document.querySelector("#feed-detail").textContent = window.location.protocol === "file:"
    ? "Local preview · use hosted page for embeds"
    : imageReady > 0
      ? `${imageReady} still image${imageReady === 1 ? "" : "s"} checked · Video at source`
      : "Video playback varies by resort";
}

function hideUnavailable(card, reason) {
  card.dataset.ready = "false";
  card.dataset.unavailable = "true";
  card.querySelectorAll(".source-dot").forEach((dot) => dot.classList.remove("is-ready"));
  card.hidden = true;
  card.setAttribute("aria-hidden", "true");
  card.dataset.failureReason = reason;
  updateRegionVisibility();
  updateFeedCount();
}

function markReady(card) {
  if (card.dataset.unavailable === "true") return;
  card.dataset.ready = "true";
  card.querySelectorAll(".source-dot").forEach((dot) => dot.classList.add("is-ready"));
  updateFeedCount();
}

function setImageCheck(card) {
  const label = card.querySelector(".image-checked");
  if (label) label.textContent = shortTimeFmt.format(new Date());
}

function prepareImage(card) {
  const image = card.querySelector("img.live-image");
  if (!image) return;
  image.addEventListener("load", () => {
    setImageCheck(card);
    markReady(card);
  });
  image.addEventListener("error", () => hideUnavailable(card, "image request failed"));
  if (image.complete && image.naturalWidth > 0) {
    setImageCheck(card);
    markReady(card);
  }
}

function applyResortFilter() {
  activeResort = resortFilter.value;
  cameraCards.forEach((card) => {
    const unavailable = card.dataset.unavailable === "true";
    card.hidden = unavailable || (activeResort !== "all" && card.dataset.resort !== activeResort);
    card.setAttribute("aria-hidden", String(card.hidden));
  });
  updateRegionVisibility();
  updateFeedCount();
}

function refreshCamera(card) {
  card.dataset.unavailable = "false";
  card.dataset.ready = "false";
  card.querySelectorAll(".source-dot").forEach((dot) => dot.classList.remove("is-ready"));
  const frame = card.querySelector("iframe");
  const image = card.querySelector("img.live-image");
  if (frame && !card.hidden) {
    frame.src = frame.src;
  }
  if (image && !card.hidden) {
    const url = new URL(image.dataset.source);
    url.searchParams.set("refresh", Date.now());
    image.src = url.href;
  }
  updateFeedCount();
}

populateResortFilter();
cameraCards.forEach((card) => {
  prepareImage(card);
});
resortFilter.addEventListener("change", applyResortFilter);

cameraOnlyButton.addEventListener("click", () => {
  const active = cameraOnlyButton.getAttribute("aria-pressed") !== "true";
  cameraOnlyButton.setAttribute("aria-pressed", String(active));
  document.body.classList.toggle("camera-only", active);
});

document.querySelectorAll(".expand-button").forEach((button) => {
  if (window.location.protocol === "file:") {
    button.hidden = true;
    return;
  }
  button.addEventListener("click", async () => {
    const frame = button.closest(".camera-frame");
    try {
      if (document.fullscreenElement) await document.exitFullscreen();
      else await frame.requestFullscreen();
    } catch {
      button.setAttribute("aria-label", "Fullscreen is unavailable for this camera");
    }
  });
});

document.querySelector("#refresh-all").addEventListener("click", (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.classList.add("refreshing");
  cameraCards.filter((card) => !card.hidden).forEach(refreshCamera);
  window.setTimeout(() => {
    button.disabled = false;
    button.classList.remove("refreshing");
    updateFeedCount();
  }, 2200);
});

paintClock();
window.setInterval(paintClock, 15000);
window.setInterval(() => {
  cameraCards.filter((card) => card.querySelector("img.live-image") && !card.hidden && card.dataset.unavailable !== "true").forEach(refreshCamera);
}, 5 * 60 * 1000);
updateFeedCount();
