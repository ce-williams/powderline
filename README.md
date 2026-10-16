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

- The camera catalog covers eight Colorado resorts. Use the resort selector to narrow the wall.
- Brownrice video cameras show the latest poster JPEG exposed by their player. Video iframes load only when selected, and the viewer can return to the still image if playback fails. The browser checks that each image loads before showing its camera card.
- Still images refresh every five minutes. A failed refresh keeps the last image that loaded successfully during the current visit. A first-load failure hides the camera card.
- The Breckenridge snow stake time-lapse is omitted while its provider has an invalid HTTPS certificate.
- A Content Security Policy in `index.html` limits scripts and styles to this site, frames to Brownrice, and images to the listed camera hosts. External fonts are not requested.
- External links that open a new tab use `noopener noreferrer`.

## Source integrity

- The camera wall links each listed view to its player and resort page. Cross-origin video playback cannot be verified by the parent page.
- `camera-catalog.js` provides the runtime camera list; `source-registry.json` records the same official camera URLs and any known source limitations.
- The catalog review date is not a promise that a camera will stay available. Provider streams can go offline later.
- The app refreshes visible stills and Brownrice posters on a five-minute cadence without replacing a successfully loaded image when a new request fails.
- Resort snowfall, depth, weather, terrain, and lift totals are intentionally blank until a timestamped source adapter is implemented. No demo or inferred conditions are included.
- Road conditions are linked to COtrip. No road safety state is inferred from camera imagery.

## Current implementation boundary

This first build is a static front end. It does not yet include a server-side provider layer, automated resort-report integration, or CDOT camera/incident feed access. The source registry identifies the checked camera embeds and the outstanding limits for those integrations.
