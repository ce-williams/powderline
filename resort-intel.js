(function (root) {
  const MAX_REPORT = 72 * 3600000;
  const MAX_IMAGE = 30 * 86400000;
  const timestamp = (value, max, now = Date.now()) => {
    const t = Date.parse(value);
    return Number.isFinite(t) && t <= now + 300000 && now - t <= max;
  };
  const https = (value) => typeof value === "string" && /^https:\/\//.test(value);
  const imagePath = (value) => typeof value === "string" && /^satellite\/[a-z0-9-]+\.jpg$/.test(value);
  const stamp = (value) => new Intl.DateTimeFormat("en-US", {timeZone: "America/Denver", month: "short", day: "numeric", year: "numeric", hour: "numeric", minute: "2-digit", timeZoneName: "short"}).format(new Date(value));
  const today = (value) => new Date(value).toLocaleDateString("en-CA", {timeZone: "America/Denver"}) === new Date().toLocaleDateString("en-CA", {timeZone: "America/Denver"});
  const usableRead = (row, now = Date.now()) => row && typeof row.summary === "string" && row.summary.length <= 850 &&
    timestamp(row.generatedAt, 18 * 3600000, now) && Array.isArray(row.sources) &&
    row.sources.length > 0 && row.sources.every((s) => https(s.url) && timestamp(s.reportedAt, s.kind === "forecast" ? 18 * 3600000 : MAX_REPORT, now));
  const usableImage = (row, now = Date.now()) => row && imagePath(row.image) && https(row.source) && timestamp(row.capturedAt, MAX_IMAGE, now);
  root.powderlineIntelTools = {timestamp, imagePath, usableRead, usableImage};
  if (typeof document === "undefined") return;
  let satellite = {resorts: {}}, conditions = {resorts: {}};
  const catalog = root.powderlineResortCatalog || [];
  const select = document.querySelector("#intel-resort");
  const view = document.querySelector("#intel-view");
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
  catalog.forEach((r) => {
    const option = el("option", "", r.name); option.value = r.name; select.append(option);
  });
  select.value = catalog.some((r) => r.name === "Copper Mountain") ? "Copper Mountain" : catalog[0]?.name;
  function render() {
    const name = select.value, resort = catalog.find((r) => r.name === name);
    const scene = satellite.resorts?.[name], read = conditions.resorts?.[name];
    const layout = el("div", "intel-layout");
    const figure = el("figure", "satellite-panel");
    const frame = el("div", "satellite-frame");
    if (usableImage(scene)) {
      const img = el("img"); img.src = new URL(scene.image+"?scene="+encodeURIComponent(scene.sceneId || scene.capturedAt), document.baseURI).href;
      img.alt = `${name} and surrounding terrain, ${scene.sensor} true-color satellite image acquired ${stamp(scene.capturedAt)}`;
      img.decoding = "async";
      img.addEventListener("error", () => {
        frame.replaceChildren(el("p", "satellite-empty", "Satellite image could not load. Open the scene source below."));
      });
      frame.append(img, el("span", "satellite-north", "N ↑"), el("span", "satellite-crosshair", "+"), el("span", "satellite-scale", "10 KM ACROSS · TRUE COLOR"));
      const expand = el("button", "satellite-expand", "Expand image ⛶"); expand.type = "button";
      expand.addEventListener("click", () => {
        const dialog = document.querySelector("#satellite-dialog");
        dialog.querySelector("h2").textContent = `${name} · ${scene.sensor}`;
        dialog.querySelector("img").src = img.src; dialog.querySelector("img").alt = img.alt;
        dialog.querySelector("p").textContent = `Captured ${stamp(scene.capturedAt)} · ${scene.attribution}. North up; 10 km across. No trail boundaries shown.`;
        dialog.showModal();
      });
      frame.append(expand);
    } else frame.append(el("p", "satellite-empty", "No usable satellite crop from the past 30 days. Clouds or source availability can delay imagery."));
    figure.append(frame);
    const caption = el("figcaption", "satellite-caption");
    if (usableImage(scene)) {
      const age = Math.floor((Date.now()-Date.parse(scene.capturedAt))/86400000);
      caption.append(el("strong", "", `${scene.sensor} · ${scene.resolutionM} m${scene.fallback ? " · BACKUP SOURCE" : ""}`),
        el("span", age > 7 ? "intel-old" : "", `Captured ${stamp(scene.capturedAt)} · ${age === 0 ? "today" : `${age} day${age === 1 ? "" : "s"} old`}${scene.retained ? " · saved image" : ""}`),
        el("span", "", `${scene.obscuredPercent}% estimated cloud / shadow in crop · ${scene.provider}`),
        el("small", "", `${scene.attribution} · Checked ${stamp(scene.checkedAt)}`), link(scene.source, "Scene metadata ↗"));
    }
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
    view.replaceChildren(layout);
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
    select(name) { if (!catalog.some((r) => r.name === name)) return; select.value = name; render(); document.querySelector("#resort-intel").scrollIntoView({behavior: "smooth"}); },
    async refresh() {
      await Promise.allSettled([['satellite.json', (v) => satellite = v], ['conditions.json', (v) => conditions = v]].map(async ([file, set]) => {
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
  dialog.append(title, close, el("img"), el("p", "dialog-age")); document.body.append(dialog);
  render();
})(typeof window === "undefined" ? globalThis : window);
