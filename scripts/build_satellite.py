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
import hashlib
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
ASSET_LOCK = threading.Lock()
ASSET_CACHE = {}


def asset_bytes(path):
    # Shared assets are fetched once even when several resort jobs retain them.
    with ASSET_LOCK:
        if path not in ASSET_CACHE:
            ASSET_CACHE[path] = get(PUBLIC+path)
        return ASSET_CACHE[path]


def encode_webp(image, size=None):
    from PIL import Image
    image = image.copy()
    if size:
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
    data = BytesIO()
    image.save(data, format='WEBP', quality=90, method=4)
    return data.getvalue()


def publish_images(resorts, output):
    """Keep each native crop separate; encode the full RGB pixels losslessly once."""
    from PIL import Image
    available = [(n, r) for n, r in resorts.items() if r.get('image') and r.get('bbox')]
    def write(data, prefix):
        path = 'satellite/'+prefix+'-'+hashlib.sha256(data).hexdigest()[:20]+'.webp'
        (output/path).write_bytes(data)
        return path
    for name, row in available:
        with Image.open(output/row['image']) as source:
            image = source.convert('RGB')
        native = BytesIO()
        image.save(native, format='WEBP', lossless=True, method=4)
        full = native.getvalue()
        row.update(image=write(full, 'detail'), thumbnail=write(encode_webp(image, 448), 'thumb'),
                   view=[0, 0, 1, 1], sharedWith=[name], imageBytes=len(full),
                   pixelWidth=image.width, pixelHeight=image.height)
        row['spanKm'] = round((row['bbox'][3]-row['bbox'][1])*111.32, 2)
        row['orientation'] = 'north-up'
    keep = {r[k] for _, r in available for k in ('image', 'thumbnail')}
    for path in (output/'satellite').iterdir():
        if 'satellite/'+path.name not in keep and path.is_file():
            path.unlink()
    full = {r['image'] for _, r in available}
    thumbs = {r['thumbnail'] for _, r in available}
    return {'resortCount': len(available), 'fullImageCount': len(full), 'encoding': 'lossless WebP',
            'fullImageBytes': sum((output/p).stat().st_size for p in full),
            'thumbnailBytes': sum((output/p).stat().st_size for p in thumbs)}


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


def bounds(lat, lon, span_km=5):
    dy = span_km / 2 / 111.32
    dx = dy / math.cos(math.radians(lat))
    return [round(lon-dx, 6), round(lat-dy, 6), round(lon+dx, 6), round(lat+dy, 6)]


def resort_bounds(name, location):
    """Frame the selected lift corridors with padding; keep at least 5 km context."""
    try:
        routes = json.loads((ROOT/'lift-routes.json').read_text())['resorts'].get(name, {}).get('routes', [])
    except (OSError, ValueError):
        routes = []
    points = [c for r in routes for c in r.get('coordinates', [])]
    if not points:
        return bounds(*location)
    west, east = min(c[0] for c in points), max(c[0] for c in points)
    south, north = min(c[1] for c in points), max(c[1] for c in points)
    lat, lon = (south+north)/2, (west+east)/2
    span = max(5, (north-south)*111.32+1.2, (east-west)*111.32*math.cos(math.radians(lat))+1.2)
    return bounds(lat, lon, span)


def native_size(bbox, resolution):
    return max(1, math.ceil((bbox[3]-bbox[1])*111320/resolution))


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
    size = native_size(bbox, 30 if landsat else 10)
    if landsat:
        channels, masks = zip(*(read_crop(assets[k]['href'], bbox, host, size=size) for k in ('red', 'green', 'blue')))
        rgb = np.concatenate(channels)
        # USGS Collection 2 surface-reflectance scaling, fixed across scenes.
        rgb = np.clip((rgb.astype(float)*0.0000275-0.2)/0.35*255, 0, 255).astype('uint8')
        valid = np.logical_and.reduce(masks) & np.any(rgb > 0, axis=0)
        qa, _ = read_crop(assets['qa_pixel']['href'], bbox, host, size=size)
        bad = (qa[0].astype('uint16') & sum(1 << b for b in (1, 2, 3, 4))) != 0
    else:
        rgb, valid = read_crop(assets['visual']['href'], bbox, host, size=size)
        rgb = rgb[:3].astype('uint8')
        valid &= np.any(rgb > 0, axis=0)
        scl, _ = read_crop(assets['SCL' if host == PC else 'scl']['href'], bbox, host, size=size)
        valid &= ~np.isin(scl[0], [0, 1])
        bad = np.isin(scl[0], [3, 8, 9, 10])
    coverage = float(valid.mean())
    obscured = float(bad[valid].mean()) if valid.any() else 1
    if coverage < .95 or obscured > .35:
        raise ValueError('Crop obscured or incomplete')
    output = BytesIO()
    Image.fromarray(np.moveaxis(rgb, 0, -1)).save(output, format='PNG')
    return output.getvalue(), round(obscured*100, 1)


def save_previous(entry, output, now):
    if not isinstance(entry, dict) or not date(entry.get('capturedAt')):
        return None
    if not timedelta(0) <= now-date(entry['capturedAt']) <= timedelta(days=30):
        return None
    path = entry.get('image', '')
    if not path.startswith('satellite/') or '..' in path or not path.endswith(('.jpg', '.webp')):
        return None
    data = asset_bytes(path)
    from PIL import Image
    saved = dict(entry)
    with Image.open(BytesIO(data)) as image:
        view = entry.get('view', [0, 0, 1, 1])
        x, y, w, h = view
        crop = image.crop((round(x*image.width), round(y*image.height), round((x+w)*image.width), round((y+h)*image.height))).convert('RGB')
        # Intermediate raw view; the final publication uses content-addressed WebP.
        path = 'satellite/retained-'+hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()[:20]+'.png'
        crop.save(output/path, format='PNG')
    saved.update(image=path, view=[0, 0, 1, 1])
    return saved


def collect(name, location, previous, output, now):
    bbox = resort_bounds(name, location)
    # Reuse a checked crop for six hours across the existing half-hour workflow.
    if previous.get('qualityProfile') == 'native-individual-v1' and previous.get('bbox') == bbox and date(previous.get('checkedAt')) and timedelta(0) <= now-date(previous['checkedAt']) < timedelta(hours=6):
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
                    path = f'satellite/{slug}.png'
                    (output/path).write_bytes(image)
                    return {'image': path, 'capturedAt': item['properties']['datetime'],
                            'checkedAt': now.isoformat(), 'qualityProfile': 'native-individual-v1', 'sensor': 'Landsat 8/9' if resolution == 30 else 'Sentinel-2',
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
        previous_manifest = json.loads(get(PUBLIC+'satellite.json'))
        previous = previous_manifest.get('resorts', {})
    except Exception:
        previous_manifest, previous = {}, {}
    # Most half-hour builds copy unchanged individual detail images and previews.
    # Preserve their exact compressed bytes; never recompress cached images.
    if previous_manifest.get('schemaVersion') == 3 and set(previous) == set(locations) and all(
            r.get('qualityProfile') == 'native-individual-v1' and r.get('bbox') == resort_bounds(n, locations[n]) and
            r.get('image') and date(r.get('capturedAt')) and timedelta(0) <= now-date(r['capturedAt']) <= timedelta(days=30) and
            date(r.get('checkedAt')) and timedelta(0) <= now-date(r['checkedAt']) < timedelta(hours=6) for n, r in previous.items()):
        try:
            paths = {r[k] for r in previous.values() for k in ('image', 'thumbnail')}
            with ThreadPoolExecutor(max_workers=4) as pool:
                for path, data in pool.map(lambda p: (p, get(PUBLIC+p)), sorted(paths)):
                    if not path.startswith('satellite/') or '..' in path or not path.endswith('.webp'):
                        raise ValueError('Invalid cached image path')
                    from PIL import Image
                    Image.open(BytesIO(data)).verify()
                    (output/path).write_bytes(data)
            previous_manifest['generatedAt'] = now.isoformat()
            for row in previous.values():
                row['orientation'] = 'north-up'
            (output/'satellite.json').write_text(json.dumps(previous_manifest, separators=(',', ':'))+'\n')
            print(f'Satellite: reused {len(previous)} resort views from {len(paths)} cached assets', flush=True)
            return
        except Exception:
            pass
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
    stats = publish_images(resorts, output)
    payload = {'schemaVersion': 3, 'generatedAt': now.isoformat(), 'resorts': resorts, 'storage': stats}
    (output/'satellite.json').write_text(json.dumps(payload, separators=(',', ':'))+'\n')
    print(f'Satellite: {sum(bool(x.get("image")) for x in resorts.values())}/{len(resorts)} resort crops', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'_site')
    parser.add_argument('--resort', action='append')
    args = parser.parse_args()
    build(args.output, args.resort)
