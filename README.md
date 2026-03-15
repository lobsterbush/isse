# Global States of Emergency Dashboard

A real-time tracker of global states of emergency, emergency powers, and executive emergency declarations. A project of the [Institute for the Study of States of Exception (ISSE)](https://www.statesofexception.org/).

## Authors

- Charles Crabtree, Senior Lecturer, School of Social Sciences, Monash University and K-Club Professor, University College, Korea University.

## Overview

This dashboard combines data from multiple automated sources to track countries currently under declared or de facto states of emergency:

1. **Wikipedia** — Active states of emergency scraped from the [State of emergency](https://en.wikipedia.org/wiki/State_of_emergency) article via the MediaWiki API (primary baseline)
2. **GDELT DOC 2.0 API** — Global news monitoring for emergency-related terms
3. **ReliefWeb API** — Humanitarian reports and active disasters from OCHA/ReliefWeb
4. **Curated overrides** — Optional hand-checked entries for corrections or additions

A GitHub Actions pipeline runs every 6 hours to fetch fresh data, classify emergencies by type (disaster, public health, conflict, migration, governance), and publish updated JSON files that power the static frontend.

## Live Dashboard

Visit the dashboard at: https://lobsterbush.github.io/isse/

## Requirements

- Python 3.10+
- `requests`, `pycountry`, `beautifulsoup4`, `lxml` (see `scripts/requirements.txt`)
- No API keys required (all data sources are public)

## Local Development

```bash
# Install Python dependencies
pip install -r scripts/requirements.txt

# Run the full data pipeline
python scripts/00_fetch_wikipedia_soe.py
python scripts/01_fetch_reliefweb.py
python scripts/02_fetch_gdelt.py
python scripts/03_merge_and_classify.py

# Serve locally (any static file server works)
python -m http.server 8000
# Open http://localhost:8000
```

## Project Structure

```
isse/
├── .github/workflows/
│   └── update-data.yml        # Scheduled data refresh (every 6 hours)
├── assets/
│   ├── isse_logo_light.png    # ISSE logo (for dark backgrounds)
│   ├── isse_logo_dark.png     # ISSE logo (for light backgrounds)
│   └── favicon.ico
├── css/
│   └── style.css              # ISSE-branded dark theme
├── data/
│   ├── countries.geojson          # Local GeoJSON for country boundaries
│   ├── overrides.json             # Optional hand-curated entries
│   ├── wiki_emergencies.json      # Generated: Wikipedia baseline
│   ├── emergencies.json           # Generated: merged active emergencies
│   ├── events.json                # Generated: news event stream
│   ├── reliefweb_raw.json         # Generated: raw ReliefWeb data
│   └── gdelt_raw.json             # Generated: raw GDELT data
├── js/
│   └── app.js                     # Dashboard application
├── scripts/
│   ├── 00_fetch_wikipedia_soe.py  # Wikipedia state-of-emergency scraper
│   ├── 01_fetch_reliefweb.py      # ReliefWeb API fetcher
│   ├── 02_fetch_gdelt.py          # GDELT DOC API fetcher
│   ├── 03_merge_and_classify.py   # Merge, classify, and output
│   └── requirements.txt
├── index.html                     # Dashboard page
├── WARP.md
└── README.md
```

## Data Sources

- [Wikipedia: State of emergency](https://en.wikipedia.org/wiki/State_of_emergency) — Primary baseline for active declarations
- [GDELT Project](https://www.gdeltproject.org/) — Global news event monitoring
- [ReliefWeb API](https://api.reliefweb.int/) — OCHA humanitarian information service

## License

Data from Wikipedia is available under [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). Data from ReliefWeb and GDELT is subject to their respective terms of service.
