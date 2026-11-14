(function (root) {
  const MAX_REPORT = 72 * 3600000;
  const MAX_IMAGE = 30 * 86400000;
  const timestamp = (value, max, now = Date.now()) => {
    const t = Date.parse(value);
    return Number.isFinite(t) && t <= now + 300000 && now - t <= max;
  };
  const https = (value) => typeof value === "string" && /^https:\/\//.test(value);
  const imagePath = (value) => typeof value === "string" && /^satellite\/[a-z0-9-]+\.(jpg|webp)$/.test(value);
  const validView = (view) => view === undefined || (Array.isArray(view) && view.length === 4 &&
    view.every((v) => typeof v === "number" && Number.isFinite(v)) && view[0] >= 0 && view[1] >= 0 &&
    view[2] > 0 && view[3] > 0 && view[0]+view[2] <= 1.000001 && view[1]+view[3] <= 1.000001);
  const stamp = (value) => new Intl.DateTimeFormat("en-US", {timeZone: "America/Denver", month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"}).format(new Date(value));
  const today = (value) => new Date(value).toLocaleDateString("en-CA", {timeZone: "America/Denver"}) === new Date().toLocaleDateString("en-CA", {timeZone: "America/Denver"});
  const usableRead = (row, now = Date.now()) => row && typeof row.summary === "string" && row.summary.length <= 850 &&
    timestamp(row.generatedAt, 18 * 3600000, now) && Array.isArray(row.sources) &&
    row.sources.length > 0 && row.sources.every((s) => https(s.url) && timestamp(s.reportedAt, s.kind === "forecast" ? 18 * 3600000 : MAX_REPORT, now));
  const usableImage = (row, now = Date.now()) => row && imagePath(row.image) && validView(row.view) && https(row.source) && timestamp(row.capturedAt, MAX_IMAGE, now);
  const project = (coordinate, bbox) => [(coordinate[0]-bbox[0])/(bbox[2]-bbox[0])*1000, (bbox[3]-coordinate[1])/(bbox[3]-bbox[1])*1000];
  root.powderlineIntelTools = {timestamp, imagePath, validView, usableRead, usableImage, project};
  if (typeof document === "undefined") return;
  let satellite = {resorts: {}}, conditions = {resorts: {}}, lifts = {resorts: {}};
  const catalog = root.powderlineResortCatalog || [];
  const select = document.querySelector("#intel-resort");
  const view = document.querySelector("#intel-view");
  const gallery = document.querySelector("#satellite-gallery");
  function el(tag, className, text) {
    const node = document.createElement(tag);
    node.className = className || "";
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function link(url, text) {
    const a = el("a", "", text);
    a.href = url; a.target = "_blank"; a.rel = "noopener noreferrer";
    return a;
  }
  const all = el("option", "", `All ${catalog.length} resorts`); all.value = "all"; select.append(all);
  catalog.forEach((r) => {
    const option = el("option", "", r.name); option.value = r.name; select.append(option);
  });
  select.value = "all";
  function imageUrl(scene) {
    // Hash-named assets are stable across builds. Legacy JPEGs retain scene keys.
    return new URL(scene.image+(scene.image.endsWith('.webp') ? '' : "?scene="+encodeURIComponent(scene.sceneId || scene.capturedAt)), document.baseURI).href;
  }
  function showCrop(frame, img, scene, zoom = 1) {
    const [x, y, w, h] = scene.view || [0, 0, 1, 1];
    img.classList.add("satellite-crop-image");
    img.style.width = `${100*zoom/w}%`; img.style.height = `${100*zoom/h}%`;
    img.style.left = `${50-(x+w/2)*100*zoom/w}%`; img.style.top = `${50-(y+h/2)*100*zoom/h}%`;
    frame.append(img);
  }
  function orientationMark(frame) {
    frame.querySelector('.satellite-north')?.remove();
    const mark = el('div', 'satellite-north');
    mark.setAttribute('aria-label', 'North is up; east is right');
    mark.append(el('strong', '', 'N ↑'), el('span', '', 'NORTH UP · E →')); frame.append(mark);
  }
  const liftName = (route) => route.name === 'Mapped lift' ? `${route.type === 'chair_lift' ? 'Chairlift' : 'Lift'} (name unavailable)` : route.name;
  function liftOverlay(frame, scene, routes, zoom = 1) {
    frame.querySelector('.lift-overlay')?.remove();
    if (!Array.isArray(scene.bbox) || scene.bbox.length !== 4 || !routes.length) return;
    const ns = 'http://www.w3.org/2000/svg';
    const svg = document.createElementNS(ns, 'svg'); svg.classList.add('lift-overlay');
    svg.setAttribute('viewBox', '0 0 1000 1000'); svg.setAttribute('preserveAspectRatio', 'none'); svg.setAttribute('aria-hidden', 'true');
    routes.slice(0, 1).forEach((route) => {
      if (!Array.isArray(route.coordinates) || route.coordinates.length < 2) return;
      const points = route.coordinates.map((c) => project(c, scene.bbox)).map(([x, y]) => [500+(x-500)*zoom, 500+(y-500)*zoom]);
      const line = document.createElementNS(ns, 'polyline');
      line.setAttribute('points', points.map((p) => p.join(',')).join(' ')); line.setAttribute('vector-effect', 'non-scaling-stroke'); svg.append(line);
      // Anchor the name to the visible part of the line nearest the map center.
      const anchors = points.slice(1).map((b, i) => {
        const a = points[i], dx = b[0]-a[0], dy = b[1]-a[1];
        const t = Math.max(0, Math.min(1, ((500-a[0])*dx+(500-a[1])*dy)/(dx*dx+dy*dy || 1)));
        return [a[0]+t*dx, a[1]+t*dy];
      }).filter(([x, y]) => x >= 0 && x <= 1000 && y >= 0 && y <= 1000)
        .sort((a, b) => Math.hypot(a[0]-500, a[1]-500)-Math.hypot(b[0]-500, b[1]-500));
      if (!anchors.length) return;
      const [x, y] = anchors[0];
      const name = liftName(route);
      const width = Math.min(900, name.length*17+32), height = 62;
      const left = Math.max(24, Math.min(976-width, x+28)), top = Math.max(120, Math.min(870, y-90));
      const leader = document.createElementNS(ns, 'line'); leader.setAttribute('class', 'lift-label-leader');
      leader.setAttribute('x1', x); leader.setAttribute('y1', y); leader.setAttribute('x2', left+16); leader.setAttribute('y2', top+height/2); leader.setAttribute('vector-effect', 'non-scaling-stroke');
      const background = document.createElementNS(ns, 'rect'); background.setAttribute('x', left); background.setAttribute('y', top); background.setAttribute('width', width); background.setAttribute('height', height); background.setAttribute('rx', 8);
      const marker = document.createElementNS(ns, 'text'); marker.setAttribute('x', left+16); marker.setAttribute('y', top+42); marker.textContent = name;
      const title = document.createElementNS(ns, 'title'); title.textContent = `Main reference lift: ${name}`;
      svg.append(title, leader, background, marker);
    });
    frame.append(svg);
  }
  function renderGallery() {
    gallery.replaceChildren();
    const ready = catalog.filter((r) => usableImage(satellite.resorts?.[r.name])).length;
    const summary = el("p", "gallery-summary", `${ready}/${catalog.length} resort snapshots available · Choose a mountain to zoom in and read its conditions.`);
    gallery.append(summary);
    for (const region of [...new Set(catalog.map((r) => r.region))]) {
      const group = el("section", "satellite-region"); group.setAttribute("aria-label", `${region} satellite snapshots`);
      group.append(el("h3", "eyebrow", region.toUpperCase()));
      const grid = el("div", "satellite-gallery-grid");
      catalog.filter((r) => r.region === region).forEach((resort) => {
        const scene = satellite.resorts?.[resort.name];
        const card = el("button", "satellite-resort-card"); card.type = "button";
        card.setAttribute("aria-label", `View ${resort.name} satellite and conditions`);
        const preview = el("div", "satellite-thumb");
        if (usableImage(scene)) {
          const img = el("img"); img.alt = `${resort.name}, captured ${stamp(scene.capturedAt)}`;
          img.loading = "lazy"; img.decoding = "async"; img.width = 448; img.height = 448;
          if (imagePath(scene.thumbnail)) img.src = new URL(scene.thumbnail, document.baseURI).href;
          else { img.src = imageUrl(scene); showCrop(preview, img, scene); }
          img.addEventListener("error", () => preview.replaceChildren(el("span", "", "Preview unavailable · open resort")));
          preview.append(img);
          orientationMark(preview);
          liftOverlay(preview, scene, lifts.resorts?.[resort.name]?.routes || []);
        } else preview.append(el("span", "", "Awaiting a usable scene"));
        const caption = el("div", "satellite-thumb-caption");
        caption.append(el("strong", "", resort.name), el("span", "", usableImage(scene) ? `${scene.sensor} · ${stamp(scene.capturedAt)}` : "No recent usable image"), el("span", "gallery-open", "Zoom in & read conditions ↗"));
        card.append(preview, caption); card.addEventListener("click", () => root.powderlineIntel.select(resort.name)); grid.append(card);
      });
      group.append(grid); gallery.append(group);
    }
  }
  function render() {
    gallery.hidden = select.value !== "all";
    if (select.value === "all") {
      view.replaceChildren(); renderGallery(); renderTileLinks(); return;
    }
    const name = select.value, resort = catalog.find((r) => r.name === name);
    const scene = satellite.resorts?.[name], read = conditions.resorts?.[name];
    const routes = (lifts.resorts?.[name]?.routes || []).slice(0, 1);
    const layout = el("div", "intel-layout");
    const figure = el("figure", "satellite-panel");
    const frame = el("div", "satellite-frame");
    if (usableImage(scene)) {
      const img = el("img"); img.src = imageUrl(scene);
      img.alt = `${name} and surrounding terrain, ${scene.sensor} true-color satellite image acquired ${stamp(scene.capturedAt)}`;
      img.decoding = "async";
      img.addEventListener("error", () => {
        frame.replaceChildren(el("p", "satellite-empty", "Satellite image could not load. Open the scene source below."));
      });
      showCrop(frame, img, scene);
      const span = Number.isFinite(scene.spanKm) ? scene.spanKm : Array.isArray(scene.bbox) ? (scene.bbox[3]-scene.bbox[1])*111.32 : 10;
      orientationMark(frame);
      frame.append(el("span", "satellite-scale", `${span.toFixed(1)} KM ACROSS · TRUE COLOR`));
      let zoom = 1;
      let linesVisible = true;
      liftOverlay(frame, scene, routes, zoom);
      const zoomTools = el("div", "satellite-zoom-tools");
      const zoomOut = el("button", "", "−"), zoomIn = el("button", "", "+");
      zoomOut.type = zoomIn.type = "button"; zoomOut.setAttribute("aria-label", "Zoom satellite out"); zoomIn.setAttribute("aria-label", "Zoom satellite in");
      const zoomLabel = el("span", "", "1×");
      function changeZoom(next) {
        zoom = Math.max(1, Math.min(3, next)); showCrop(frame, img, scene, zoom);
        zoomLabel.textContent = `${zoom}×`; zoomOut.disabled = zoom === 1; zoomIn.disabled = zoom === 3;
        frame.querySelector('.satellite-scale').textContent = `${(span/zoom).toFixed(1)} KM ACROSS · ${zoom > 1 ? 'DIGITAL ZOOM' : 'TRUE COLOR'}`;
        liftOverlay(frame, scene, linesVisible ? routes : [], zoom);
      }
      zoomOut.addEventListener("click", () => changeZoom(zoom-1)); zoomIn.addEventListener("click", () => changeZoom(zoom+1)); zoomOut.disabled = true;
      zoomTools.append(zoomOut, zoomLabel, zoomIn); frame.append(zoomTools);
      const expand = el("button", "satellite-expand", "Expand image ⛶"); expand.type = "button";
      expand.addEventListener("click", () => {
        const dialog = document.querySelector("#satellite-dialog");
        dialog.querySelector("h2").textContent = `${name} · ${scene.sensor}`;
        const expanded = dialog.querySelector("img"); expanded.src = img.src; expanded.alt = img.alt;
        showCrop(dialog.querySelector('.satellite-dialog-frame'), expanded, scene, zoom);
        orientationMark(dialog.querySelector('.satellite-dialog-frame'));
        liftOverlay(dialog.querySelector('.satellite-dialog-frame'), scene, linesVisible ? routes : [], zoom);
        dialog.querySelector("p").textContent = `Captured ${stamp(scene.capturedAt)} · ${scene.attribution}. North up; ${(span/zoom).toFixed(1)} km across. Lift routes are map references, not current operating status.`;
        dialog.showModal();
      });
      frame.append(expand);
      if (routes.length) {
        const toggle = el('button', 'lift-toggle', 'Main lift on'); toggle.type = 'button'; toggle.setAttribute('aria-pressed', 'true');
        toggle.addEventListener('click', () => { linesVisible = !linesVisible; toggle.textContent = `Main lift ${linesVisible ? 'on' : 'off'}`; toggle.setAttribute('aria-pressed', String(linesVisible)); liftOverlay(frame, scene, linesVisible ? routes : [], zoom); });
        frame.append(toggle);
      }
    } else frame.append(el("p", "satellite-empty", "No usable satellite crop from the past 30 days. Clouds or source availability can delay imagery."));
    figure.append(frame);
    const caption = el("figcaption", "satellite-caption");
    if (usableImage(scene)) {
      const age = Math.floor((Date.now()-Date.parse(scene.capturedAt))/86400000);
      caption.append(el("strong", "", `${scene.sensor} · ${scene.resolutionM} m${scene.fallback ? " · BACKUP SOURCE" : ""}`),
        el("span", age > 7 ? "intel-old" : "", `Captured ${stamp(scene.capturedAt)} · ${age === 0 ? "today" : `${age} day${age === 1 ? "" : "s"} old`}${scene.retained ? " · saved image" : ""}`),
        el("span", "", `${scene.obscuredPercent}% estimated cloud / shadow in crop · ${scene.provider}`),
        el("small", "", `${scene.attribution} · Checked ${stamp(scene.checkedAt)}`), link(scene.source, "Scene metadata ↗"));
      caption.append(el('span', '', `${scene.pixelWidth || 640} source-view pixels across · ${scene.qualityProfile === 'native-individual-v1' ? 'Individual crop · lossless detail' : 'Saved earlier-quality crop'}`));
      if (scene.resolutionM >= 30) caption.append(el('span', 'intel-old', 'Coarser 30 m backup imagery · lower terrain detail than Sentinel-2.'));
    }
    const routeList = el('div', 'lift-legend');
    routeList.append(el('strong', '', 'MAIN REFERENCE LIFT / GONDOLA'));
    routes.forEach((r) => { if (https(r.source)) routeList.append(link(r.source, `${liftName(r)} ↗`)); });
    routeList.append(el('small', '', routes.length ? 'Approximate mapped routes; no open/closed status is implied.' : 'No verified mapped lift route is available for this resort.'));
    if (Number.isFinite(Date.parse(lifts.sourceDataAt))) routeList.append(el('small', '', `Map data as of ${stamp(lifts.sourceDataAt)}`));
    caption.append(routeList);
    if (lifts.attribution) caption.append(link(lifts.source, lifts.attribution), link(lifts.license, 'Lift data · ODbL ↗'), link(new URL('lift-routes.json', document.baseURI).href, 'Route coordinates ↗'));
    caption.append(link("https://browser.dataspace.copernicus.eu/", "Copernicus browser ↗"), link("https://worldview.earthdata.nasa.gov/", "NASA daily regional backup ↗"));
    figure.append(caption); layout.append(figure);
    const brief = el("article", "condition-panel");
    brief.append(el("div", "eyebrow", resort?.region?.toUpperCase()), el("h3", "", name));
    if (usableRead(read)) {
      const report = read.sources.find((s) => s.kind === "reported");
      brief.append(el("span", "condition-mode", read.mode === "ai" ? "AI CONDITIONS READ" : "SOURCE-BASED CONDITIONS READ"));
      const tags = el("div", "condition-tags");
      (read.tags || []).forEach((tag) => tags.append(el("span", "condition-tag", tag)));
      if (!(read.tags || []).length) tags.append(el("span", "condition-tag unknown", "Surface texture unconfirmed"));
      brief.append(tags);
      if (report && !today(report.reportedAt)) brief.append(el("p", "intel-old", `Older surface evidence · reported ${stamp(report.reportedAt)}. No same-day surface report available.`));
      brief.append(el("p", "condition-summary", read.summary));
      if (report?.facts?.conditionsText) {
        const notes = el("details", "condition-notes"); notes.append(el("summary", "", "Resort notes & terrain nuance"), el("p", "", report.facts.conditionsText)); brief.append(notes);
      }
      const sources = el("div", "condition-sources");
      sources.append(el("div", "eyebrow", "DATED EVIDENCE"));
      read.sources.forEach((s) => {
        const item = el("div", "condition-source");
        item.append(link(s.url, `${s.name} ↗`), el("time", "", `${s.kind === "forecast" ? "Forecast issued" : "Reported"} ${stamp(s.reportedAt)}`)); sources.append(item);
      });
      brief.append(sources, el("small", "condition-generation", `Summary generated ${stamp(read.generatedAt)}${read.mode === "ai" ? ` · ${read.model}` : " · AI unavailable; source-based fallback"}`));
    } else {
      brief.append(el("span", "condition-mode", "AWAITING RECENT EVIDENCE"), el("p", "condition-summary", "A fresh, dated conditions read is not available. Check the official resort report; satellite coverage does not confirm snow texture."));
    }
    brief.append(link(resort?.source, "Official resort cameras ↗")); layout.append(brief);
    const back = el("button", "gallery-back", `← All ${catalog.length} resort snapshots`); back.type = "button";
    back.addEventListener("click", () => { select.value = "all"; render(); });
    view.replaceChildren(back, layout);
    renderTileLinks();
  }
  function renderTileLinks() {
    document.querySelectorAll(".tile-intel").forEach((node) => node.remove());
    document.querySelectorAll(".camera-panel").forEach((card) => {
      const name = card.dataset.resort, row = conditions.resorts?.[name];
      const box = el("div", "tile-intel");
      if (usableRead(row) && row.tags?.length) {
        const report = row.sources.find((s) => s.kind === "reported");
        box.append(el("span", "", row.tags.join(" · ")+(report ? ` · Reported ${stamp(report.reportedAt)}` : "")));
      }
      const button = el("button", "", "Satellite & conditions ↗"); button.type = "button";
      button.addEventListener("click", () => root.powderlineIntel.select(name));
      box.append(button); card.append(box);
    });
  }
  root.powderlineIntel = {
    select(name, scroll = true) { if (name !== 'all' && !catalog.some((r) => r.name === name)) return; select.value = name; render(); if (scroll) document.querySelector("#resort-intel").scrollIntoView({behavior: "smooth"}); },
    async refresh() {
      await Promise.allSettled([['satellite.json', (v) => satellite = v], ['conditions.json', (v) => conditions = v], ['lift-routes.json', (v) => lifts = v]].map(async ([file, set]) => {
        const response = await fetch(new URL(file, document.baseURI), {cache: "no-store"});
        if (response.ok) { const json = await response.json(); if (json.resorts && typeof json.resorts === "object") set(json); }
      }));
      render();
    },
  };
  select.addEventListener("change", render);
  const dialog = el("dialog", "camera-dialog satellite-dialog"); dialog.id = "satellite-dialog";
  dialog.setAttribute("aria-labelledby", "satellite-dialog-title");
  const title = el("h2"); title.id = "satellite-dialog-title";
  const close = el("button", "dialog-close", "Close image ×"); close.type = "button"; close.addEventListener("click", () => dialog.close());
  const expandedFrame = el('div', 'satellite-frame satellite-dialog-frame'); expandedFrame.append(el('img'));
  dialog.append(title, close, expandedFrame, el("p", "dialog-age")); document.body.append(dialog);
  render();
})(typeof window === "undefined" ? globalThis : window);
