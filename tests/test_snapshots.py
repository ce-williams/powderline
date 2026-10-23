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

    def test_known_offline_graphic_is_rejected_including_resized_jpeg_and_retention(self):
        body = (Path(__file__).parent / "fixtures/brownrice-offline.jpg").read_bytes()
        with Image.open(BytesIO(body)) as image:
            image.thumbnail((960, 720))
            encoded = BytesIO()
            image.save(encoded, format="JPEG", quality=82)
        for candidate in [body, encoded.getvalue()]:
            with self.assertRaisesRegex(ValueError, "Provider status graphic"):
                snapshots.normalize_image(candidate)
        with tempfile.TemporaryDirectory() as directory, patch.object(snapshots, "download", return_value=body):
            entry = {"file": "snapshots/test-cam.jpg", "fetchedAt": "2026-10-22T10:00:00Z", "sha256": hashlib.sha256(body).hexdigest()}
            with self.assertRaisesRegex(ValueError, "Provider status graphic"):
                snapshots.retain_snapshot(Path(directory), "test-cam", entry)

    def test_black_night_frame_is_not_confused_with_offline_graphic(self):
        output = BytesIO()
        Image.new("RGB", (640, 360), (0, 0, 0)).save(output, format="JPEG")
        self.assertTrue(snapshots.normalize_image(output.getvalue()))

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

    def test_confirmed_offline_archive_is_not_fetched_as_a_current_camera(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(snapshots, "download") as fetch:
            camera = {"id":"archive-cam","provider":"image","src":"https://example.com/archive.jpg"}
            self.assertEqual(snapshots.capture_image(camera, Path(directory), {}, {"disabledReason":"Provider reports offline"}), ("archive-cam", None))
            fetch.assert_not_called()

    def test_provider_preview_is_usable_without_claiming_a_rendered_video_frame(self):
        with tempfile.TemporaryDirectory() as directory:
            camera = {"id": "test-cam", "provider": "link", "src": "https://example.com/cameras"}
            config = {"snapshotUrl": "https://example.com/preview.jpg", "snapshotKind": "provider-preview"}
            with patch.object(snapshots, "download", return_value=camera_image()):
                camera_id, entry = snapshots.capture_image(camera, Path(directory), {}, config)
            self.assertEqual(camera_id, "test-cam")
            self.assertEqual(entry["method"], "provider-preview")
            self.assertTrue((Path(directory) / entry["file"]).exists())

    def test_steamboat_and_sunlight_images_do_not_depend_on_loading_the_resort_page(self):
        root = Path(__file__).resolve().parents[1]
        configs = json.loads((root / "snapshot-sources.json").read_text())
        cameras = {camera["id"]: camera for camera in json.loads((root / "source-registry.json").read_text())["cameras"]}
        ids = ["steamboat-mid-snow", "steamboat-champagne", "steamboat-square", "steamboat-gondola", "steamboat-christie", "steamboat-four-points", "sunlight-stake"]
        with tempfile.TemporaryDirectory() as directory:
            for camera_id in ids:
                with self.subTest(camera=camera_id), patch.object(snapshots, "download", return_value=camera_image()) as fetch:
                    _, entry = snapshots.capture_image(cameras[camera_id], Path(directory), {}, configs[camera_id])
                    fetch.assert_called_once_with(configs[camera_id]["snapshotUrl"])
                    self.assertIsNotNone(entry)
                    self.assertTrue((Path(directory) / entry["file"]).exists())

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
