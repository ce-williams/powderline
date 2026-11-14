import importlib.util
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
import unittest
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, ROOT/'scripts'/f'build_{name}.py')
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


conditions = module('conditions')
satellite = module('satellite')


class ConditionsTest(unittest.TestCase):
    def setUp(self):
        self.now = datetime(2026, 11, 14, 2, tzinfo=timezone.utc)
        self.report = {'source': 'https://example.com/report', 'reportedAt': self.now.isoformat(),
                       'surfacePrimary': 'P/PP', 'surfaceSecondary': 'MM', 'snow24': 0}

    def test_mixed_surfaces_and_zero_do_not_imply_powder(self):
        self.assertEqual(conditions.surface_tags(self.report), ['Powder', 'Packed powder', 'Machine-made'])
        self.assertEqual(conditions.surface_tags({'snow24': 20}), [])

    def test_nuanced_surfaces_require_explicit_surface_fields(self):
        self.assertIn('Dust on crust', conditions.surface_tags({'surfacePrimary': 'dust on crust'}))
        self.assertEqual(conditions.surface_tags({'surfacePrimary': 'No powder; possible crust tomorrow'}), [])
        self.assertEqual(conditions.surface_tags({'conditionsText': 'Powder expected tomorrow'}), [])

    def test_old_future_and_undated_reports_are_excluded(self):
        for stamp in [None, 'not-a-date', (self.now-timedelta(hours=73)).isoformat(), (self.now+timedelta(hours=1)).isoformat()]:
            with self.subTest(stamp=stamp):
                self.assertEqual(conditions.evidence({**self.report, 'reportedAt': stamp}, None, self.now), [])
        old = conditions.evidence({**self.report, 'reportedAt': (self.now-timedelta(hours=26)).isoformat()}, None, self.now)
        self.assertFalse(old[0]['sameDay'])
        self.assertIn('older resort report', conditions.fallback(old)[0])

    def test_forecast_alone_never_claims_texture(self):
        weather = {'id': 'nws', 'lowF': 24, 'highF': 42, 'periods': [{'text': 'Snow'}]}
        summary, tags = conditions.fallback([weather])
        self.assertEqual(tags, [])
        self.assertIn('possible, not a confirmed', summary)

    def test_ai_rejects_unbacked_category_and_bad_citations(self):
        sources = conditions.evidence(self.report, None, self.now)
        for answer in [{'summary': 'Dust on crust across the entire mountain.', 'sourceIds': ['resort']},
                       {'summary': 'The resort reports packed powder.', 'sourceIds': ['invented']}]:
            response = {'output': [{'content': [{'type': 'output_text', 'text': json.dumps(answer)}]}]}
            with patch.object(conditions, 'request_json', return_value=response), self.assertRaises(ValueError):
                conditions.ai_summary('Resort', sources, 'test-key', 'test-model')

    def test_ai_uses_structured_sources_and_no_browser_secret(self):
        sources = conditions.evidence(self.report, None, self.now)
        answer = {'summary': 'The resort reports powder, packed powder and machine-made snow. Conditions can vary.', 'sourceIds': ['resort']}
        response = {'output': [{'content': [{'type': 'output_text', 'text': json.dumps(answer)}]}]}
        with patch.object(conditions, 'request_json', return_value=response) as api:
            self.assertEqual(conditions.ai_summary('Resort', sources, 'test-key', 'test-model')[0], answer['summary'])
            self.assertFalse(api.call_args.args[1]['store'])
            self.assertTrue(api.call_args.args[1]['text']['format']['strict'])


class SatelliteTest(unittest.TestCase):
    def test_primary_failure_uses_backup_and_preserves_acquisition(self):
        now = datetime.now(timezone.utc)
        scene = {'id': 'scene', 'properties': {'datetime': (now-timedelta(days=2)).isoformat()}}
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder)
            (output/'satellite').mkdir()
            with patch.object(satellite, 'search', side_effect=[OSError('offline'), [scene]]), patch.object(satellite, 'render', return_value=(b'image', 4.2)):
                row = satellite.collect('Resort', [39.5, -106], {}, output, now)
            self.assertTrue(row['fallback'])
            self.assertEqual(row['capturedAt'], scene['properties']['datetime'])
            self.assertEqual(row['checkedAt'], now.isoformat())
            self.assertEqual(row['provider'], 'Microsoft Planetary Computer')

    def test_recency_order_and_visibility_filter(self):
        now = datetime.now(timezone.utc)
        def scene(days, clouds):
            return {'properties': {'datetime': (now-timedelta(days=days)).isoformat(), 'eo:cloud_cover': clouds}}
        good, old = scene(1, 20), scene(5, 0)
        self.assertEqual(satellite.candidates([old, scene(-1, 0), scene(31, 0), scene(0, 99), good], now), [good, old])

    def test_every_resort_has_a_colorado_location(self):
        locations = json.loads((ROOT/'resort-locations.json').read_text())['resorts']
        names = {r['name'] for r in json.loads((ROOT/'source-registry.json').read_text())['resorts']}
        self.assertEqual(set(locations), names)
        for lat, lon in locations.values():
            self.assertTrue(37 <= lat <= 41 and -109 <= lon <= -102)
            west, south, east, north = satellite.bounds(lat, lon)
            self.assertTrue(west < lon < east and south < lat < north)

    def test_local_clouds_and_incomplete_coverage_rejected(self):
        import numpy as np
        item = {'assets': {'visual': {'href': 'rgb'}, 'scl': {'href': 'scl'}}}
        rgb = np.full((3, 10, 10), 180, dtype='uint8')
        valid = np.ones((10, 10), dtype=bool)
        for scl, mask in [(np.full((1, 10, 10), 9), valid), (np.full((1, 10, 10), 4), np.zeros((10, 10), dtype=bool))]:
            with patch.object(satellite, 'read_crop', side_effect=[(rgb, mask), (scl, valid)]), self.assertRaises(ValueError):
                satellite.render(item, [-106, 39, -105, 40], satellite.ES, 'sentinel-2-l2a')
        with patch.object(satellite, 'read_crop', side_effect=[(rgb, valid), (np.full((1, 10, 10), 11), valid)]):
            image, cloud = satellite.render(item, [-106, 39, -105, 40], satellite.ES, 'sentinel-2-l2a')
            self.assertTrue(image.startswith(b'\xff\xd8'))
            self.assertEqual(cloud, 0)


if __name__ == '__main__':
    unittest.main()
