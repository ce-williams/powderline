#!/usr/bin/env python3
"""Collect public resort measurements alongside the scheduled camera batch."""
import argparse
import html as html_lib
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parent.parent
COLORADO_FEED = 'https://snow.coloradoski.com/view/publicreport-feed'
COLORADO_SOURCE = 'https://www.coloradoski.com/snow-report/'
PUBLIC_REPORTS = 'https://ce-williams.github.io/powderline/snow-reports.json'
VAIL_SOURCES = {
    'Vail': 'https://www.vail.com/the-mountain/mountain-conditions/snow-and-weather-report.aspx',
    'Beaver Creek': 'https://www.beavercreek.com/the-mountain/mountain-conditions/snow-and-weather-report.aspx',
    'Breckenridge': 'https://www.breckenridge.com/the-mountain/mountain-conditions/snow-and-weather-report.aspx',
    'Keystone': 'https://www.keystoneresort.com/the-mountain/mountain-conditions/snow-and-weather-report.aspx',
    'Crested Butte': 'https://www.skicb.com/the-mountain/mountain-conditions/weather-report.aspx',
}
ALIASES = {'Cooper': 'Ski Cooper', 'Monarch': 'Monarch Mountain', 'Silverton': 'Silverton Mountain',
           'Purgatory Resort': 'Purgatory', 'Sunlight Mountain Resort': 'Sunlight Mountain'}
FIELDS = ('snow24', 'snow48', 'snow7', 'depth', 'liftsOpen', 'liftsTotal')


def fetch(url):
    # Use curl's normal HTTPS client; no browser challenge solving or private APIs.
    result = subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error',
                             '--max-time', '25', url], check=True, capture_output=True, text=True, timeout=30)
    return result.stdout



def number(value):
    # Empty, trace, unknown, and missing must not become a measured zero.
    if isinstance(value, bool) or value is None:
        return None
    if not re.fullmatch(r'\d+(?:\.\d+)?', str(value).strip()):
        return None
    result = float(str(value).strip())
    return result if 0 <= result <= 2000 else None


def iso_date(value):
    try:
        date = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return date.isoformat() if date.tzinfo else None
    except (ValueError, TypeError, AttributeError):
        return None


def parse_colorado(payload, fetched_at):
    result = {}
    if not isinstance(payload.get('open_resorts'), list) or not isinstance(payload.get('closed_resorts'), list):
        raise ValueError('Colorado report feed schema changed')
    for row in payload['open_resorts'] + payload['closed_resorts']:
        resort, snow = row['resort'], row.get('snow_report') or {}
        name = ALIASES.get(resort['resort_title'], resort['resort_title'])
        result[name] = {
            'source': COLORADO_SOURCE, 'sourceName': 'Colorado Ski Country USA',
            'fetchedAt': fetched_at, 'reportedAt': iso_date(snow.get('updated')),
            'snow24': number(snow.get('snow_total_24_hour')),
            'snow48': number(snow.get('snow_total_48_hour')),
            'snow7': None, 'depth': number(snow.get('mid_mountain_snow_depth')),
            'depthLabel': 'MID-MTN',
            'liftsOpen': number(snow.get('open_lifts')),
            'liftsTotal': number(snow.get('available_lifts', resort.get('available_lifts'))),
            'surfacePrimary': str(snow.get('surface_conditions') or '')[:200],
            'surfaceSecondary': str(snow.get('secondary_surface_conditions') or '')[:200],
            'conditionsText': html_lib.unescape(re.sub(r'<[^>]+>', ' ', str(snow.get('resort_conditions') or '')))[:4000],
        }
    return result


def parse_vail(html, source, fetched_at):
    match = re.search(r'FR\.snowReportData\s*=\s*', html)
    if not match:
        raise ValueError('Resort report data missing')
    data, _ = json.JSONDecoder().raw_decode(html[match.end():])
    stamp = data.get('LastUpdatedText', '')
    date_match = re.search(r'Updated (\w+ \d{1,2}, \d{4} at \d{1,2}:\d{2} [AP]M) (MDT|MST)', stamp)
    if not date_match:
        raise ValueError('Resort report timestamp missing')
    # The source supplies the Mountain-time offset explicitly, including DST.
    offset = -6 if date_match[2] == 'MDT' else -7
    reported = datetime.strptime(date_match[1], '%B %d, %Y at %I:%M %p').replace(tzinfo=timezone(timedelta(hours=offset)))
    result = {'source': source, 'sourceName': 'Official resort report', 'fetchedAt': fetched_at,
              'reportedAt': reported.isoformat(), 'depthLabel': 'BASE', 'liftsOpen': None, 'liftsTotal': None,
              'overallConditions': str(data.get('OverallSnowConditions') or '')[:200]}
    for key, source_key in [('snow24', 'TwentyFourHourSnowfall'), ('snow48', 'FortyEightHourSnowfall'),
                            ('snow7', 'SevenDaySnowfall'), ('depth', 'BaseDepth')]:
        result[key] = number((data.get(source_key) or {}).get('Inches'))
    return result


def retain(previous, source, now):
    """Keep provenance on transient failures; a successful empty report clears old stats."""
    if not isinstance(previous, dict) or previous.get('source') != source:
        return None
    fetched = iso_date(previous.get('fetchedAt'))
    if not fetched or not timedelta(0) <= now - datetime.fromisoformat(fetched) <= timedelta(days=7):
        return None
    result = dict(previous)
    result['retained'] = True
    return result


def build(output):
    now = datetime.now(timezone.utc)
    stamp = now.isoformat()
    catalog = json.loads((ROOT / 'source-registry.json').read_text())['resorts']
    try:
        previous = json.loads(fetch(PUBLIC_REPORTS)).get('resorts', {})
    except Exception:
        previous = {}
    reports = {row['name']: {'source': row['source'], 'sourceName': 'Resort website', 'unavailable': True} for row in catalog}
    jobs = {'colorado': COLORADO_FEED, **VAIL_SOURCES}
    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = {pool.submit(fetch, url): name for name, url in jobs.items()}
        for future in as_completed(futures):
            name = futures[future]
            try:
                raw = future.result()
                entries = parse_colorado(json.loads(raw), stamp) if name == 'colorado' else {name: parse_vail(raw, jobs[name], stamp)}
                for resort, report in entries.items():
                    if resort in reports:
                        reports[resort] = report
            except Exception as error:
                print(f'Snow report unavailable: {name}: {error}')
                names = [key for key, value in previous.items() if value.get('source') == COLORADO_SOURCE] if name == 'colorado' else [name]
                source = COLORADO_SOURCE if name == 'colorado' else jobs[name]
                for resort in names:
                    saved = retain(previous.get(resort), source, now)
                    if saved and resort in reports:
                        reports[resort] = saved
    # Undated measurements cannot be presented as a current report.
    for report in reports.values():
        if not report.get('reportedAt'):
            for field in FIELDS:
                report[field] = None
    manifest = {'generatedAt': stamp, 'resorts': reports}
    output.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(manifest, ensure_ascii=True, separators=(',', ':'))
    (output / 'snow-reports.json').write_text(encoded + '\n')
    (output / 'snow-reports.js').write_text('window.powderlineSnowReports = ' + encoded + ';\n')
    print(f'Snow reports: {sum(bool(r.get("reportedAt")) for r in reports.values())} dated reports / {len(reports)} ski areas')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path, default=ROOT / '_site')
    build(parser.parse_args().output)
