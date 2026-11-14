# POWDERLINE

A Colorado mountain camera wall and conditions-planning interface.

## Run locally

This initial version is a dependency-free static app. From this directory, run:

```sh
python3 -m http.server 4173
```

Then open `http://localhost:4173`.

## Publish with GitHub Pages

The app is plain HTML, CSS, and JavaScript, with relative asset paths so it works at a repository subpath such as `https://ACCOUNT.github.io/REPOSITORY/`.

1. In the repository, open **Settings → Pages**.
2. Under **Build and deployment**, select **GitHub Actions** as the source.
3. Push changes to `main`; `.github/workflows/pages.yml` publishes the static site automatically.
4. After the first successful deployment, enable **Enforce HTTPS** in the same settings area if it is not already on.

## Hourly camera snapshots

The directory covers **34 Colorado ski areas**, grouped by geography. GitHub Actions captures images at **17 minutes past each hour**, and on pushes or manual workflow runs. Scheduled runs can be delayed by GitHub. No new hosting account or API key is needed.

- The site serves captured JPEGs from its own `snapshots/` directory, immediately when a tile is visible. Video players remain optional.
- Winter Park and six active Steamboat cameras use their camera-specific public video preview images, labeled **Source preview**. These are provider thumbnails, not a guarantee of a current live frame.
- Source image endpoints are preferred. Public player pages are used for cameras without a snapshot endpoint, capturing only ready video elements or explicitly configured camera images. Browser challenges, login screens, and error pages are never captured as cameras.
- A failed source refresh downloads and preserves the last-good image from the previous public deployment. The original fetch timestamp stays unchanged. A zero-image batch aborts publication.
- Tiles show **Fetched … ago**. Failed refreshes or images older than two hours say **Last good image**. Provider image capture time may differ from fetch time; identical image hashes preserve a separate last-changed timestamp.
- Refresh loads the latest published batch; it does not trigger a new capture. Open pages check for a new manifest every 15 minutes. Owners can start a batch from GitHub Actions using **Run workflow**.
- Images and manifests are deployment artifacts, excluded from Git history. The runtime catalogs and source provenance remain in Git.
- Resort options show captured-image counts separately from camera listings (for example, Steamboat’s six available previews out of seven listed cameras). Thunderhead is explicitly marked down by the resort.
- Ski areas without a public camera retain a website link. Cameras that cannot be captured retain an explicit availability note and official source link.

The collector is `scripts/build_snapshots.py`; `snapshot-sources.json` maps cameras requiring rendered-player capture. `snapshot-manifest.js` is an empty seed in Git and is replaced with the captured manifest during deployment. The public JSON manifest is `snapshots/manifest.json`.

For a local snapshot preview, install `requirements-snapshots.txt`, assemble `_site`, and run `python scripts/build_snapshots.py --output _site --skip-browser`. Serve `_site` with `python -m http.server 4174 --directory _site`. Omit `--skip-browser` in the deployment to include public-player captures.

## Source integrity and validation

`camera-catalog.js` is the runtime source for both the resort directory and camera list. `source-registry.json` mirrors both lists with a review date and public provenance. Resort sources and HDRelay public camera configurations identify the listed views. No access-controlled or credential-bearing feeds are included.

Run `node --test tests/*.test.mjs` and `python -m unittest discover -s tests -p 'test_*.py'` to validate statewide coverage, unique identifiers, HTTPS URLs, provider restrictions, CSP compatibility, and source-registry parity. The Pages workflow runs these checks before deploying and publishes only the site assets.

Each camera tile shows resort-reported 24-hour, 48-hour, seven-day snowfall and base or mid-mountain depth in inches, plus lifts open when supplied. `scripts/build_snow_reports.py` collects the public Colorado Ski Country USA JSON feed and public Vail, Beaver Creek, Breckenridge, Keystone, and Crested Butte report pages in the same Pages build. Measurements require a source reporting timestamp; missing/trace values stay blank and numeric zero stays zero. Reports older than 36 hours are marked; measurements older than seven days are hidden. Closed areas without dated measurements show an explicit awaiting-report state. Source failures retain the prior report for up to seven days without changing its timestamps. Successful empty reports clear prior measurements. Reports are served from same-origin `snow-reports.json` with a generated JS seed and refresh with the camera wall. Road conditions link to COtrip; camera images do not establish road safety.

## Current implementation boundary

The front end remains static; scheduled jobs collect and publish camera snapshots. It does not include an unauthenticated capture-trigger API, CDOT camera/incident feed access. Unavailable providers remain explicitly labeled.

### Browser QA — 2026-10-22

The entire published wall was scrolled and visually inspected in Chromium: all 92 cached image requests loaded, but Monarch Pioneer Top was a scheduled-offline graphic. That graphic is now rejected both during collection and last-good retention. A regression test checks the original graphic, JPEG recompression, and a legitimate black nighttime frame.

Clicking Sunlight’s in-page player reproduced an unsupported-playback error that covered a valid snapshot. The wall now displays cached images only; optional live sources open separately. No iframe load event is treated as evidence of playable video. Unavailable cameras and ski areas without verified feeds remain listed under expandable regional status sections, which open when that resort is selected.

The Breckenridge snow-stake embed fails on the official resort page, Telluride’s two powder-camera frames return 404, and Steamboat marks Thunderhead down. These are labeled as unavailable rather than counted as working images. Foggy views remain valid camera images.

The expand control uses an accessible in-page image dialog, with Close, Escape, and backdrop dismissal, so denied fullscreen permissions do not break the action.

### Freshness follow-up — 2026-10-22

The hourly GitHub scheduler left a gap exceeding four hours between the last published batch and the live check. Collections now request two runs per hour, at minutes 13 and 43, and the UI describes this as best-effort. A batch older than 90 minutes displays an overdue banner. The page checks the published manifest on opening, returning to the tab, every five minutes, and manual Refresh. Provider previews explicitly show that capture time is unknown; images that have not changed for more than two hours carry an unchanged-source label. Refresh cannot force a source camera to update or trigger GitHub from this public static page.

A direct browser source check also found Telluride Revelation Bowl explicitly offline, with an April 11, 2026 archive in its public viewer. Its collection and retention are disabled until a source review confirms current imagery. Loveland Lift 9’s unchanged public still remains labeled with its unchanged age.

### Independent freshness watchdog — 2026-10-28

GitHub scheduled runs continued to arrive 5–6 hours apart despite the 30-minute request. `python3 -B scripts/check_feed_freshness.py` reports the published batch's age and the current Pages workflow state. Add `--refresh` to dispatch the existing workflow when the batch is older than 40 minutes and no build is active. It uses existing `gh` authentication, never stores credentials, and reports builds older than 20 minutes as stalled instead of piling up duplicate jobs.

An active app heartbeat named **Powderline feed freshness watchdog** checks every 30 minutes in the original project chat. It verifies recovery after dispatch and reports failures. This backup requires the local computer and app to stay running; the GitHub schedule remains enabled when the local backup is unavailable. A server-hosted independent scheduler is still needed for an always-on freshness guarantee.
# Satellite imagery and resort conditions

The satellite section defaults to an all-resort regional gallery. Up to 448 px
WebP previews load lazily; individual full images load on resort selection.
Full images are framed around up to three selected main lift routes, with a
minimum 5 km square and 600 m padding beyond lift extents. Sentinel crops use
approximately one output pixel per 10 m; Landsat crops use one per 30 m. Full
RGB imagery goes through a lossless PNG intermediate and lossless WebP, without
JPEG recompression, forced 640 px resizing, or shared regional atlases. Digital
zoom cannot reveal detail finer than the satellite sensor captured.

Full images and previews use content hashes so unchanged imagery keeps stable
URLs across deployments. A complete recent collection copies each cached asset
once without re-encoding; imagery checks remain on the existing workflow and
reuse crops for six hours. Schema 3 invalidates earlier broad, compressed views.
Failed collection may retain an earlier view, labeled with its quality and age.
All images expire after 30 days. Cloud/invalid-data checks still apply.

`lift-routes.json` contains a small, attributed derivative of OpenSkiData / OSM,
served publicly under ODbL. The map-data timestamp is independent of image
capture time. The UI projects those longitude/latitude polylines onto the crop
and keeps them aligned during zoom and expansion. A consistent north-up / east-right compass appears on square gallery previews,
resort views and expanded images. A single primary lift/gondola is drawn in red
and labeled by name directly on the map. Its label stays tied to the visible
route during zoom. A toggle hides the line, and the source link remains below. Resort
membership comes from upstream ski-area associations, not nearest-neighbor
assignment. Preferred named trunk lifts are selected where known, then longest
major aerialways fill the remaining slots. This is a subset of lift
infrastructure, not daily operating status. Disused/proposed routes are excluded.
Hoedown currently has no eligible routes in the upstream dataset.

Refresh the small route extract manually when needed (no new schedule):

```sh
# Respect OpenSkiData's maximum of one automated download per day.
curl --compressed -o /tmp/lifts.geojson https://tiles.openskimap.org/geojson/lifts.geojson
# Read the upstream metadata.json openStreetMap.dataTimestamp for --source-date.
python3 -B scripts/import_lift_routes.py --input /tmp/lifts.geojson --source-date <upstream-timestamp>
```

The existing Pages workflow publishes `satellite.json`, individual WebP assets
in `satellite/`, `lift-routes.json`, and `conditions.json`. Imagery comes directly
from Sentinel-2 Level-2A on Earth Search, with Planetary Computer and Landsat
fallbacks; it does not use CalTopo's licensed tiles. Geometry is approximate and
does not define resort or trail boundaries. NASA Worldview is linked for coarser
regional context. No imagery API key is required.

Conditions combine dated Colorado Ski Country USA / official resort reports
with the National Weather Service hourly point forecast. Primary and secondary
surface fields are retained, along with resort notes for terrain/elevation
nuance. Same-day means America/Denver; older reports remain dated and expire
after 72 hours. Forecasts expire after 18 hours. Forecast temperatures crossing
freezing are labeled as a possibility, never a confirmed surface texture.
Missing, future-dated and expired evidence is excluded. A new collection time
does not refresh the source's report or image acquisition time.

For automatically generated AI prose, add **`OPENAI_API_KEY`** as a GitHub
Actions repository secret. Optionally set repository variable
**`POWDERLINE_AI_MODEL`** (default `gpt-4.1-mini`, Responses API with strict JSON
output). The key is available only to the build step, never to browser assets.
The generator sends only the public evidence bundle, disables response storage,
requires known source IDs, rejects unsupported surface terminology, and reuses
unchanged AI output for up to six hours. AI can still make mistakes: the UI
shows its dated inputs and the original resort notes. Missing keys, rejected
output, refusal, rate limits and provider failures use an explicitly labeled
source-based fallback; that fallback is not described as AI-generated. No
production AI calls have been verified without a configured secret.

OpenSnow and Slopes are external reading links only. OpenSnow's terms prohibit
scraping and derivative use without permission; licensed provider integration
can be added separately. No private endpoints, paywall bypass, social posts or
anonymous reports are used as current conditions evidence.

References:

- [CalTopo live satellite layers](https://training.caltopo.com/all_users/base-layers/layers)
- [Earth Search source and collections](https://github.com/Element84/earth-search)
- [Planetary Computer signing](https://planetarycomputer.microsoft.com/docs/concepts/sas/)
- [USGS Landsat scaling](https://www.usgs.gov/faqs/how-do-i-use-a-scale-factor-landsat-level-2-science-products)
- [NWS API](https://www.weather.gov/documentation/services-web-api)
- [OpenAI structured output](https://developers.openai.com/api/docs/guides/structured-outputs)
- [OpenSnow terms](https://support.opensnow.com/legal/terms)

Local collection:

```sh
python3 -B scripts/build_snow_reports.py --output _site
python3 -B scripts/build_satellite.py --output _site
python3 -B scripts/build_conditions.py --output _site
```

Satellite and conditions collectors accept repeated `--resort 'Copper Mountain'`
arguments for focused previews. Install `requirements-snapshots.txt` first.
