const cameraCatalog = window.powderlineCameraCatalog || [];
const resortCatalog = window.powderlineResortCatalog || [];
const snapshotTools = window.powderlineSnapshotTools;
let snapshotManifest = window.powderlineSnapshots || { cameras: {} };
const cachedSnapshot = (id) => snapshotTools.valid(id, snapshotManifest.cameras?.[id]) ? snapshotManifest.cameras[id] : null;
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

function createCameraCard(camera, index) {
  const card = makeElement("article", "camera-panel");
  card.dataset.resort = camera.resort;
  card.dataset.cameraId = camera.id;
  card.dataset.directory = String(Boolean(camera.directory));
  card.dataset.provider = camera.provider;

  const snapshot = cachedSnapshot(camera.id);
  const frame = makeElement("div", `camera-frame${camera.provider === "image" ? " image-frame" : " preview-frame"}`);
  // Public snapshots are the in-page view. Third-party playback may fail even
  // when the iframe fires load, so it must never replace a usable image.
  if (snapshot) {
    const image = makeElement("img", "live-image");
    image.src = snapshotTools.url(snapshot, document.baseURI);
    image.dataset.source = image.src;
    rememberSnapshot(card, snapshot);
    image.alt = `${camera.resort} ${camera.name} latest available camera image`;
    image.loading = "lazy";
    frame.append(image);
  }

  const fallback = makeElement("div", "camera-fallback");
  fallback.hidden = Boolean(snapshot);
  fallback.append(
    makeElement("strong", "", camera.directory ? "No verified public webcam" : "Camera currently unavailable"),
    makeElement("p", "", camera.note || "This camera has not supplied a usable snapshot yet. The player or official camera source may still be available."),
    makeExternalLink(camera.playerUrl || camera.source, camera.directory ? "SKI AREA WEBSITE ↗" : "OPEN RESORT CAMERAS ↗")
  );
  frame.append(fallback);
  frame.append(makeElement("span", "frame-index", camera.directory ? "SKI AREA INFO" : `CAM ${String(index + 1).padStart(2, "0")} / ${cameraCatalog.length}`));
  const expand = makeElement("button", "expand-button", "⛶");
  expand.type = "button";
  expand.setAttribute("aria-label", `Expand ${camera.resort} ${camera.name} camera`);
  if (!snapshot) expand.hidden = true;
  frame.append(expand, makeElement("span", "frame-category", camera.kind));
  if (camera.refreshNote) frame.append(makeElement("span", "image-refresh-note", camera.refreshNote));
  const badge = makeElement("span", "snapshot-badge", "CACHED · HOURLY");
  badge.hidden = !snapshot;
  frame.append(badge);
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
  const imageStatus = makeElement("span", "image-status");
  imageStatus.hidden = !snapshot;
  imageStatus.append(makeElement("span", "image-kind", snapshot ? "CACHED IMAGE " : "IMAGE CHECKED "), makeElement("time", "image-checked", "—"), document.createElement("br"));
  sourceDetails.append(imageStatus);
  sourceDetails.append(makeExternalLink(camera.playerUrl || (camera.provider === "image" ? camera.source : camera.src), camera.provider === "link" ? "SOURCE WEBSITE ↗" : camera.provider === "image" ? "CAMERA SOURCE ↗" : "LIVE SOURCE ↗"));
  sourceDetails.append(document.createElement("br"), makeExternalLink(camera.source, "RESORT CAMS ↗"));
  source.append(sourceDetails);
  caption.append(source);
  card.append(caption);
  return card;
}

function populateResortFilter() {
  const counts = new Map();
  resortFilter.replaceChildren();
  orderedCameras.forEach((camera) => counts.set(camera.resort, (counts.get(camera.resort) || 0) + 1));
  const allOption = makeElement("option", "", `All resorts · ${cameraCatalog.length} cameras`);
  allOption.value = "all";
  resortFilter.append(allOption);
  resortCatalog.forEach((resort) => {
    const count = counts.get(resort.name) || 0;
    const captured = cameraCatalog.filter((camera) => camera.resort === resort.name && cachedSnapshot(camera.id)).length;
    const option = makeElement("option", "", `${resort.name} · ${count ? `${captured}/${count} images` : "no verified webcam"}`);
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
  const unavailable = makeElement("details", "unavailable-cameras");
  const summary = makeElement("summary");
  const unavailableGrid = makeElement("div", "camera-group-grid");
  unavailable.append(summary, unavailableGrid);
  section.append(heading, grid, unavailable);
  cameraWall.append(section);
  cameraRegions.set(region.name, { section, grid, unavailable, unavailableGrid, summary });
});

orderedCameras.forEach((camera, index) => {
  const card = createCameraCard(camera, index);
  card.dataset.ready = "false";
  card.dataset.unavailable = "false";
  cameraCards.push(card);
  const region = regions.find((entry) => entry.resorts.includes(camera.resort));
  const target = cameraRegions.get(region.name);
  (cachedSnapshot(camera.id) ? target.grid : target.unavailableGrid).append(card);
});

resortCatalog.filter((resort) => !cameraCatalog.some((camera) => camera.resort === resort.name)).forEach((resort) => {
  const card = createCameraCard({
    id: `directory-${resort.name.toLowerCase().replace(/[^a-z0-9]+/g, "-")}`,
    resort: resort.name, name: "Webcam availability", kind: "SKI AREA", provider: "link",
    src: resort.source, source: resort.source, directory: true,
    note: resort.note || "No public mountain webcam was found during the latest source review. Check the ski area’s website for updates.",
  }, 0);
  cameraCards.push(card);
  cameraRegions.get(resort.region).unavailableGrid.append(card);
});

const resortCount = resortCatalog.length;
document.querySelector("#camera-summary").textContent = `${cameraCatalog.length} CAMERAS · ${resortCount} COLORADO SKI AREAS`;
document.querySelector("#brief-lead").textContent = `Explore ${resortCount} Colorado ski areas. Camera snapshots update hourly, with the last successful image kept visible between updates. Browse by region or choose your mountain.`;
document.querySelector("#report-summary").textContent = `${document.querySelectorAll("#resort-report tbody tr").length} RESORTS · MEASUREMENTS`;

function updateRegionVisibility() {
  cameraCards.forEach((card) => {
    const region = regions.find((entry) => entry.resorts.includes(card.dataset.resort));
    const target = cameraRegions.get(region.name);
    const grid = cachedSnapshot(card.dataset.cameraId) && card.querySelector("img.live-image") ? target.grid : target.unavailableGrid;
    if (card.parentElement !== grid) grid.append(card);
  });
  cameraRegions.forEach(({ section, unavailable, unavailableGrid, summary }) => {
    section.hidden = !section.querySelector(".camera-panel:not([hidden])");
    const cards = [...unavailableGrid.querySelectorAll(".camera-panel:not([hidden])")];
    const areas = cards.filter((card) => card.dataset.directory === "true").length;
    const cameras = cards.length - areas;
    unavailable.hidden = cards.length === 0;
    summary.textContent = [cameras ? `${cameras} camera${cameras === 1 ? "" : "s"} currently unavailable` : "", areas ? `${areas} ski area${areas === 1 ? "" : "s"} without a verified feed` : ""].filter(Boolean).join(" · ");
    unavailable.open = activeResort !== "all";
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
  const sourceOnly = eligible.filter((card) => card.dataset.provider === "link" && !card.querySelector("img.live-image")).length;
  const cached = eligible.filter((card) => card.dataset.snapshotFetchedAt).length;
  const totalCached = cameraCatalog.filter((camera) => cachedSnapshot(camera.id)).length;
  document.querySelector("#camera-summary").textContent = `${totalCached} CACHED IMAGES · ${cameraCatalog.length} CAMERA LISTINGS · ${resortCount} SKI AREAS`;
  const unavailable = eligible.filter((card) => card.dataset.unavailable === "true").length;
  document.querySelector("#feed-count").textContent = `${eligible.length} CAMERAS LISTED`;
  document.querySelector("#feed-detail").textContent = eligible.length
    ? `${imageReady} images loaded · ${cached} cached${sourceOnly ? ` · ${sourceOnly} source links` : ""}${unavailable ? ` · ${unavailable} previews unavailable` : ""}`
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

function rememberSnapshot(card, entry) {
  card.dataset.snapshotFetchedAt = entry.fetchedAt;
  card.dataset.snapshotChangedAt = entry.changedAt || entry.fetchedAt;
  card.dataset.snapshotStatus = entry.status;
  card.dataset.snapshotSha = entry.sha256 || entry.fetchedAt;
  card.dataset.snapshotMethod = entry.method;
}

function setImageCheck(card) {
  const label = card.querySelector(".image-checked");
  if (!label) return;
  if (card.dataset.snapshotFetchedAt) {
    const entry = { fetchedAt: card.dataset.snapshotFetchedAt, status: card.dataset.snapshotStatus };
    const stale = snapshotTools.stale(entry);
    label.textContent = `${snapshotTools.age(entry.fetchedAt)}${stale ? " · Last good image" : ""}`;
    label.dateTime = entry.fetchedAt;
    label.title = `Fetched: ${new Date(entry.fetchedAt).toLocaleString()}. Image last changed: ${new Date(card.dataset.snapshotChangedAt).toLocaleString()}. The source’s capture time may differ.`;
    card.classList.toggle("snapshot-stale", stale);
    card.querySelector(".image-kind").textContent = "";
    card.querySelector(".snapshot-badge").hidden = false;
    card.querySelector(".snapshot-badge").textContent = card.dataset.snapshotMethod === "provider-preview" ? "SOURCE PREVIEW · HOURLY" : "CACHED · HOURLY";
    const note = card.querySelector(".image-refresh-note");
    if (note) note.hidden = true;
  } else {
    label.textContent = shortTimeFmt.format(new Date());
  }
}

function prepareImage(card) {
  const image = card.querySelector("img.live-image");
  if (!image || image.dataset.prepared) return;
  image.dataset.prepared = "true";
  image.addEventListener("load", () => {
    setImageCheck(card);
    markReady(card);
  });
  image.addEventListener("error", () => {
    showUnavailable(card, "Cached image request failed; use Refresh to retry.");
  });
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
  cameraCards.filter((card) => !card.hidden && cachedSnapshot(card.dataset.cameraId)).forEach((card) => applySnapshot(card, cachedSnapshot(card.dataset.cameraId)));
}

function applySnapshot(card, entry) {
  if (card.hidden || !snapshotTools.valid(card.dataset.cameraId, entry)) return Promise.resolve();
  if (card.dataset.snapshotSha === (entry.sha256 || entry.fetchedAt) && card.dataset.ready === "true") {
    rememberSnapshot(card, entry);
    setImageCheck(card);
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const url = snapshotTools.url(entry, document.baseURI);
    const nextImage = new Image();
    nextImage.onload = () => {
      let image = card.querySelector("img.live-image");
      if (!image) {
        image = makeElement("img", "live-image");
        image.alt = `${card.dataset.resort} latest available camera snapshot`;
        card.querySelector(".camera-frame").prepend(image);
        prepareImage(card);
      }
      rememberSnapshot(card, entry);
      image.dataset.source = url;
      image.src = url;
      card.querySelector(".image-status").hidden = false;
      card.querySelector(".expand-button").hidden = false;
      setImageCheck(card);
      markReady(card);
      resolve();
    };
    // Keep the currently visible image if the next deployment or request fails.
    nextImage.onerror = resolve;
    nextImage.src = url;
  });
}

function refreshCamera(card) {
  const snapshot = cachedSnapshot(card.dataset.cameraId);
  if (snapshot) return applySnapshot(card, snapshot);
  if (snapshotManifest.cameras?.[card.dataset.cameraId]?.status === "unavailable") {
    // A publisher-verified outage or rejected status graphic is not a last-good image.
    delete card.dataset.snapshotFetchedAt;
    card.querySelector("img.live-image")?.remove();
    card.querySelector(".snapshot-badge").hidden = true;
    card.querySelector(".image-status").hidden = true;
    card.querySelector(".expand-button").hidden = true;
    showUnavailable(card, "No usable source image");
  }
  return Promise.resolve();
}

async function refreshWall() {
  try {
    const response = await fetch(new URL("./snapshots/manifest.json", document.baseURI), { cache: "no-store" });
    if (response.ok) {
      const latest = await response.json();
      if (latest.cameras && typeof latest.cameras === "object") {
        snapshotManifest = latest;
        populateResortFilter();
        resortFilter.value = activeResort;
      }
    }
  } catch { /* Local previews or temporary outages keep the current images. */ }
  await Promise.allSettled(cameraCards.filter((card) => !card.hidden).map(refreshCamera));
  updateRegionVisibility();
  updateFeedCount();
}

populateResortFilter();
updateRegionVisibility();
cameraCards.forEach((card) => {
  prepareImage(card);
  if (card.dataset.snapshotFetchedAt) setImageCheck(card);
});
resortFilter.addEventListener("change", applyResortFilter);

cameraOnlyButton.addEventListener("click", () => {
  const active = cameraOnlyButton.getAttribute("aria-pressed") !== "true";
  cameraOnlyButton.setAttribute("aria-pressed", String(active));
  document.body.classList.toggle("camera-only", active);
});

const imageDialog = makeElement("dialog", "camera-dialog");
imageDialog.setAttribute("aria-labelledby", "expanded-camera-title");
const dialogTitle = makeElement("h2");
dialogTitle.id = "expanded-camera-title";
const dialogClose = makeElement("button", "dialog-close", "Close image ×");
dialogClose.type = "button";
dialogClose.addEventListener("click", () => imageDialog.close());
const expandedImage = makeElement("img");
const dialogAge = makeElement("p", "dialog-age");
imageDialog.append(dialogTitle, dialogClose, expandedImage, dialogAge);
document.body.append(imageDialog);
imageDialog.addEventListener("click", (event) => {
  if (event.target !== imageDialog) return;
  const bounds = imageDialog.getBoundingClientRect();
  if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) imageDialog.close();
});
document.querySelectorAll(".expand-button").forEach((button) => {
  button.addEventListener("click", () => {
    const card = button.closest(".camera-panel");
    const image = card.querySelector("img.live-image");
    if (!image || !image.naturalWidth) return;
    dialogTitle.textContent = `${card.dataset.resort} · ${card.querySelector(".camera-name").textContent}`;
    expandedImage.src = image.currentSrc || image.src;
    expandedImage.alt = image.alt;
    dialogAge.textContent = card.querySelector(".image-checked").textContent;
    imageDialog.showModal();
  });
});

document.querySelector("#refresh-all").addEventListener("click", async (event) => {
  const button = event.currentTarget;
  button.disabled = true;
  button.classList.add("refreshing");
  try { await refreshWall(); }
  finally {
    button.disabled = false;
    button.classList.remove("refreshing");
  }
});

paintClock();
window.setInterval(paintClock, 15000);
window.setInterval(refreshWall, 15 * 60 * 1000);
window.setInterval(() => {
  cameraCards.filter((card) => card.dataset.snapshotFetchedAt).forEach(setImageCheck);
}, 60 * 1000);
updateFeedCount();
