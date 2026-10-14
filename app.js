const cameraCatalog = window.powderlineCameraCatalog || [];
const cameraWall = document.querySelector("#camera-wall");
const resortFilter = document.querySelector("#resort-filter");
const cameraOnlyButton = document.querySelector("#camera-only");
const cameraCards = [];
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

  const frame = makeElement("div", `camera-frame${camera.provider === "image" ? " image-frame" : ""}`);
  if (camera.provider === "image") {
    const image = makeElement("img", "live-image");
    image.src = camera.src;
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
    const player = makeElement("iframe");
    player.title = `${camera.resort} ${camera.name} camera`;
    player.src = camera.src;
    player.loading = "lazy";
    player.allow = "autoplay; fullscreen";
    player.allowFullscreen = true;
    player.referrerPolicy = "strict-origin-when-cross-origin";
    frame.append(player);
  }

  frame.append(makeElement("span", "frame-index", `CAM ${String(index + 1).padStart(2, "0")} / ${cameraCatalog.length}`));
  const expand = makeElement("button", "expand-button", "⛶");
  expand.type = "button";
  expand.setAttribute("aria-label", `Expand ${camera.resort} ${camera.name} camera`);
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
  sourceDetails.append(makeExternalLink(camera.src, "OPEN PLAYER ↗"));
  sourceDetails.append(document.createElement("br"), makeExternalLink(camera.source, "RESORT CAMS ↗"));
  source.append(sourceDetails);
  caption.append(source);
  card.append(caption);
  return card;
}

function populateResortFilter() {
  const counts = new Map();
  cameraCatalog.forEach((camera) => counts.set(camera.resort, (counts.get(camera.resort) || 0) + 1));
  const allOption = makeElement("option", "", `All resorts · ${cameraCatalog.length} cameras`);
  allOption.value = "all";
  resortFilter.append(allOption);
  counts.forEach((count, resort) => {
    const option = makeElement("option", "", `${resort} · ${count} cameras`);
    option.value = resort;
    resortFilter.append(option);
  });
}

cameraCatalog.forEach((camera, index) => {
  const card = createCameraCard(camera, index);
  card.dataset.ready = "false";
  card.dataset.unavailable = "false";
  cameraCards.push(card);
  cameraWall.append(card);
});

function paintClock() {
  const now = new Date();
  document.querySelector("#mountain-time").textContent = clockFmt.format(now);
  document.querySelector("#mountain-date").textContent = dateFmt.format(now).toUpperCase();
}

function updateFeedCount() {
  const eligible = cameraCards.filter((card) => activeResort === "all" || card.dataset.resort === activeResort);
  const imageReady = eligible.filter((card) => card.querySelector("img.live-image") && card.dataset.ready === "true" && card.dataset.unavailable !== "true").length;
  document.querySelector("#feed-count").textContent = window.location.protocol === "file:"
    ? `LOCAL PREVIEW · ${eligible.length} CAMERAS`
    : `${eligible.length} CAMERAS · ${imageReady} IMAGE FEED${imageReady === 1 ? "" : "S"} VERIFIED`;
}

function hideUnavailable(card, reason) {
  card.dataset.ready = "false";
  card.dataset.unavailable = "true";
  card.querySelectorAll(".source-dot").forEach((dot) => dot.classList.remove("is-ready"));
  card.hidden = true;
  card.setAttribute("aria-hidden", "true");
  card.dataset.failureReason = reason;
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

function prepareFrame(card) {
  const frame = card.querySelector("iframe");
  if (!frame) return;
  // iframe load only confirms the frame navigation completed; cross-origin
  // policy prevents us from verifying that video is actually playing.
}

function applyResortFilter() {
  activeResort = resortFilter.value;
  cameraCards.forEach((card) => {
    const unavailable = card.dataset.unavailable === "true";
    card.hidden = unavailable || (activeResort !== "all" && card.dataset.resort !== activeResort);
    card.setAttribute("aria-hidden", String(card.hidden));
  });
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
    image.addEventListener("load", () => {
      setImageCheck(card);
      markReady(card);
    }, { once: true });
    image.addEventListener("error", () => hideUnavailable(card, "image refresh failed"), { once: true });
    const base = image.src.split("?")[0];
    image.src = `${base}?refresh=${Date.now()}`;
  }
  updateFeedCount();
}

populateResortFilter();
cameraCards.forEach((card) => {
  prepareImage(card);
  prepareFrame(card);
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

const planCards = document.querySelector("#plan-cards");
const planPreviewStatus = document.querySelector("#plan-preview-status");
document.querySelectorAll("[data-plan-select]").forEach((button) => {
  button.addEventListener("click", () => {
    const selectedPlan = button.dataset.planSelect;
    planCards.dataset.planMode = selectedPlan;
    document.querySelectorAll("[data-plan-select]").forEach((planButton) => {
      const selected = planButton === button;
      planButton.setAttribute("aria-pressed", String(selected));
      planButton.closest(".plan-card").classList.toggle("is-selected", selected);
    });
    planPreviewStatus.textContent = selectedPlan === "pro"
      ? "Pro preview selected. The watchlist, snowfall history, and alerts shown here are future concepts and are not active."
      : "Free preview selected. Everything currently on Powderline stays available without an account.";
  });
});

paintClock();
window.setInterval(paintClock, 15000);
window.setInterval(() => {
  const keystoneStake = document.querySelector('[data-camera-id="keystone-snow-stake"]');
  if (keystoneStake && !keystoneStake.hidden && keystoneStake.dataset.unavailable !== "true") refreshCamera(keystoneStake);
}, 5 * 60 * 1000);
updateFeedCount();
