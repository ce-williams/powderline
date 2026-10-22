const cameraCatalog = window.powderlineCameraCatalog || [];
const resortCatalog = window.powderlineResortCatalog || [];
const regions = [...new Set(resortCatalog.map((resort) => resort.region))].map((name) => ({
  name, resorts: resortCatalog.filter((resort) => resort.region === name).map((resort) => resort.name),
}));
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
  player.addEventListener("load", () => frame.classList.add("player-loaded"), { once: true });
  frame.classList.remove("player-pending");
  frame.querySelector(".player-entry")?.remove();
  frame.prepend(player);
  const stillButton = makeElement("button", "show-still-button", "Show last image");
  stillButton.type = "button";
  stillButton.addEventListener("click", () => {
    const showStill = frame.classList.toggle("show-still");
    stillButton.textContent = showStill ? "Resume player" : "Show last image";
    stillButton.setAttribute("aria-pressed", String(showStill));
  });
  if (frame.querySelector("img.live-image")) frame.append(stillButton);
  frame.querySelector(".expand-button").hidden = false;
}

function createCameraCard(camera, index) {
  const card = makeElement("article", "camera-panel");
  card.dataset.resort = camera.resort;
  card.dataset.cameraId = camera.id;
  card.dataset.directory = String(Boolean(camera.directory));
  card.dataset.provider = camera.provider;

  const frame = makeElement("div", `camera-frame${camera.provider === "image" ? " image-frame" : " preview-frame"}`);
  if (camera.provider === "image" || camera.previewSrc) {
    const image = makeElement("img", "live-image");
    image.src = camera.previewSrc || camera.src;
    image.dataset.source = image.src;
    image.alt = `${camera.resort} ${camera.name} latest available camera image`;
    image.loading = "lazy";
    image.referrerPolicy = "strict-origin-when-cross-origin";
    frame.append(image);
  }
  if (camera.provider === "link") {
    // Source-only cameras remain accessible without loading a blocked player.
  } else if (camera.provider === "image") {
    // The latest still is the camera view; no video player is needed.
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
    entry.append(makeElement("span", "player-entry-label", camera.previewSrc ? "LATEST SOURCE IMAGE" : "CAMERA ON REQUEST"));
    const load = makeElement("button", "load-player", "Load camera player →");
    load.type = "button";
    load.setAttribute("aria-label", `Load ${camera.resort} ${camera.name} camera`);
    load.addEventListener("click", () => loadPlayer(frame, camera), { once: true });
    entry.append(load);
    frame.append(entry);
  }

  const fallback = makeElement("div", "camera-fallback");
  fallback.hidden = camera.provider !== "link";
  fallback.append(
    makeElement("strong", "", camera.directory ? "Webcam not available" : "View on resort website"),
    makeElement("p", "", camera.note || "This preview could not be loaded. You can still open the official camera source."),
    makeExternalLink(camera.playerUrl || camera.source, camera.directory ? "SKI AREA WEBSITE ↗" : "OPEN RESORT CAMERAS ↗")
  );
  frame.append(fallback);
  frame.append(makeElement("span", "frame-index", camera.directory ? "SKI AREA INFO" : `CAM ${String(index + 1).padStart(2, "0")} / ${cameraCatalog.length}`));
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
  if (camera.provider === "image" || camera.previewSrc) {
    sourceDetails.append(document.createTextNode("IMAGE CHECKED "), makeElement("time", "image-checked", "—"), document.createElement("br"));
  }
  sourceDetails.append(makeExternalLink(camera.playerUrl || (camera.provider === "image" ? camera.source : camera.src), camera.provider === "link" ? "OPEN WEBSITE ↗" : camera.provider === "image" ? "OPEN CAM ↗" : "OPEN PLAYER ↗"));
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
  resortCatalog.forEach((resort) => {
    const count = counts.get(resort.name) || 0;
    const option = makeElement("option", "", `${resort.name} · ${count ? `${count} camera${count === 1 ? "" : "s"}` : "source info"}`);
    option.value = resort.name;
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

resortCatalog.filter((resort) => !cameraCatalog.some((camera) => camera.resort === resort.name)).forEach((resort) => {
  const card = createCameraCard({
    id: `directory-${resort.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    resort: resort.name, name: "Webcam availability", kind: "SKI AREA", provider: "link",
    src: resort.source, source: resort.source, directory: true,
    note: resort.note || "No public mountain webcam was found during the latest source review. Check the ski area’s website for updates.",
  }, 0);
  cameraCards.push(card);
  cameraRegions.get(resort.region).grid.append(card);
});

const resortCount = resortCatalog.length;
const previewCount = cameraCatalog.filter((camera) => camera.provider !== "link").length;
const sourceOnlyCount = cameraCatalog.length - previewCount;
document.querySelector("#camera-summary").textContent = `${cameraCatalog.length} CAMERAS · ${resortCount} COLORADO SKI AREAS`;
document.querySelector("#brief-lead").textContent = `Explore ${resortCount} Colorado ski areas: ${previewCount} camera views on the wall and ${sourceOnlyCount} cameras on official resort sites. Every ski area stays within reach.`;
document.querySelector("#report-summary").textContent = `${document.querySelectorAll("#resort-report tbody tr").length} RESORTS · MEASUREMENTS`;

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
  const eligible = cameraCards.filter((card) => card.dataset.directory !== "true" && (activeResort === "all" || card.dataset.resort === activeResort));
  const imageReady = eligible.filter((card) => card.querySelector("img.live-image") && card.dataset.ready === "true").length;
  const sourceOnly = eligible.filter((card) => card.dataset.provider === "link").length;
  const unavailable = eligible.filter((card) => card.dataset.unavailable === "true").length;
  document.querySelector("#feed-count").textContent = `${eligible.length} CAMERAS LISTED`;
  document.querySelector("#feed-detail").textContent = eligible.length
    ? `${imageReady} images loaded · ${sourceOnly} on resort sites${unavailable ? ` · ${unavailable} previews unavailable` : ""}`
    : "No public webcam found · Ski area website available below";
}

function showUnavailable(card, reason) {
  card.dataset.ready = "false";
  card.dataset.unavailable = "true";
  card.dataset.failureReason = reason;
  card.querySelectorAll(".source-dot").forEach((dot) => dot.classList.remove("is-ready"));
  card.querySelector(".camera-fallback").hidden = false;
  const image = card.querySelector("img.live-image");
  if (image) image.hidden = true;
  updateFeedCount();
}

function markReady(card) {
  card.dataset.ready = "true";
  card.dataset.unavailable = "false";
  delete card.dataset.failureReason;
  card.querySelector(".camera-fallback").hidden = true;
  const image = card.querySelector("img.live-image");
  if (image) image.hidden = false;
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
  image.addEventListener("error", () => showUnavailable(card, "image request failed"));
  if (image.complete && image.naturalWidth > 0) {
    setImageCheck(card);
    markReady(card);
  }
}

function applyResortFilter() {
  activeResort = resortFilter.value;
  cameraCards.forEach((card) => {
    card.hidden = activeResort !== "all" && card.dataset.resort !== activeResort;
    card.setAttribute("aria-hidden", String(card.hidden));
  });
  updateRegionVisibility();
  updateFeedCount();
}

function refreshCamera(card) {
  const frame = card.querySelector("iframe");
  const image = card.querySelector("img.live-image");
  if (frame && !card.hidden) {
    frame.src = frame.src;
  }
  if (image && !card.hidden) {
    const url = new URL(image.dataset.source);
    url.searchParams.set("refresh", Date.now());
    const nextImage = new Image();
    nextImage.referrerPolicy = "strict-origin-when-cross-origin";
    nextImage.onload = () => {
      image.src = url.href;
      setImageCheck(card);
      markReady(card);
    };
    // If a fresh request fails, keep the last image that loaded successfully.
    nextImage.onerror = () => {
      if (card.dataset.ready !== "true") showUnavailable(card, "image request failed");
    };
    nextImage.src = url.href;
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
  cameraCards.filter((card) => card.querySelector("img.live-image") && !card.hidden).forEach(refreshCamera);
}, 5 * 60 * 1000);
updateFeedCount();
