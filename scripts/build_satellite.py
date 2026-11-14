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


def union_bbox(rows):
    return [min(r['bbox'][0] for r in rows), min(r['bbox'][1] for r in rows),
            max(r['bbox'][2] for r in rows), max(r['bbox'][3] for r in rows)]


def crop_view(bbox, atlas):
    """Normalized top-left window; longitude rightward, latitude downward."""
    return [(bbox[0]-atlas[0])/(atlas[2]-atlas[0]), (atlas[3]-bbox[3])/(atlas[3]-atlas[1]),
            (bbox[2]-bbox[0])/(atlas[2]-atlas[0]), (bbox[3]-bbox[1])/(atlas[3]-atlas[1])]


def encode_webp(image, size=None):
    from PIL import Image
    image = image.copy()
    if size:
        image.thumbnail((size, size), Image.Resampling.LANCZOS)
    data = BytesIO()
    image.save(data, format='WEBP', quality=82, method=4)
    return data.getvalue()


def publish_images(resorts, output):
    """Deduplicate overlapping same-scene windows only when the bytes improve.

    Compose georeferenced, already validated crops from the SAME acquisition.
    Gaps outside resort windows stay black and are never shown in resort views.
    Preserve each local crop's ~640px detail instead of stretching a tiny region.
    """
    from PIL import Image
    available = [(n, r) for n, r in resorts.items() if r.get('image') and r.get('bbox')]
    baseline = sum((output/r['image']).stat().st_size for _, r in available)
    images, singles = {}, {}
    def write(data, prefix):
        path = 'satellite/'+prefix+'-'+hashlib.sha256(data).hexdigest()[:20]+'.webp'
        (output/path).write_bytes(data)
        return path
    for name, row in available:
        with Image.open(output/row['image']) as image:
            images[name] = image.convert('RGB').resize((640, 640), Image.Resampling.LANCZOS)
        singles[name] = encode_webp(images[name])
        row['thumbnail'] = write(encode_webp(images[name], 256), 'thumb')
    groups = []
    for name, row in sorted(available):
        chosen = None
        for group in groups:
            if any(date(resorts[n]['capturedAt']) != date(row['capturedAt']) or
                   resorts[n]['sensor'] != row['sensor'] or resorts[n]['provider'] != row['provider'] for n in group):
                continue
            members = [resorts[n] for n in group]+[row]
            box = union_bbox(members)
            # Keep regional downloads bounded and require overlapping coverage.
            area = (box[2]-box[0])*(box[3]-box[1])
            total = sum((r['bbox'][2]-r['bbox'][0])*(r['bbox'][3]-r['bbox'][1]) for r in members)
            if area < 1.05*total and box[2]-box[0] < .24 and box[3]-box[1] < .19:
                chosen = group
                break
        if chosen is None:
            groups.append([name])
        else:
            chosen.append(name)
    shared = 0
    for group in groups:
        rows = [resorts[n] for n in group]
        box = union_bbox(rows)
        views = {n: crop_view(resorts[n]['bbox'], box) for n in group}
        if len(group) > 1:
            width = math.ceil(max(640/v[2] for v in views.values()))
            height = math.ceil(max(640/v[3] for v in views.values()))
            atlas = Image.new('RGB', (width, height))
            for name in group:
                x, y, w, h = views[name]
                rect = [round(x*width), round(y*height), round((x+w)*width), round((y+h)*height)]
                atlas.paste(images[name].resize((rect[2]-rect[0], rect[3]-rect[1]), Image.Resampling.LANCZOS), rect[:2])
            encoded = encode_webp(atlas)
            if len(encoded) < .95*sum(len(singles[n]) for n in group):
                path = write(encoded, 'region')
                for name in group:
                    resorts[name].update(image=path, view=[round(v, 8) for v in views[name]], sharedWith=group, imageBytes=len(encoded))
                shared += 1
                continue
        for name in group:
            resorts[name].update(image=write(singles[name], 'scene'), view=[0, 0, 1, 1], sharedWith=[name], imageBytes=len(singles[name]))
    # Remove intermediate JPEGs and old assets after all views have been encoded.
    keep = {r[k] for _, r in available for k in ('image', 'thumbnail')}
    for path in (output/'satellite').iterdir():
        if 'satellite/'+path.name not in keep and path.is_file():
            path.unlink()
    full = {r['image'] for _, r in available}
    thumbs = {r['thumbnail'] for _, r in available}
    return {'resortCount': len(available), 'fullImageCount': len(full), 'sharedRegionCount': shared,
            'inputCropJpegBytes': baseline, 'unsharedWebpBytes': sum(len(data) for data in singles.values()),
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
        path = 'satellite/retained-'+hashlib.sha256(json.dumps(entry, sort_keys=True).encode()).hexdigest()[:20]+'.jpg'
        crop.save(output/path, format='JPEG', quality=95)
    saved.update(image=path, view=[0, 0, 1, 1])
    return saved


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
        previous_manifest = json.loads(get(PUBLIC+'satellite.json'))
        previous = previous_manifest.get('resorts', {})
    except Exception:
        previous_manifest, previous = {}, {}
    # Most half-hour builds only copy a small set of unchanged regional assets.
    # Preserve their exact compressed bytes; never recompress cached images.
    if previous_manifest.get('schemaVersion') == 2 and set(previous) == set(locations) and all(
            r.get('image') and date(r.get('capturedAt')) and timedelta(0) <= now-date(r['capturedAt']) <= timedelta(days=30) and
            date(r.get('checkedAt')) and timedelta(0) <= now-date(r['checkedAt']) < timedelta(hours=6) for r in previous.values()):
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
    payload = {'schemaVersion': 2, 'generatedAt': now.isoformat(), 'resorts': resorts, 'storage': stats}
    (output/'satellite.json').write_text(json.dumps(payload, separators=(',', ':'))+'\n')
    print(f'Satellite: {sum(bool(x.get("image")) for x in resorts.values())}/{len(resorts)} resort crops', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT/'_site')
    parser.add_argument('--resort', action='append')
    args = parser.parse_args()
    build(args.output, args.resort)
