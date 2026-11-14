#!/usr/bin/env python3
"""Reduce an OpenSkiData lift download to a small, attributed Colorado overlay.

Download lifts.geojson at most once per day per the provider's terms. This
manual import has no schedule and never calls live map tiles or private APIs.
"""
import argparse
from datetime import datetime, timezone
import json
import math
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parent.parent
ALIASES = {'Aspen Snowmass': 'Snowmass', 'Beaver Creek Resort (Arrowhead Mountain)': 'Beaver Creek',
    'Breckenridge Ski Resort': 'Breckenridge', 'Chapman Hill Recreation Area': 'Chapman Hill',
    'Cranor Hill Municipal Ski Hill': 'Cranor Hill', 'Crested Butte Mountain Resort': 'Crested Butte',
    'Cuchara Mountain Resort': 'Cuchara Mountain Park', 'Hesperus Ski Area': 'Hesperus',
    'Howelson Hill Ski Area': 'Howelsen Hill', 'Kendall Mountain Recreation Area': 'Kendall Mountain',
    'Loveland Basin Ski Area': 'Loveland', 'Loveland Valley Ski Area': 'Loveland',
    'Purgatory Resort': 'Purgatory', 'Steamboat Ski Resort': 'Steamboat',
    'Sunlight Mountain Resort': 'Sunlight Mountain', 'Telluride Ski Area': 'Telluride',
    'Winter Park Resort': 'Winter Park', 'Wolf Creek Ski Area': 'Wolf Creek'}
PREFERRED = {
    'Copper Mountain': ['American Eagle', 'American Flyer', 'Super Bee'],
    'Arapahoe Basin': ['Black Mountain Express', 'Lenawee Express', 'Pallavicini'],
    'Keystone': ['River Run Gondola', 'Summit Express', 'Peru Express'],
    'Breckenridge': ['Colorado SuperChair', 'Rocky Mountain SuperChair', 'Independence SuperChair'],
    'Vail': ['Gondola One', 'Eagle Bahn Gondola', 'Mountaintop Express'],
    'Beaver Creek': ['Centennial Express', 'Strawberry Park Express', 'Birds of Prey Express'],
    'Loveland': ["Chet's Dream", 'Lift 2', 'Ptarmigan Lift'],
    'Eldora': ['Alpenglow', 'Indian Peaks', 'Corona'],
    'Winter Park': ['The Gondola', 'Super Gauge Express', 'Pioneer Express'],
    'Steamboat': ['Wild Blue Gondola', 'Steamboat Gondola', 'Sundown Express'],
    'Aspen Mountain': ['Silver Queen', 'Ajax Express', 'Gentleman’s Ridge'],
    'Aspen Highlands': ['Exhibition', 'Loge Peak', 'Cloud Nine'],
    'Buttermilk': ['Summit Express', 'West Buttermilk Express', 'Tiehack Express'],
    'Snowmass': ['Elk Camp Gondola', 'Village Express', 'Alpine Springs'],
    'Crested Butte': ['Red Lady Express', 'Silver Queen Express', 'Paradise Express'],
    'Telluride': ['Gondola', 'Village Express', 'Plunge'],
    'Powderhorn': ['Flat Top Flyer', 'West End', 'Easy Rider'],
    'Wolf Creek': ['Treasure Stoke Chairlift', 'Bonanza Chair', 'Alberta Lift'],
}


def normalize(name):
    return re.sub(r'[^a-z0-9]', '', (name or '').lower())


def length_km(coords):
    return sum(math.hypot((b[0]-a[0])*111.32*math.cos(math.radians((a[1]+b[1])/2)),
                          (b[1]-a[1])*111.32) for a, b in zip(coords, coords[1:]))


def select_routes(features, names):
    candidates = {name: [] for name in names}
    for feature in features:
        p, geometry = feature.get('properties', {}), feature.get('geometry') or {}
        coords = geometry.get('coordinates', [])
        if geometry.get('type') != 'LineString' or len(coords) < 2 or p.get('status') != 'operating':
            continue
        if p.get('liftType') in ('zip_line', 'goods') or not coords or not (-109.1 < coords[0][0] < -102 and 37 < coords[0][1] < 41.1):
            continue
        for area in p.get('skiAreas', []):
            source_name = area.get('properties', {}).get('name')
            name = ALIASES.get(source_name, source_name)
            if name not in candidates:
                continue
            sources = ['https://www.openstreetmap.org/'+s['id'] for s in p.get('sources', []) if s.get('type') == 'openstreetmap' and re.fullmatch(r'(way|relation)/\d+', s.get('id', ''))]
            if not sources:
                continue
            candidates[name].append({'name': p.get('name') or p.get('ref') or 'Mapped lift',
                'type': p.get('liftType'), 'coordinates': [[round(c[0], 7), round(c[1], 7)] for c in coords],
                'source': sources[0], 'lengthKm': round(length_km(coords), 3)})
    resorts = {}
    for name, rows in candidates.items():
        # Infrastructure status is not a daily open/closed report.
        unique = {r['source']: r for r in rows}
        rows = list(unique.values())
        selected = []
        for preferred in PREFERRED.get(name, []):
            match = next((r for r in rows if normalize(r['name']).startswith(normalize(preferred))), None)
            if match and match not in selected:
                selected.append(match)
        ranked = sorted(rows, key=lambda r: (r['type'] not in ('gondola', 'mixed_lift', 'cable_car'),
                                             r['type'] != 'chair_lift', -r['lengthKm']))
        for row in ranked:
            if len(selected) >= 3:
                break
            if row not in selected:
                selected.append(row)
        resorts[name] = {'routes': selected[:3], 'mappedLiftCount': len(rows)}
    return resorts


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--source-date', required=True, help='OpenStreetMap dataTimestamp from metadata.json')
    args = parser.parse_args()
    names = json.loads((ROOT/'resort-locations.json').read_text())['resorts']
    payload = {'sourceDataAt': args.source_date, 'importedAt': datetime.now(timezone.utc).isoformat(),
        'source': 'https://openskidata.org/', 'license': 'https://opendatacommons.org/licenses/odbl/1-0/',
        'attribution': "Data from OpenSkiData / OpenSkiMap.org, © OpenStreetMap contributors (ODbL), Skimap.org, Who’s On First, © Mapterhorn",
        'note': 'Selected lift infrastructure routes, not a live lift-status report. Map geometry is approximate and may lag resort changes.',
        'resorts': select_routes(json.loads(args.input.read_text())['features'], names)}
    (ROOT/'lift-routes.json').write_text(json.dumps(payload, separators=(',', ':'))+'\n')
    print(f'Lift routes: {sum(bool(r["routes"]) for r in payload["resorts"].values())}/{len(names)} resorts')
