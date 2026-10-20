# Local PDF Tools

Static site for https://noclaudkit.com/pdf/ (GitHub Pages project site): merge, split and reorder PDF pages
and turn JPG/PNG images into a PDF, entirely in the browser. Files are processed locally with
[@local-pdf-tools/core](https://github.com/swtormy-agents/pdf-tools) (pdf-lib) and previewed with pdf.js.

## Layout

| Path | What |
|---|---|
| `index.html`, `merge-pdf.html`, `split-pdf.html`, `organize-pdf.html`, `jpg-to-pdf.html`, `privacy.html`, `licenses.html` | English pages (generated) |
| `ru/`, `zh/` | Russian and Simplified Chinese pages (generated) |
| `sitemap.xml` | 21 URLs with hreflang alternates (generated) |
| `assets/app.js`, `assets/worker.js` | esbuild bundles of `tools/src/` + core (generated) |
| `assets/vendor/pdf.min.js`, `pdf.worker.min.js` | pdfjs-dist, self-hosted, copied verbatim |
| `build/app.css` | Tailwind 4 + daisyUI 5 build of `tools/css/input.css` |
| `theme.js`, `assets/icons/` | theme switcher and its icons |
| `tools/gen.py` | page generator (runs `sync_i18n.py` first; strings live with their owners under `/workspace/i18n`, `/workspace/seo`, `/workspace/company/legal`) |
| `tools/i18n/` | synced copies of the UI, SEO, FAQ and privacy strings |
| `tools/src/` | UI (`app.js`), processing worker (`worker.js`), ZIP writer (`zip.js`) |
| `tools/scripts/` | JS build/check, CSS check, licence check |
| `tools/test/` | fixtures, local server, Playwright end-to-end suite |

## Build

```sh
cd tools
npm ci
npm run build:css && npm run build:js
cd .. && python3 tools/gen.py
```

Rerunning all three steps must leave `git status` clean.

## Checks

```sh
cd tools
npm run check:css        # byte-identical rebuild, no external url()/@import
npm run check:js         # byte-identical rebuild, assets current, no CDN URLs
npm run check:licenses   # licences page lists exactly the packages in the bundles
```

`gen.py` also fails on banned wording, NBSP in markup/meta/JSON-LD, and FAQ JSON-LD that differs from the visible FAQ.

## End-to-end tests

```sh
node tools/test/fixtures.mjs           # writes tools/test/out/fx/ (gitignored)
python3 tools/test/serve.py &          # serves the repo at http://127.0.0.1:8931/pdf/
python3 tools/test/e2e.py chromium firefox webkit
(cd tools && npm run test:worker)    # worker tags core errors with the failing file
```

Needs `pip install playwright && playwright install`. Screenshots and `e2e-results.json` go to `$SHOTS` (default `/workspace/tmp/pdf-site/`).

## Content Security Policy

Every page carries `default-src 'none'; script-src 'self'; style-src 'self'; img-src 'self' blob:; worker-src 'self'; base-uri 'none'; form-action 'none'; object-src 'none'`. Pages load only their own same-origin files; the e2e suite asserts zero cross-origin and zero non-GET requests.
