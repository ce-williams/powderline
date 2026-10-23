"""Build an hourly, same-origin camera wall; retain last-good images on failure.

Only public source URLs are used. Failed players/challenges never become snapshots.
No images are committed to Git. The previous deployed manifest is our durable cache.
"""
import argparse
import concurrent.futures
from datetime import datetime, timezone
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import urllib.request
from urllib.parse import urlsplit, urljoin

from PIL import Image, ImageOps

SITE_URL = "https://ce-williams.github.io/powderline/"
MAX_BYTES = 8 * 1024 * 1024
Image.MAX_IMAGE_PIXELS = 30_000_000
REJECTED_IMAGES = json.loads(Path(__file__).with_name("rejected-images.json").read_text())


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def public_url(url):
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Not a public HTTPS source")
    return url


def download(url):
    request = urllib.request.Request(public_url(url), headers={"User-Agent": "Powderline/1.0 (+https://ce-williams.github.io/powderline/)"})
    with urllib.request.urlopen(request, timeout=25) as response:
        public_url(response.url)
        body = response.read(MAX_BYTES + 1)
    if len(body) > MAX_BYTES:
        raise ValueError("Response too large")
    return body


def normalize_image(body):
    with Image.open(BytesIO(body)) as image:
        image.load()
        if image.width < 160 or image.height < 90:
            raise ValueError("Response is too small to be a camera view")
        image = ImageOps.exif_transpose(image).convert("RGB")
        sample = image.convert("L").resize((32, 18)).tobytes()
        for rejected in REJECTED_IMAGES:
            reference = bytes.fromhex(rejected["sample"])
            if sum(abs(a - b) for a, b in zip(sample, reference)) / len(sample) < 1.5:
                raise ValueError("Provider status graphic: " + rejected["name"])
        image.thumbnail((960, 720))
        output = BytesIO()
        image.save(output, format="JPEG", quality=82, optimize=True)
        return output.getvalue()


def valid_entry(camera_id, entry):
    return (isinstance(entry, dict) and entry.get("file") == f"snapshots/{camera_id}.jpg"
            and bool(re.fullmatch(r"[a-z0-9-]+", camera_id)) and bool(entry.get("fetchedAt")))


def write_snapshot(output, camera_id, body, previous=None, fetched_at=None, method="source-image"):
    body = normalize_image(body)
    fetched_at = fetched_at or now()
    digest = hashlib.sha256(body).hexdigest()
    previous = previous or {}
    filename = f"snapshots/{camera_id}.jpg"
    path = output / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(body)
    temporary.replace(path)
    return {"file": filename, "fetchedAt": fetched_at,
            "changedAt": previous.get("changedAt", fetched_at) if previous.get("sha256") == digest else fetched_at,
            "sha256": digest, "method": method, "lastAttemptAt": fetched_at, "status": "ok"}


def retain_snapshot(output, camera_id, entry, previous_site=SITE_URL):
    if not valid_entry(camera_id, entry):
        raise ValueError("No valid last-good snapshot")
    body = download(urljoin(previous_site, entry["file"]) + "?v=" + entry.get("sha256", ""))
    # Validate the old JPEG but preserve its bytes and original timestamps.
    normalize_image(body)
    if hashlib.sha256(body).hexdigest() != entry.get("sha256"):
        raise ValueError("Last-good image does not match manifest")
    path = output / entry["file"]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(body)
    return {**entry, "status": "retained", "lastAttemptAt": now()}


def load_previous(previous_site=SITE_URL):
    try:
        manifest = json.loads(download(urljoin(previous_site, "snapshots/manifest.json") + "?batch=" + now()))
        if not isinstance(manifest.get("cameras"), dict):
            raise ValueError("Invalid manifest")
        return manifest["cameras"]
    except Exception:
        return {}


def capture_image(camera, output, previous, config=None):
    config = config or {}
    source = camera.get("previewSrc") or (camera["src"] if camera["provider"] == "image" else config.get("snapshotUrl"))
    if not source:
        return camera["id"], None
    try:
        return camera["id"], write_snapshot(output, camera["id"], download(source), previous.get(camera["id"]), method=config.get("snapshotKind", "source-image"))
    except Exception:
        return camera["id"], None


def write_manifest(output, cameras, entries):
    manifest = {"generatedAt": now(), "refreshIntervalMinutes": 30, "cameras": entries,
                "summary": {"totalCameras": len(cameras), "available": sum(bool(e.get("file")) for e in entries.values()),
                            "updated": sum(e["status"] == "ok" for e in entries.values()),
                            "retained": sum(e["status"] == "retained" for e in entries.values())}}
    (output / "snapshots").mkdir(parents=True, exist_ok=True)
    (output / "snapshots/manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    (output / "snapshot-manifest.js").write_text("window.powderlineSnapshots = " + json.dumps(manifest) + ";\n")
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("_site"))
    parser.add_argument("--skip-browser", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    cameras = json.loads((root / "source-registry.json").read_text())["cameras"]
    previous = load_previous()
    configs = json.loads((root / "snapshot-sources.json").read_text())
    args.output.mkdir(parents=True, exist_ok=True)
    entries = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        for camera_id, entry in pool.map(lambda camera: capture_image(camera, args.output, previous, configs.get(camera["id"])), cameras):
            if entry:
                entries[camera_id] = entry
    print(f"Fetched {len(entries)} source images", flush=True)
    if not args.skip_browser:
        try:
            from capture_players import capture_players
            pending = [camera for camera in cameras if camera["id"] not in entries]
            entries.update(capture_players(pending, configs, args.output, previous))
        except Exception as error:
            print(f"Player capture unavailable ({type(error).__name__}); retaining previous images", flush=True)
    for camera in cameras:
        camera_id = camera["id"]
        if camera_id in entries:
            continue
        try:
            entries[camera_id] = retain_snapshot(args.output, camera_id, previous.get(camera_id))
        except Exception:
            entries[camera_id] = {"status": "unavailable", "lastAttemptAt": now()}
    manifest = write_manifest(args.output, cameras, entries)
    print(json.dumps(manifest["summary"]), flush=True)
    print("No snapshot: " + ", ".join(camera_id for camera_id, entry in entries.items() if not entry.get("file")), flush=True)
    # Do not replace a populated site with an empty cache during a systemic outage.
    if not manifest["summary"]["available"]:
        raise SystemExit("No usable snapshots; preserving the current deployment")


if __name__ == "__main__":
    main()
