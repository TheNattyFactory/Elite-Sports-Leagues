# Elite Core V16 — Static Routing + Mobile Polish

Fixes:
- serves `elite-sports-logo.svg` and `elite-crest.svg`
- supports SVG/PNG/JPEG/WebP/ICO MIME types
- serves all approved root-level HTML/CSS/JS/static assets without individual route maintenance
- keeps path traversal/nested file requests blocked
- fixes mobile hero button stacking
- fixes stat-card spacing and readability
- keeps broadcast ticker on a single animated line
- improves small-screen logo sizing and section spacing

No `static/` folder is required. `index.html` and the visual assets remain in the repository root.
