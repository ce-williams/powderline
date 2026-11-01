import importlib.util
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path

spec = importlib.util.spec_from_file_location('snow', Path(__file__).resolve().parents[1] / 'scripts/build_snow_reports.py')
snow = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snow)


class SnowReportsTest(unittest.TestCase):
    def test_missing_and_trace_are_not_zero(self):
        for value in [None, '', '-', 'Trace', True, -1, 'NaN', 'Infinity', '2 inches']:
            self.assertIsNone(snow.number(value))
        self.assertEqual(snow.number('0'), 0)
        self.assertEqual(snow.number('2.5'), 2.5)

    def test_colorado_alias_and_source_timestamp(self):
        result = snow.parse_colorado({'open_resorts': [{'resort': {'resort_title': 'Cooper', 'available_lifts': 5},
            'snow_report': {'snow_total_24_hour': 0, 'snow_total_48_hour': '', 'updated': '2026-11-01T05:00:00-07:00', 'open_lifts': 0}}], 'closed_resorts': []}, '2026-11-01T12:00:00Z')['Ski Cooper']
        self.assertEqual(result['snow24'], 0)
        self.assertIsNone(result['snow48'])
        self.assertEqual(result['liftsOpen'], 0)
        self.assertEqual(result['liftsTotal'], 5)
        self.assertEqual(result['reportedAt'], '2026-11-01T05:00:00-07:00')

    def test_vail_reads_only_json_and_preserves_mountain_offset(self):
        html = 'FR.snowReportData = {"TwentyFourHourSnowfall":{"Inches":"3"},"BaseDepth":{"Inches":"18"},"LastUpdatedText":"Updated November 1, 2026 at 5:10 AM MST"}; evil();'
        report = snow.parse_vail(html, 'https://www.vail.com/', 'now')
        self.assertEqual(report['snow24'], 3)
        self.assertEqual(report['depth'], 18)
        self.assertIsNone(report['snow48'])
        self.assertTrue(report['reportedAt'].endswith('-07:00'))
        with self.assertRaises(ValueError):
            snow.parse_vail('FR.snowReportData = {};', 'source', 'now')

    def test_retention_does_not_reset_age_or_cross_sources(self):
        now = datetime.now(timezone.utc)
        old = {'source': 'https://source/', 'reportedAt': (now - timedelta(days=1)).isoformat(), 'fetchedAt': (now - timedelta(hours=1)).isoformat(), 'snow24': 2}
        retained = snow.retain(old, 'https://source/', now)
        self.assertEqual(retained['reportedAt'], old['reportedAt'])
        self.assertEqual(retained['fetchedAt'], old['fetchedAt'])
        self.assertTrue(retained['retained'])
        self.assertIsNone(snow.retain(old, 'https://other/', now))
        old['fetchedAt'] = (now - timedelta(days=8)).isoformat()
        self.assertIsNone(snow.retain(old, 'https://source/', now))
