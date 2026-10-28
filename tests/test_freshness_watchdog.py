from datetime import datetime, timezone
from pathlib import Path
import sys
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from check_feed_freshness import decide


class WatchdogTests(unittest.TestCase):
    now = datetime(2026, 10, 28, 20, 0, tzinfo=timezone.utc)
    old = {"generatedAt": "2026-10-28T17:26:37Z"}

    def test_fresh_batch_needs_no_dispatch(self):
        self.assertEqual(decide({"generatedAt":"2026-10-28T19:30:00Z"}, [], self.now)["action"], "fresh")

    def test_scheduler_gap_requests_refresh(self):
        self.assertEqual(decide(self.old, [], self.now)["action"], "refresh_needed")

    def test_running_or_queued_build_prevents_duplicate_dispatch(self):
        for status in ["in_progress", "queued", "pending", "waiting"]:
            run = {"status":status,"createdAt":"2026-10-28T19:55:00Z","databaseId":42}
            self.assertEqual(decide(self.old, [run], self.now)["action"], "build_running")

    def test_stalled_build_is_reported_without_dispatching_more_jobs(self):
        run = {"status":"in_progress","createdAt":"2026-10-28T19:30:00Z","databaseId":42}
        self.assertEqual(decide(self.old, [run], self.now)["action"], "build_stalled")

    def test_future_batch_does_not_suppress_checks_indefinitely(self):
        with self.assertRaises(ValueError):
            decide({"generatedAt":"2026-10-29T20:00:00Z"}, [], self.now)
