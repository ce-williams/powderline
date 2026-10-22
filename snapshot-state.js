// Shared validation and timestamps for cached camera images.
window.powderlineSnapshotTools = {
  valid(id, entry) {
    return Boolean(entry && /^[a-z0-9-]+$/.test(id) && entry.file === `snapshots/${id}.jpg` && Number.isFinite(Date.parse(entry.fetchedAt)));
  },
  age(timestamp, currentTime = Date.now()) {
    const minutes = Math.max(0, Math.floor((currentTime - Date.parse(timestamp)) / 60000));
    if (!Number.isFinite(minutes)) return "Time unavailable";
    if (minutes < 1) return "Fetched just now";
    if (minutes < 60) return `Fetched ${minutes}m ago`;
    const hours = Math.floor(minutes / 60);
    return hours < 24 ? `Fetched ${hours}h ago` : `Fetched ${Math.floor(hours / 24)}d ago`;
  },
  stale(entry, currentTime = Date.now()) {
    return entry.status === "retained" || currentTime - Date.parse(entry.fetchedAt) > 2 * 60 * 60 * 1000;
  },
  url(entry, base) {
    const url = new URL(`./${entry.file}`, base);
    url.searchParams.set("v", entry.sha256 || entry.fetchedAt);
    return url.href;
  },
};
