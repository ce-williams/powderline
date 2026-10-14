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

## Camera loading and privacy

- The camera catalog includes every camera listed on the five resorts' official camera pages as of the review date. Use the resort selector to narrow the wall.
- Video players are loaded as camera tiles approach the viewport, avoiding a burst of 25 simultaneous video embeds. Open the player or resort page from the tile caption if the embed is blank.
- A slow iframe is left visible rather than being removed after a fixed timeout. The embedded player reports its own stream state; the parent page does not claim to verify cross-origin video playback.
- Keystone's official still image is checked by the browser and removed if its image request fails. It is refreshed on the source's five-minute cadence.
- A Content Security Policy in `index.html` limits scripts and styles to this site, frames to Brownrice and the Breckenridge time-lapse host, and the Keystone image to its source host. External fonts are not requested.
- External links that open a new tab use `noopener noreferrer`.

## Source integrity

- The camera wall embeds every currently listed resort camera directly. Resort-page and direct-player links are provided as fallbacks.
- An explicit iframe request error or a failed image request removes that camera tile. A slow iframe is not hidden just because its load event was delayed.
- `camera-catalog.js` provides the runtime camera list; `source-registry.json` records the same official camera URLs and any known source limitations.
- The catalog review date is not a promise that a camera will stay available. Provider streams can go offline later.
- Keystone documents a five-minute refresh for its still-image snow stake. The app re-fetches it on that cadence and hides it if the image request fails.
- Resort snowfall, depth, weather, terrain, and lift totals are intentionally blank until a timestamped source adapter is implemented. No demo or inferred conditions are included.
- Road conditions are linked to COtrip. No road safety state is inferred from camera imagery.

## Current implementation boundary

This first build is a static front end. It does not yet include a server-side provider layer, automated resort-report integration, or CDOT camera/incident feed access. The source registry identifies the checked camera embeds and the outstanding limits for those integrations.
