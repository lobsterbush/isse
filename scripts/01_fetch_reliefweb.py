"""Fetch state-of-emergency related reports and disasters from ReliefWeb API v2.

Queries the reports and disasters endpoints for SOE-related search terms,
extracts structured fields, and writes raw results to data/reliefweb_raw.json.
"""

import json
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests

# ── Config ──────────────────────────────────────────────────────────────────
BASE_URL = "https://api.reliefweb.int/v2"
APP_NAME = "isse-dashboard-2126g5pVgIsE16SfP4cWJ9K1"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"

SOE_QUERIES: list[str] = [
    '"state of emergency"',
    '"emergency declared"',
    '"declared a national emergency"',
    '"public health emergency"',
    '"state of disaster"',
    '"emergency extended"',
    '"lifted the emergency"',
    '"martial law"',
    '"state of exception"',
    '"emergency powers"',
]

# Look back 90 days for reports
LOOKBACK_DAYS = 90

FIELDS_REPORTS: list[str] = [
    "id",
    "title",
    "date.created",
    "date.original",
    "country.name",
    "country.iso3",
    "primary_country.name",
    "primary_country.iso3",
    "source.name",
    "disaster.name",
    "disaster_type.name",
    "url_alias",
]

FIELDS_DISASTERS: list[str] = [
    "id",
    "name",
    "date.created",
    "date.event",
    "country.name",
    "country.iso3",
    "type.name",
    "status",
    "glide",
    "url_alias",
]


def _post(endpoint: str, payload: dict[str, Any]) -> list[dict]:
    """POST to a ReliefWeb endpoint with retry logic."""
    url = f"{BASE_URL}/{endpoint}?appname={APP_NAME}"
    results: list[dict] = []
    offset = 0
    limit = 500

    while True:
        payload_page = {**payload, "offset": offset, "limit": limit}
        for attempt in range(3):
            try:
                resp = requests.post(url, json=payload_page, timeout=30)
                if resp.status_code == 403:
                    print(
                        "  [WARN] ReliefWeb returned 403 Forbidden. "
                        "Register an appname at https://apidoc.reliefweb.int/parameters#appname",
                        file=sys.stderr,
                    )
                    return results
                resp.raise_for_status()
                data = resp.json()
                break
            except (requests.RequestException, ValueError) as exc:
                if attempt == 2:
                    print(f"  [WARN] Failed after 3 attempts: {exc}", file=sys.stderr)
                    return results
                time.sleep(2 ** attempt)

        items = data.get("data", [])
        if not items:
            break
        results.extend(items)
        offset += limit
        if offset >= data.get("totalCount", 0):
            break
        time.sleep(0.5)  # rate-limit courtesy

    return results


def fetch_reports() -> list[dict]:
    """Fetch reports matching SOE search terms from the last 90 days."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime(
        "%Y-%m-%dT00:00:00+00:00"
    )
    all_reports: list[dict] = []
    seen_ids: set[int] = set()

    for query in SOE_QUERIES:
        print(f"  ReliefWeb reports: {query}")
        payload = {
            "query": {"value": query, "operator": "AND"},
            "filter": {
                "field": "date.created",
                "value": {"from": cutoff},
            },
            "fields": {"include": FIELDS_REPORTS},
            "sort": ["date.created:desc"],
        }
        items = _post("reports", payload)
        for item in items:
            rid = item.get("id")
            if rid and rid not in seen_ids:
                seen_ids.add(rid)
                all_reports.append(item)

    print(f"  → {len(all_reports)} unique reports")
    return all_reports


def fetch_disasters() -> list[dict]:
    """Fetch currently ongoing disasters."""
    print("  ReliefWeb disasters: ongoing")
    payload = {
        "filter": {"field": "status", "value": "ongoing"},
        "fields": {"include": FIELDS_DISASTERS},
        "sort": ["date.event:desc"],
    }
    items = _post("disasters", payload)
    print(f"  → {len(items)} ongoing disasters")
    return items


def normalize_report(item: dict) -> dict:
    """Flatten a ReliefWeb report into a standard record."""
    fields = item.get("fields", {})
    countries = fields.get("country", [])
    primary = fields.get("primary_country", {})
    sources = fields.get("source", [])
    disasters = fields.get("disaster", [])
    disaster_types = fields.get("disaster_type", [])

    # Use primary country if available, else first country
    if primary:
        iso3 = primary.get("iso3", "")
        country_name = primary.get("name", "")
    elif countries:
        iso3 = countries[0].get("iso3", "")
        country_name = countries[0].get("name", "")
    else:
        iso3 = ""
        country_name = ""

    return {
        "source": "reliefweb",
        "type": "report",
        "id": item.get("id"),
        "title": fields.get("title", ""),
        "date": fields.get("date", {}).get("original")
        or fields.get("date", {}).get("created", ""),
        "iso3": iso3,
        "country": country_name,
        "all_countries": [
            {"iso3": c.get("iso3", ""), "name": c.get("name", "")}
            for c in countries
        ],
        "source_name": sources[0].get("name", "") if sources else "",
        "disaster_names": [d.get("name", "") for d in disasters],
        "disaster_types": [d.get("name", "") for d in disaster_types],
        "url": f"https://reliefweb.int{fields.get('url_alias', '')}",
    }


def normalize_disaster(item: dict) -> dict:
    """Flatten a ReliefWeb disaster into a standard record."""
    fields = item.get("fields", {})
    countries = fields.get("country", [])
    types = fields.get("type", [])

    iso3 = countries[0].get("iso3", "") if countries else ""
    country_name = countries[0].get("name", "") if countries else ""

    return {
        "source": "reliefweb",
        "type": "disaster",
        "id": item.get("id"),
        "title": fields.get("name", ""),
        "date": fields.get("date", {}).get("event")
        or fields.get("date", {}).get("created", ""),
        "iso3": iso3,
        "country": country_name,
        "all_countries": [
            {"iso3": c.get("iso3", ""), "name": c.get("name", "")}
            for c in countries
        ],
        "source_name": "ReliefWeb",
        "disaster_names": [fields.get("name", "")],
        "disaster_types": [t.get("name", "") for t in types],
        "status": fields.get("status", ""),
        "glide": fields.get("glide", ""),
        "url": f"https://reliefweb.int{fields.get('url_alias', '')}",
    }


def main() -> None:
    """Run ReliefWeb fetch pipeline."""
    print("[01] Fetching ReliefWeb data...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    reports = fetch_reports()
    disasters = fetch_disasters()

    normalized = []
    for r in reports:
        normalized.append(normalize_report(r))
    for d in disasters:
        normalized.append(normalize_disaster(d))

    output_path = OUTPUT_DIR / "reliefweb_raw.json"
    output_path.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "report_count": len(reports),
                "disaster_count": len(disasters),
                "records": normalized,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"  Wrote {len(normalized)} records → {output_path.name}")


if __name__ == "__main__":
    main()
