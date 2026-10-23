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

Resort snowfall, depth, weather, terrain, and lift totals stay blank until a timestamped source adapter is implemented. Road conditions link to COtrip; camera images do not establish road safety.

## Current implementation boundary

The front end remains static; scheduled jobs collect and publish camera snapshots. It does not include an unauthenticated capture-trigger API, automated resort-report integration, or CDOT camera/incident feed access. Unavailable providers remain explicitly labeled.

### Browser QA — 2026-10-22

The entire published wall was scrolled and visually inspected in Chromium: all 92 cached image requests loaded, but Monarch Pioneer Top was a scheduled-offline graphic. That graphic is now rejected both during collection and last-good retention. A regression test checks the original graphic, JPEG recompression, and a legitimate black nighttime frame.

Clicking Sunlight’s in-page player reproduced an unsupported-playback error that covered a valid snapshot. The wall now displays cached images only; optional live sources open separately. No iframe load event is treated as evidence of playable video. Unavailable cameras and ski areas without verified feeds remain listed under expandable regional status sections, which open when that resort is selected.

The Breckenridge snow-stake embed fails on the official resort page, Telluride’s two powder-camera frames return 404, and Steamboat marks Thunderhead down. These are labeled as unavailable rather than counted as working images. Foggy views remain valid camera images.

The expand control uses an accessible in-page image dialog, with Close, Escape, and backdrop dismissal, so denied fullscreen permissions do not break the action.

### Freshness follow-up — 2026-10-22

The hourly GitHub scheduler left a gap exceeding four hours between the last published batch and the live check. Collections now request two runs per hour, at minutes 13 and 43, and the UI describes this as best-effort. A batch older than 90 minutes displays an overdue banner. The page checks the published manifest on opening, returning to the tab, every five minutes, and manual Refresh. Provider previews explicitly show that capture time is unknown; images that have not changed for more than two hours carry an unchanged-source label. Refresh cannot force a source camera to update or trigger GitHub from this public static page.

A direct browser source check also found Telluride Revelation Bowl explicitly offline, with an April 11, 2026 archive in its public viewer. Its collection and retention are disabled until a source review confirms current imagery. Loveland Lift 9’s unchanged public still remains labeled with its unchanged age.
