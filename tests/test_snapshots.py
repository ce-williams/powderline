import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_snapshots as snapshots


def camera_image(size=(640, 360)):
    output = BytesIO()
    Image.new("RGB", size, (21, 42, 63)).save(output, format="PNG")
    return output.getvalue()


class SnapshotTests(unittest.TestCase):
    def test_error_pages_and_tiny_provider_icons_never_become_snapshots(self):
        for body in [b"<html>Camera unavailable</html>", camera_image((120, 90))]:
            with self.assertRaises(Exception):
                snapshots.normalize_image(body)

    def test_nighttime_frames_are_valid_and_large_images_are_reduced(self):
        body = snapshots.normalize_image(camera_image((1920, 1080)))
        with Image.open(BytesIO(body)) as image:
            self.assertEqual(image.size, (960, 540))
            self.assertEqual(image.format, "JPEG")

    def test_unchanged_source_updates_fetch_time_but_preserves_change_time(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            first = snapshots.write_snapshot(output, "test-cam", camera_image(), fetched_at="2026-10-21T10:00:00Z")
            second = snapshots.write_snapshot(output, "test-cam", camera_image(), first, fetched_at="2026-10-21T11:00:00Z")
            self.assertEqual(second["changedAt"], first["changedAt"])
            self.assertEqual(second["fetchedAt"], "2026-10-21T11:00:00Z")
            self.assertEqual(hashlib.sha256((output / second["file"]).read_bytes()).hexdigest(), second["sha256"])

    def test_failed_capture_retains_the_previous_image_without_freshening_its_age(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            previous = snapshots.write_snapshot(output, "test-cam", camera_image(), fetched_at="2026-10-21T10:00:00Z")
            body = (output / previous["file"]).read_bytes()
            camera = {"id": "test-cam", "provider": "image", "src": "https://example.com/camera.jpg"}
            with patch.object(snapshots, "download", side_effect=OSError("source offline")):
                self.assertEqual(snapshots.capture_image(camera, output, {"test-cam": previous}), ("test-cam", None))
            with patch.object(snapshots, "download", return_value=body):
                retained = snapshots.retain_snapshot(output, "test-cam", previous)
            self.assertEqual(retained["status"], "retained")
            self.assertEqual(retained["fetchedAt"], previous["fetchedAt"])
            self.assertEqual((output / retained["file"]).read_bytes(), body)

    def test_corrupt_or_mismatched_previous_image_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            previous = snapshots.write_snapshot(output, "test-cam", camera_image())
            with patch.object(snapshots, "download", return_value=b"<html>Not found</html>"):
                with self.assertRaises(Exception):
                    snapshots.retain_snapshot(output, "test-cam", previous)
            with patch.object(snapshots, "download", return_value=camera_image()):
                with self.assertRaises(ValueError):
                    snapshots.retain_snapshot(output, "test-cam", previous)

    def test_manifest_cannot_supply_arbitrary_paths_or_authenticated_urls(self):
        self.assertFalse(snapshots.valid_entry("test-cam", {"file": "../private.jpg", "fetchedAt": "2026-10-21T10:00:00Z"}))
        for url in ["http://example.com/cam", "https://user:secret@example.com/cam"]:
            with self.assertRaises(ValueError):
                snapshots.public_url(url)

    def test_manifest_counts_retained_views_as_available_and_keeps_unavailable_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            entries = {"a": {"file": "snapshots/a.jpg", "status": "ok"}, "b": {"file": "snapshots/b.jpg", "status": "retained"}, "c": {"status": "unavailable"}}
            manifest = snapshots.write_manifest(Path(directory), [{}, {}, {}], entries)
            self.assertEqual(manifest["summary"], {"totalCameras": 3, "available": 2, "updated": 1, "retained": 1})
            self.assertEqual(json.loads((Path(directory) / "snapshots/manifest.json").read_text()), manifest)


if __name__ == "__main__":
    unittest.main()
