"""Fetch recent disaster alerts from GDACS (Global Disaster Alert and Coordination System).

Queries the GDACS event search API for significant (Orange/Red alert level)
natural disaster events in the last 90 days. These often correlate with or
trigger state-of-emergency declarations.

Outputs: data/gdacs_raw.json

Source: https://www.gdacs.org  (UN/EU cooperation framework)
Terms of use: acknowledge source as "Global Disaster Alert and Coordination System, GDACS"
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

# ── Config ──────────────────────────────────────────────────────────────────
BASE_URL = "https://www.gdacs.org/gdacsapi/api/events/geteventlist/SEARCH"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"
UA = {"User-Agent": "ISSE-Dashboard/1.0 (research project; emergency monitoring)"}

# Event types to fetch
EVENT_TYPES = "EQ,TC,FL,VO,DR,WF"  # earthquake, cyclone, flood, volcano, drought, wildfire

# Only significant events (Orange or Red alert level)
ALERT_LEVELS = "Orange;Red"

# Look back 90 days
LOOKBACK_DAYS = 90

# Map GDACS event type codes to human-readable labels
EVENT_TYPE_LABELS: dict[str, str] = {
    "EQ": "Earthquake",
    "TC": "Tropical Cyclone",
    "FL": "Flood",
    "VO": "Volcanic Eruption",
    "DR": "Drought",
    "WF": "Wildfire",
}


def fetch_events() -> list[dict]:
    """Fetch recent significant disaster events from GDACS API."""
    to_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    from_date = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime(
        "%Y-%m-%d"
    )

    params = {
        "eventlist": EVENT_TYPES,
        "fromdate": from_date,
        "todate": to_date,
        "alertlevel": ALERT_LEVELS,
    }

    for attempt in range(3):
        try:
            resp = requests.get(BASE_URL, params=params, headers=UA, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            features = data.get("features", [])
            print(f"  GDACS API: {len(features)} significant events (Orange/Red)")
            return features
        except requests.RequestException as exc:
            if attempt == 2:
                print(f"  [WARN] GDACS API failed after 3 attempts: {exc}", file=sys.stderr)
                return []
            wait = 3 * (attempt + 1)
            print(f"  Retrying in {wait}s...", file=sys.stderr)
            time.sleep(wait)

    return []


def normalize_event(feature: dict) -> list[dict]:
    """Normalize a GDACS GeoJSON feature into one record per affected country.

    A single GDACS event can affect multiple countries (e.g., a regional drought).
    We produce one record per affected country so the merge script can match by ISO3.
    """
    props = feature.get("properties", {})
    geometry = feature.get("geometry", {})
    coords = geometry.get("coordinates", [None, None])

    event_type = props.get("eventtype", "")
    event_label = EVENT_TYPE_LABELS.get(event_type, event_type)
    alert_level = props.get("alertlevel", "")
    event_name = props.get("eventname", "")

    # Build a descriptive title
    country_str = props.get("country", "")
    if event_name:
        title = f"{event_label}: {event_name}"
    elif country_str:
        title = f"{event_label} in {country_str}"
    else:
        title = f"{event_label} ({alert_level} alert)"

    # Extract dates
    from_date = props.get("fromdate", "")[:10]
    to_date = props.get("todate", "")[:10]

    # GDACS report URL
    report_url = props.get("url", {}).get("report", "")
    details_url = props.get("url", {}).get("details", "")
    url = report_url or details_url or f"https://www.gdacs.org/report.aspx?eventid={props.get('eventid', '')}&eventtype={event_type}"

    # Alert score (1=Green, 2=Orange, 3=Red)
    alert_score = props.get("alertscore", 0)

    # Affected countries with ISO3
    affected = props.get("affectedcountries", [])
    if not affected:
        # Fall back to primary iso3
        iso3 = props.get("iso3", "")
        if iso3:
            affected = [{"iso3": iso3, "countryname": country_str.split(",")[0].strip()}]

    records = []
    for ac in affected:
        iso3 = ac.get("iso3", "")
        if not iso3 or len(iso3) != 3:
            continue
        records.append({
            "source": "gdacs",
            "type": "disaster_alert",
            "event_id": props.get("eventid"),
            "episode_id": props.get("episodeid"),
            "event_type_code": event_type,
            "event_type": event_label,
            "alert_level": alert_level,
            "alert_score": alert_score,
            "title": title,
            "date": from_date,
            "end_date": to_date,
            "iso3": iso3,
            "country": ac.get("countryname", ""),
            "url": url,
            "source_name": "GDACS",
            "lat": coords[1] if len(coords) > 1 else None,
            "lon": coords[0] if len(coords) > 0 else None,
            "is_current": props.get("iscurrent", ""),
        })

    return records


def main() -> None:
    """Run GDACS fetch pipeline."""
    print("[01b] Fetching GDACS disaster alerts...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    features = fetch_events()

    all_records: list[dict] = []
    for feat in features:
        all_records.extend(normalize_event(feat))

    # Deduplicate by (event_id, iso3)
    seen: set[tuple] = set()
    unique: list[dict] = []
    for rec in all_records:
        key = (rec["event_id"], rec["iso3"])
        if key not in seen:
            seen.add(key)
            unique.append(rec)

    countries_covered = len({r["iso3"] for r in unique})
    print(f"  → {len(unique)} records across {countries_covered} countries")

    output_path = OUTPUT_DIR / "gdacs_raw.json"
    output_path.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "source": "GDACS (Global Disaster Alert and Coordination System)",
                "attribution": "Global Disaster Alert and Coordination System, GDACS",
                "event_count": len(features),
                "record_count": len(unique),
                "records": unique,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"  Wrote {len(unique)} records → {output_path.name}")


if __name__ == "__main__":
    main()
