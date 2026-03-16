# Global States of Emergency Dashboard

**Status:** Active

**Description:** Real-time dashboard tracking global states of emergency, emergency powers, and executive emergency declarations. Features a crisis comparison map highlighting the disconnect between humanitarian crises and formal emergency declarations. Static site on GitHub Pages with automated data pipeline.

**Live URL:** https://lobsterbush.github.io/isse/

**Authors:** Charles Crabtree (Monash University / Korea University)

**Organization:** Institute for the Study of States of Exception (ISSE)

## Current Coverage
- 25 active emergencies across 24 countries
- 72 crisis countries tracked (ReliefWeb, GDACS, IRC Watchlist)
- 122 events in the news stream
- Crisis comparison map showing 14 overlap, 58 crisis-only, 11 SoE-only countries

## Data Pipeline
Runs every 6 hours via GitHub Actions. Scripts in `scripts/` (numbered for execution order):
1. `00_fetch_wikipedia_soe.py` — Scrapes Wikipedia State_of_emergency, Martial_law, State_of_exception articles
2. `01_fetch_reliefweb.py` — ReliefWeb API (corroborative only)
3. `01b_fetch_gdacs.py` — GDACS disaster alerts (corroborative only)
4. `01c_fetch_iccpr_derogations.py` — UN Treaty Collection ICCPR Art. 4(3) derogations
5. `01d_fetch_us_nea.py` — US National Emergencies Act declarations from Wikipedia
6. `02_fetch_gdelt.py` — GDELT news monitoring (corroborative only)
7. `03_merge_and_classify.py` — Merges all sources, applies overrides, generates emergencies.json, events.json, crises.json

## Key Files
- `index.html` — Dashboard frontend (Leaflet maps, table, event stream, crisis comparison)
- `js/app.js` — Client-side rendering, two Leaflet maps, filters, CSV download
- `css/style.css` — Muted warm dark theme
- `data/overrides.json` — Hand-verified corrections and additions
- `data/emergencies.json` — Active emergencies (generated)
- `data/crises.json` — Crisis comparison data (generated)
- `.github/workflows/update-data.yml` — 6-hour cron pipeline

## Tech Stack
- Python 3.10+ with requests, beautifulsoup4, pycountry, lxml
- Vanilla JS + Leaflet.js + CARTO dark tiles
- GitHub Pages (static hosting)
