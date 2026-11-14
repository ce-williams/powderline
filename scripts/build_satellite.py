#!/usr/bin/env python3
"""Publish dated resort crops from open Sentinel-2, with host and Landsat fallback.

No CalTopo tiles or credentials are used. Read cloud-optimized GeoTIFF windows,
never entire scenes. Classification is for image visibility, not snow texture.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from io import BytesIO
import json
import math
import threading
import time
from pathlib import Path
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parent.parent
PUBLIC = 'https://ce-williams.github.io/powderline/'
PC = 'https://planetarycomputer.microsoft.com/api/stac/v1'
ES = 'https://earth-search.aws.element84.com/v1'
HOSTS = [(ES, 'sentinel-2-l2a', 'Element 84 Earth Search', 10),
         (PC, 'sentinel-2-l2a', 'Microsoft Planetary Computer', 10),
         (PC, 'landsat-c2-l2', 'Microsoft Planetary Computer', 30)]
TOKEN_LOCK = threading.Lock()
TOKENS = {}
STARTED = time.monotonic()


def get(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'Powderline/1.0 (public resort imagery)'})
    with urllib.request.urlopen(req, timeout=25) as response:
        return response.read()


def date(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return result if result.tzinfo else None
    except (TypeError, ValueError, AttributeError):
        return None


def bounds(lat, lon):
    dy = 5 / 111.32
    dx = dy / math.cos(math.radians(lat))
    return [round(lon-dx, 6), round(lat-dy, 6), round(lon+dx, 6), round(lat+dy, 6)]


def candidates(items, now):
    # Prefer recency within a usable visibility threshold. Never choose future,
    # undated, or >30-day scenes; scene cloud estimates aren't local guarantees.
    return sorted([f for f in items if date(f.get('properties', {}).get('datetime')) and
                   timedelta(0) <= now-date(f['properties']['datetime']) <= timedelta(days=30) and
                   isinstance(f['properties'].get('eo:cloud_cover'), (int, float)) and
                   0 <= f['properties']['eo:cloud_cover'] <= 60],
                  key=lambda f: f['properties']['datetime'], reverse=True)


def search(host, collection, bbox, now):
    params = {'collections': collection, 'bbox': ','.join(map(str, bbox)), 'limit': 100,
              'datetime': (now-timedelta(days=30)).isoformat()+'/'+now.isoformat()}
    # Earth Search does not support the same sort extension as PC. Sort locally.
    payload = json.loads(get(host+'/search?'+urllib.parse.urlencode(params)))
    return candidates(payload.get('features', []), now)


def signed(href, host):
    if host != PC:
        return href
    parsed = urllib.parse.urlsplit(href)
    container = (parsed.netloc, parsed.path.split('/')[1])
    with TOKEN_LOCK:
        if container in TOKENS:
            return urllib.parse.urlunsplit(parsed._replace(query=TOKENS[container]))
        url = json.loads(get('https://planetarycomputer.microsoft.com/api/sas/v1/sign?'+
                             urllib.parse.urlencode({'href': href})))['href']
        token = urllib.parse.urlsplit(url).query
        # A container-scoped signature can be reused for other scene assets;
        # blob-scoped signatures cannot. Tokens stay private in process memory.
        if urllib.parse.parse_qs(token).get('sr') == ['c']:
            TOKENS[container] = token
        return url


def read_crop(href, bbox, host, size=640):
    import numpy as np
    import rasterio
    from rasterio.vrt import WarpedVRT
    from rasterio.transform import from_bounds
    from rasterio.enums import Resampling
    with rasterio.Env(GDAL_DISABLE_READDIR_ON_OPEN='EMPTY_DIR', GDAL_HTTP_TIMEOUT='15',
                      GDAL_HTTP_MAX_RETRY='1', VSI_CACHE=True):
        with rasterio.open(signed(href, host)) as src:
            with WarpedVRT(src, crs='EPSG:4326', transform=from_bounds(*bbox, size, size),
                           width=size, height=size, resampling=Resampling.nearest) as vrt:
                values = vrt.read(masked=True)
                valid = ~np.any(np.ma.getmaskarray(values), axis=0)
                return values.filled(0), valid


def render(item, bbox, host, collection):
    import numpy as np
    from PIL import Image
    assets = item['assets']
    landsat = collection == 'landsat-c2-l2'
    if landsat:
        channels, masks = zip(*(read_crop(assets[k]['href'], bbox, host) for k in ('red', 'green', 'blue')))
        rgb = np.concatenate(channels)
        # USGS Collection 2 surface-reflectance scaling, fixed across scenes.
        rgb = np.clip((rgb.astype(float)*0.0000275-0.2)/0.35*255, 0, 255).astype('uint8')
        valid = np.logical_and.reduce(masks) & np.any(rgb > 0, axis=0)
        qa, _ = read_crop(assets['qa_pixel']['href'], bbox, host)
        bad = (qa[0].astype('uint16') & sum(1 << b for b in (1, 2, 3, 4))) != 0
    else:
        rgb, valid = read_crop(assets['visual']['href'], bbox, host)
        rgb = rgb[:3].astype('uint8')
        valid &= np.any(rgb > 0, axis=0)
        scl, _ = read_crop(assets['SCL' if host == PC else 'scl']['href'], bbox, host)
        valid &= ~np.isin(scl[0], [0, 1])
        bad = np.isin(scl[0], [3, 8, 9, 10])
    coverage = float(valid.mean())
    obscured = float(bad[valid].mean()) if valid.any() else 1
    if coverage < .95 or obscured > .35:
        raise ValueError('Crop obscured or incomplete')
    output = BytesIO()
    Image.fromarray(np.moveaxis(rgb, 0, -1)).save(output, format='JPEG', quality=88)
    return output.getvalue(), round(obscured*100, 1)


def save_previous(entry, output, now):
    if not isinstance(entry, dict) or not date(entry.get('capturedAt')):
        return None
    if not timedelta(0) <= now-date(entry['capturedAt']) <= timedelta(days=30):
        return None
    path = entry.get('image', '')
    if not path.startswith('satellite/') or '..' in path or not path.endswith('.jpg'):
        return None
    data = get(PUBLIC+path)
    from PIL import Image
    Image.open(BytesIO(data)).verify()
    (output/path).write_bytes(data)
    return dict(entry)


def collect(name, location, previous, output, now):
    bbox = bounds(*location)
    # Reuse a checked crop for six hours across the existing half-hour workflow.
    if date(previous.get('checkedAt')) and timedelta(0) <= now-date(previous['checkedAt']) < timedelta(hours=6):
        try:
            saved = save_previous(previous, output, now)
            if saved:
                return saved
        except Exception:
            pass
    slug = ''.join(c if c.isalnum() else '-' for c in name.lower()).strip('-')
    for host, collection, provider, resolution in HOSTS:
        if time.monotonic()-STARTED > 260:
            break
        try:
            scenes = search(host, collection, bbox, now)
            # Bound remote window reads per resort and per provider.
            for item in scenes[:2]:
                if time.monotonic()-STARTED > 260:
                    break
                try:
                    image, cloud = render(item, bbox, host, collection)
                    path = f'satellite/{slug}.jpg'
                    (output/path).write_bytes(image)
                    return {'image': path, 'capturedAt': item['properties']['datetime'],
                            'checkedAt': now.isoformat(), 'sensor': 'Landsat 8/9' if resolution == 30 else 'Sentinel-2',
                            'provider': provider, 'resolutionM': resolution, 'obscuredPercent': cloud,
                            'bbox': bbox, 'sceneId': item['id'], 'source': host+'/collections/'+collection+'/items/'+item['id'],
                            'attribution': 'USGS / NASA Landsat' if resolution == 30 else 'Contains modified Copernicus Sentinel data',
                            'fallback': host != HOSTS[0][0] or resolution == 30}
                except Exception as error:
                    print(f'Satellite crop skipped: {name}: {type(error).__name__}', flush=True)
        except Exception as error:
            print(f'Satellite provider unavailable: {name}: {provider}: {type(error).__name__}', flush=True)
    try:
        saved = save_previous(previous, output, now)
        if saved:
            saved['retained'] = True
            return saved
    except Exception:
        pass
    return {'unavailable': True, 'checkedAt': now.isoformat(), 'bbox': bbox}


def build(output, only=None):
    now = datetime.now(timezone.utc)
    locations = json.loads((ROOT/'resort-locations.json').read_text())['resorts']
    if only:
        locations = {n: p for n, p in locations.items() if n in only}
    (output/'satellite').mkdir(parents=True, exist_ok=True)
    try:
        previous = json.loads(get(PUBLIC+'satellite.json')).get('resorts', {})
    except Exception:
        previous = {}
    resorts = {}
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(collect, n, p, previous.get(n, {}), output, now): n for n, p in locations.items()}
        for job in as_completed(jobs):
            name = jobs[job]
            try:
                resorts[name] = job.result()
            except Exception as error:
                resorts[name] = {'unavailable': True, 'checkedAt': now.isoformat()}
                print(f'Satellite unavailable: {name}: {type(error).__name__}', flush=True)
    payload = {'generatedAt': now.isoformat(), 'resorts': resorts}
    (output/'satellite.json').write_text(json.dumps(payload, separators=(',', ':'))+'\n')
    print(f'Satellite: {sum(bool(x.get("image")) for x in resorts.values())}/{len(resorts)} resort crops', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'_site')
    parser.add_argument('--resort', action='append')
    args = parser.parse_args()
    build(args.output, args.resort)
