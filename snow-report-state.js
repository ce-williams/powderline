(function (root) {
  const fields = ["snow24", "snow48", "snow7", "depth", "liftsOpen", "liftsTotal"];
  const numeric = (value) => typeof value === "number" && Number.isFinite(value) && value >= 0 && value <= 2000;
  root.powderlineSnowTools = {
    value(report, field, now = Date.now()) {
      const date = Date.parse(report?.reportedAt);
      return Number.isFinite(date) && date <= now + 5 * 60 * 1000 && now - date <= 7 * 24 * 60 * 60 * 1000 && numeric(report[field])
        ? `${report[field]}${field.startsWith("lifts") ? "" : "″"}` : "—";
    },
    stale(report, now = Date.now()) {
      const date = Date.parse(report?.reportedAt);
      return Number.isFinite(date) && (now - date > 36 * 60 * 60 * 1000 || date > now + 5 * 60 * 1000);
    },
    valid(manifest) {
      return manifest?.resorts && typeof manifest.resorts === "object" && !Array.isArray(manifest.resorts) &&
        Object.values(manifest.resorts).every((r) => r && typeof r === "object" &&
          (!r.source || /^https:\/\//.test(r.source)) && fields.every((f) => r[f] == null || numeric(r[f])));
    },
  };
})(typeof window === "undefined" ? globalThis : window);
