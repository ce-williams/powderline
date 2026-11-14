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
lift_spec = importlib.util.spec_from_file_location('lift_import', ROOT/'scripts/import_lift_routes.py')
lift_import = importlib.util.module_from_spec(lift_spec)
lift_spec.loader.exec_module(lift_import)


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
    def test_route_import_uses_resort_membership_and_excludes_disused_lifts(self):
        def feature(status, resort):
            return {'geometry': {'type': 'LineString', 'coordinates': [[-106, 39], [-106, 39.01]]},
                    'properties': {'name': 'Main lift', 'status': status, 'liftType': 'chair_lift',
                                   'sources': [{'type': 'openstreetmap', 'id': 'way/123'}],
                                   'skiAreas': [{'properties': {'name': resort}}]}}
        result = lift_import.select_routes([feature('operating', 'Copper Mountain'), feature('disused', 'Vail')], ['Copper Mountain', 'Vail'])
        self.assertEqual(len(result['Copper Mountain']['routes']), 1)
        self.assertEqual(result['Vail']['routes'], [])

    def test_recent_native_cache_copies_exact_bytes_without_rendering(self):
        from PIL import Image
        from io import BytesIO
        data = BytesIO(); Image.new('RGB', (16, 16), 'green').save(data, format='WEBP')
        encoded = data.getvalue()
        now = datetime.now(timezone.utc).isoformat()
        names = ['Arapahoe Basin', 'Loveland']
        row = {'image': 'satellite/region-abc.webp', 'thumbnail': 'satellite/thumb-abc.webp', 'capturedAt': now, 'checkedAt': now}
        locations = json.loads((ROOT/'resort-locations.json').read_text())['resorts']
        manifest = {'schemaVersion': 3, 'resorts': {name: {**row, 'qualityProfile': 'native-individual-v1', 'bbox': satellite.resort_bounds(name, locations[name])} for name in names}}
        def get(url):
            return json.dumps(manifest).encode() if url.endswith('satellite.json') else encoded
        with tempfile.TemporaryDirectory() as temp, patch.object(satellite, 'get', side_effect=get) as fetch, patch.object(satellite, 'collect') as collect:
            satellite.build(Path(temp), names)
            collect.assert_not_called()
            self.assertEqual(fetch.call_count, 3)  # manifest, one full image, one preview
            self.assertEqual((Path(temp)/row['image']).read_bytes(), encoded)

    def test_individual_native_pixels_survive_publication_losslessly(self):
        import numpy as np
        from PIL import Image
        original = np.random.default_rng(7).integers(0, 255, (420, 500, 3), dtype='uint8')
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp); (folder/'satellite').mkdir()
            Image.fromarray(original).save(folder/'satellite/a.png')
            resorts = {'A': {'image': 'satellite/a.png', 'bbox': [-106, 39, -105.9, 39.1], 'sceneId': 'tile-a'}}
            satellite.publish_images(resorts, folder)
            row = resorts['A']
            self.assertEqual((row['pixelWidth'], row['pixelHeight']), (500, 420))
            self.assertEqual(row['view'], [0, 0, 1, 1])
            self.assertEqual(row['sharedWith'], ['A'])
            with Image.open(folder/row['image']) as actual:
                np.testing.assert_array_equal(np.array(actual), original)

    def test_selected_lifts_fit_inside_individual_frames(self):
        data = json.loads((ROOT/'lift-routes.json').read_text())
        locations = json.loads((ROOT/'resort-locations.json').read_text())['resorts']
        self.assertEqual(set(data['resorts']), set(locations))
        self.assertEqual([r['name'] for r in data['resorts']['Copper Mountain']['routes']], ['American Eagle', 'American Flyer', 'Super Bee'])
        for name, row in data['resorts'].items():
            self.assertLessEqual(len(row['routes']), 3)
            west, south, east, north = satellite.resort_bounds(name, locations[name])
            for route in row['routes']:
                self.assertRegex(route['source'], r'^https://www.openstreetmap.org/(way|relation)/[0-9]+$')
                for lon, lat in route['coordinates']:
                    self.assertTrue(west < lon < east and south < lat < north, name)

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
            self.assertTrue(image.startswith(b'\x89PNG'))
            self.assertEqual(cloud, 0)


if __name__ == '__main__':
    unittest.main()
