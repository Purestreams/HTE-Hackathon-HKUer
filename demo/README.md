# Static UI Demo

Open `demo/index.html` in a browser.

- This demo is intentionally **static** (no backend calls, no routing).
- Styling is copied from the built frontend bundle so it looks the same as `frontui`.

To refresh styles after UI changes:

1. Rebuild the frontend: `cd frontui && npm run build`
2. Copy the latest CSS from `frontui/dist/assets/*.css` into `demo/assets/frontui.css`
