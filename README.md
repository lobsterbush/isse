# Global States of Emergency Dashboard

A real-time tracker of global states of emergency, emergency powers, and executive emergency declarations. A project of the [Institute for the Study of States of Exception (ISSE)](https://www.statesofexception.org/).

## Authors

- Charles Crabtree, Senior Lecturer, School of Social Sciences, Monash University and K-Club Professor, University College, Korea University.

## Overview

This dashboard combines data from multiple sources to track countries currently under declared or de facto states of emergency:

1. **ReliefWeb API** — Humanitarian reports and active disasters from OCHA/ReliefWeb
2. **GDELT DOC 2.0 API** — Global news monitoring for emergency-related terms
3. **Curated overrides** — Hand-checked entries for known emergencies

A GitHub Actions pipeline runs every 6 hours to fetch fresh data, classify emergencies by type (disaster, public health, conflict, migration, governance), and publish updated JSON files that power the static frontend.

## Live Dashboard

Visit the dashboard at: `https://[username].github.io/isse/`

## Requirements

- Python 3.10+
- `requests` and `pycountry` (see `scripts/requirements.txt`)
- No API keys required (ReliefWeb and GDELT are public APIs)

## Local Development

```bash
# Install Python dependencies
pip install -r scripts/requirements.txt

# Run the data pipeline
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
│   ├── overrides.json         # Hand-curated emergency entries
│   ├── emergencies.json       # Generated: current emergencies
│   ├── events.json            # Generated: event stream
│   ├── reliefweb_raw.json     # Generated: raw ReliefWeb data
│   └── gdelt_raw.json         # Generated: raw GDELT data
├── js/
│   └── app.js                 # Dashboard application
├── scripts/
│   ├── 01_fetch_reliefweb.py  # ReliefWeb API fetcher
│   ├── 02_fetch_gdelt.py      # GDELT DOC API fetcher
│   ├── 03_merge_and_classify.py # Merge, classify, output
│   └── requirements.txt
├── index.html                 # Dashboard page
└── README.md
```

## Data Sources

- [ReliefWeb API](https://api.reliefweb.int/) — OCHA humanitarian information service
- [GDELT Project](https://www.gdeltproject.org/) — Global news event monitoring
- Curated override data maintained by ISSE researchers

## License

Data from ReliefWeb and GDELT is subject to their respective terms of service.
