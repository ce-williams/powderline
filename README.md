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

## Colorado camera coverage

The directory covers **34 Colorado ski areas**, including all four Aspen Snowmass mountains and the municipal hills. Each area appears in the resort selector even if a public camera could not be verified. Cameras are grouped by region.

- Camera images and click-to-load players are shown where a public source is available.
- Winter Park’s restricted players, Steamboat’s unverified offsite feeds, and other source-only cameras have explicit links to their official camera pages. They are counted separately from on-page views.
- Eldora’s official maintenance notice is shown. Ski areas without a verified public feed get a website link and an availability note rather than an invented camera.
- Initial image failures keep the camera card and official source link visible. Refresh retries failed previews and keeps the last successful image when a later request fails.
- A successfully loaded image may still be stale or contain a provider’s offline slate. “Image checked” records when the browser loaded it, not its capture time.
- Video players load only on request. Still images refresh every five minutes. CSP allows only the camera providers used by the catalog; external links use `noopener noreferrer`.

## Source integrity and validation

`camera-catalog.js` is the runtime source for both the resort directory and camera list. `source-registry.json` mirrors both lists with a review date and public provenance. Resort sources and HDRelay public camera configurations identify the listed views. No access-controlled or credential-bearing feeds are included.

Run `node --test tests/catalog.test.mjs` to validate statewide coverage, unique identifiers, HTTPS URLs, provider restrictions, CSP compatibility, and source-registry parity. The Pages workflow runs these checks before deploying and publishes only the site assets.

Resort snowfall, depth, weather, terrain, and lift totals stay blank until a timestamped source adapter is implemented. Road conditions link to COtrip; camera images do not establish road safety.

## Current implementation boundary

This first build is a static front end. It does not yet include a server-side provider layer, automated resort-report integration, or CDOT camera/incident feed access. The source registry identifies the checked camera embeds and the outstanding limits for those integrations.
