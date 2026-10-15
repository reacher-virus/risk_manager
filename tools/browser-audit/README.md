# Browser audit (optional dev tool)

Unit tests cannot see layout. These scripts drive a real headless Chrome against the built app (the API is mocked at the
network layer, so you do **not** need the Python backend) and check what users actually experience:

| Command | What it proves |
|---|---|
| `npm run audit` | No horizontal scrolling on 20 screens x 6 widths (320 to 1440 px), no sideways-scrolling regions on phones, no console errors |
| `npm run behave` | Mobile menu, clickable logo, footer links, page titles, 404, stacked tables, 3D hero is draggable... and writes screenshots to `./shots` |
| `npm run csp:serve` then `npm run csp` | The production build satisfies the exact Content-Security-Policy from `frontend/nginx.conf` (no blocked inline scripts or resources) |

```bash
cd frontend && npm run build && npm run preview &          # serves http://127.0.0.1:4173
cd ../tools/browser-audit && npm install                   # ~100 MB: it bundles Chromium
npm run audit && npm run behave

# the CSP check needs a production-style build whose API is same-origin (/api):
cd ../../frontend && VITE_API_BASE=/api npx vite build --outDir dist-csp --emptyOutDir
cd ../tools/browser-audit && (npm run csp:serve &) && npm run csp
```

Linux x64 uses the bundled Chromium. On macOS/Windows set `CHROME_PATH` to your Chrome. `BASE_URL`, `SHOTS_DIR` and `DIST_DIR` override the defaults.
Re-run `audit` after any restyle: overflow bugs almost always come from a fixed width, a grid track that cannot shrink, or a long unbroken string.
