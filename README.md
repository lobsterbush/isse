# Global States of Emergency Dashboard

A real-time tracker of global states of emergency, emergency powers, and executive emergency declarations. A project of the [Institute for the Study of States of Exception (ISSE)](https://www.statesofexception.org/).

## Authors

- Charles Crabtree, Senior Lecturer, School of Social Sciences, Monash University and K-Club Professor, University College, Korea University.

## Overview

This dashboard combines data from multiple automated sources to track countries currently under declared or de facto states of emergency:

1. **Wikipedia** — Active states of emergency and martial law declarations scraped from the [State of emergency](https://en.wikipedia.org/wiki/State_of_emergency) and [Martial law](https://en.wikipedia.org/wiki/Martial_law) articles via the MediaWiki API (primary baseline)
2. **ICCPR Article 4(3) Derogations** — Formal derogation notifications from the [UN Treaty Collection](https://treaties.un.org/Pages/ViewDetailsIII.aspx?src=TREATY&mtdsg_no=IV-4&chapter=4), indicating states that have suspended civil liberties obligations
3. **ReliefWeb API** — Humanitarian reports and ongoing disasters from [OCHA/ReliefWeb](https://reliefweb.int/) (corroborative only)
4. **GDACS** — Active disaster alerts from the [Global Disaster Alert and Coordination System](https://www.gdacs.org/) (corroborative only)
5. **GDELT DOC 2.0 API** — Global news monitoring for emergency-related terms (corroborative only)
6. **Curated overrides** — Hand-verified corrections and additions maintained by ISSE researchers

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
python scripts/01b_fetch_gdacs.py
python scripts/01c_fetch_iccpr_derogations.py
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
│   ├── iccpr_derogations.json     # Generated: ICCPR derogation data
│   ├── gdacs_raw.json             # Generated: GDACS disaster alerts
│   ├── emergencies.json           # Generated: merged active emergencies
│   ├── events.json                # Generated: news event stream
│   ├── reliefweb_raw.json         # Generated: raw ReliefWeb data
│   └── gdelt_raw.json             # Generated: raw GDELT data
├── js/
│   └── app.js                     # Dashboard application
├── scripts/
│   ├── 00_fetch_wikipedia_soe.py  # Wikipedia state-of-emergency + martial law scraper
│   ├── 01_fetch_reliefweb.py      # ReliefWeb API fetcher
│   ├── 01b_fetch_gdacs.py         # GDACS disaster alert fetcher
│   ├── 01c_fetch_iccpr_derogations.py  # ICCPR Art. 4(3) derogation scraper
│   ├── 02_fetch_gdelt.py          # GDELT DOC API fetcher
│   ├── 03_merge_and_classify.py   # Merge, classify, and output
│   └── requirements.txt
├── index.html                     # Dashboard page
├── WARP.md
└── README.md
```

## Data Sources

- [Wikipedia: State of emergency](https://en.wikipedia.org/wiki/State_of_emergency) — Primary baseline for active declarations
- [Wikipedia: Martial law](https://en.wikipedia.org/wiki/Martial_law) — Supplementary baseline for martial law declarations
- [ICCPR Article 4(3)](https://treaties.un.org/Pages/ViewDetailsIII.aspx?src=TREATY&mtdsg_no=IV-4&chapter=4) — UN Treaty Collection derogation notifications
- [GDACS](https://www.gdacs.org/) — Global Disaster Alert and Coordination System
- [ReliefWeb API](https://api.reliefweb.int/) — OCHA humanitarian information service
- [GDELT Project](https://www.gdeltproject.org/) — Global news event monitoring

## License

Data from Wikipedia is available under [CC BY-SA 3.0](https://creativecommons.org/licenses/by-sa/3.0/). Data from ReliefWeb and GDELT is subject to their respective terms of service.
