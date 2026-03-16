"""Merge Wikipedia, ReliefWeb, GDELT, GDACS, and ICCPR results into dashboard data.

Reads wiki_emergencies.json, reliefweb_raw.json, gdelt_raw.json, gdacs_raw.json,
iccpr_derogations.json, and (optionally) overrides.json.
Outputs:
  - data/emergencies.json  (current active emergencies by country)
  - data/events.json       (recent event stream for the news feed)
"""

import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

import pycountry

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

# ── Emergency type classification keywords ──────────────────────────────────
TYPE_KEYWORDS: dict[str, list[str]] = {
    "disaster": [
        "earthquake", "flood", "cyclone", "hurricane", "typhoon", "tornado",
        "tsunami", "volcanic", "eruption", "wildfire", "drought", "landslide",
        "storm", "disaster", "famine", "mudslide",
    ],
    "public_health": [
        "pandemic", "epidemic", "outbreak", "disease", "virus", "covid",
        "ebola", "cholera", "mpox", "monkeypox", "health emergency",
        "public health", "quarantine", "vaccination",
    ],
    "conflict": [
        "conflict", "war", "armed", "military", "combat", "attack",
        "terrorism", "insurgency", "militia", "rebel", "gang", "violence",
        "martial law", "coup", "civil war", "shelling", "bombardment",
    ],
    "migration": [
        "migration", "refugee", "displaced", "asylum", "border",
        "immigration", "migrant", "deportation", "exodus",
    ],
    "governance": [
        "executive order", "emergency powers", "executive emergency",
        "constitutional", "state of exception", "presidential decree",
        "authoritarian", "democratic backsliding", "suspension of rights",
        "curfew", "censorship", "surveillance",
    ],
}


# Hardcoded continent assignments for common countries
_CONTINENT_OVERRIDES: dict[str, str] = {
    "USA": "Americas", "CAN": "Americas", "MEX": "Americas", "BRA": "Americas",
    "ARG": "Americas", "COL": "Americas", "PER": "Americas", "CHL": "Americas",
    "ECU": "Americas", "VEN": "Americas", "BOL": "Americas", "PRY": "Americas",
    "URY": "Americas", "GUY": "Americas", "SUR": "Americas", "HTI": "Americas",
    "DOM": "Americas", "CUB": "Americas", "JAM": "Americas", "TTO": "Americas",
    "GTM": "Americas", "HND": "Americas", "SLV": "Americas", "NIC": "Americas",
    "CRI": "Americas", "PAN": "Americas",
    "GBR": "Europe", "FRA": "Europe", "DEU": "Europe", "ITA": "Europe",
    "ESP": "Europe", "PRT": "Europe", "NLD": "Europe", "BEL": "Europe",
    "CHE": "Europe", "AUT": "Europe", "POL": "Europe", "CZE": "Europe",
    "SVK": "Europe", "HUN": "Europe", "ROU": "Europe", "BGR": "Europe",
    "HRV": "Europe", "SRB": "Europe", "BIH": "Europe", "MNE": "Europe",
    "ALB": "Europe", "MKD": "Europe", "GRC": "Europe", "UKR": "Europe",
    "RUS": "Europe", "BLR": "Europe", "MDA": "Europe", "LTU": "Europe",
    "LVA": "Europe", "EST": "Europe", "FIN": "Europe", "SWE": "Europe",
    "NOR": "Europe", "DNK": "Europe", "ISL": "Europe", "IRL": "Europe",
    "GEO": "Europe", "ARM": "Europe", "AZE": "Europe", "TUR": "Europe",
    "CYP": "Europe", "MLT": "Europe", "LUX": "Europe",
    "CHN": "Asia", "JPN": "Asia", "KOR": "Asia", "PRK": "Asia",
    "IND": "Asia", "PAK": "Asia", "BGD": "Asia", "LKA": "Asia",
    "NPL": "Asia", "MMR": "Asia", "THA": "Asia", "VNM": "Asia",
    "KHM": "Asia", "LAO": "Asia", "MYS": "Asia", "SGP": "Asia",
    "IDN": "Asia", "PHL": "Asia", "TWN": "Asia", "MNG": "Asia",
    "KAZ": "Asia", "UZB": "Asia", "TKM": "Asia", "TJK": "Asia",
    "KGZ": "Asia", "AFG": "Asia", "IRN": "Asia", "IRQ": "Asia",
    "SYR": "Asia", "LBN": "Asia", "JOR": "Asia", "ISR": "Asia",
    "PSE": "Asia", "SAU": "Asia", "YEM": "Asia", "OMN": "Asia",
    "ARE": "Asia", "QAT": "Asia", "BHR": "Asia", "KWT": "Asia",
    "TLS": "Asia", "BRN": "Asia", "HKG": "Asia", "MAC": "Asia",
    "MDV": "Asia", "BTN": "Asia",
    "NGA": "Africa", "GHA": "Africa", "KEN": "Africa", "ETH": "Africa",
    "TZA": "Africa", "UGA": "Africa", "RWA": "Africa", "BDI": "Africa",
    "COD": "Africa", "COG": "Africa", "CMR": "Africa", "TCD": "Africa",
    "NER": "Africa", "MLI": "Africa", "BFA": "Africa", "SEN": "Africa",
    "GIN": "Africa", "SLE": "Africa", "LBR": "Africa", "CIV": "Africa",
    "SDN": "Africa", "SSD": "Africa", "SOM": "Africa", "ERI": "Africa",
    "DJI": "Africa", "ZAF": "Africa", "MOZ": "Africa", "ZWE": "Africa",
    "ZMB": "Africa", "MWI": "Africa", "AGO": "Africa", "NAM": "Africa",
    "BWA": "Africa", "MDG": "Africa", "TUN": "Africa", "DZA": "Africa",
    "MAR": "Africa", "LBY": "Africa", "EGY": "Africa", "MRT": "Africa",
    "GAB": "Africa", "GNQ": "Africa", "CAF": "Africa",
    "AUS": "Oceania", "NZL": "Oceania", "FJI": "Oceania", "PNG": "Oceania",
    "SLB": "Oceania", "VUT": "Oceania", "WSM": "Oceania", "TON": "Oceania",
}


def get_continent(iso3: str) -> str:
    """Return continent for an ISO3 code."""
    return _CONTINENT_OVERRIDES.get(iso3, "Unknown")


def classify_emergency_type(text: str) -> str:
    """Classify emergency type from title/text using keyword matching."""
    text_lower = text.lower()
    scores: dict[str, int] = defaultdict(int)

    for etype, keywords in TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                scores[etype] += 1

    if not scores:
        return "governance"  # Default for generic SOE declarations

    return max(scores, key=scores.get)


def compute_confidence(record: dict) -> float:
    """Compute a confidence score for an emergency record."""
    score = 0.3  # Base score for any API match

    # Boost for multiple sources
    sources = record.get("sources", [])
    if len(sources) >= 3:
        score += 0.3
    elif len(sources) >= 2:
        score += 0.2

    # Boost for ReliefWeb (more authoritative)
    if any(s.get("source") == "reliefweb" for s in sources):
        score += 0.2

    # Boost for recent activity
    events = record.get("recent_events", [])
    if events:
        score += 0.1

    return min(score, 1.0)


def load_raw_data() -> tuple[list[dict], list[dict], list[dict]]:
    """Load raw data files from previous fetch steps."""
    rw_path = DATA_DIR / "reliefweb_raw.json"
    gd_path = DATA_DIR / "gdelt_raw.json"
    gc_path = DATA_DIR / "gdacs_raw.json"

    rw_records = []
    gd_records = []
    gc_records = []

    if rw_path.exists():
        rw_data = json.loads(rw_path.read_text(encoding="utf-8"))
        rw_records = rw_data.get("records", [])
        print(f"  Loaded {len(rw_records)} ReliefWeb records")
    else:
        print("  [WARN] No reliefweb_raw.json found")

    if gd_path.exists():
        gd_data = json.loads(gd_path.read_text(encoding="utf-8"))
        gd_records = gd_data.get("records", [])
        print(f"  Loaded {len(gd_records)} GDELT records")
    else:
        print("  [WARN] No gdelt_raw.json found")

    if gc_path.exists():
        gc_data = json.loads(gc_path.read_text(encoding="utf-8"))
        gc_records = gc_data.get("records", [])
        print(f"  Loaded {len(gc_records)} GDACS records")
    else:
        print("  [WARN] No gdacs_raw.json found")

    return rw_records, gd_records, gc_records


def load_reference() -> list[dict]:
    """Load Wikipedia-sourced emergency baseline."""
    path = DATA_DIR / "wiki_emergencies.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        entries = data.get("emergencies", [])
        print(f"  Loaded {len(entries)} Wikipedia emergencies")
        return entries
    print("  [WARN] No wiki_emergencies.json found — run 00_fetch_wikipedia_soe.py first")
    return []


def load_iccpr() -> list[dict]:
    """Load ICCPR Article 4(3) derogation data."""
    path = DATA_DIR / "iccpr_derogations.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get("records", [])
        active = [r for r in records if r.get("active")]
        if records:
            print(f"  Loaded {len(records)} ICCPR derogations ({len(active)} active)")
        return records
    return []


def load_overrides() -> list[dict]:
    """Load optional curated overrides (supplements/corrections)."""
    path = DATA_DIR / "overrides.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        overrides = data.get("overrides", [])
        if overrides:
            print(f"  Loaded {len(overrides)} overrides")
        return overrides
    return []


def build_emergencies(
    rw_records: list[dict],
    gd_records: list[dict],
    gc_records: list[dict],
    reference: list[dict],
    iccpr_records: list[dict],
    overrides: list[dict],
) -> list[dict]:
    """Build the emergencies list by country, merging all sources.

    Priority order: reference baseline → ReliefWeb → ICCPR → GDACS → GDELT → overrides.
    Live data boosts confidence when it confirms reference entries.
    """
    # Group by ISO3
    by_country: dict[str, dict] = {}

    # 1) Seed from reference emergencies (news-sourced baseline)
    for ref in reference:
        iso3 = ref.get("iso3", "")
        if not iso3:
            continue
        by_country[iso3] = {
            "iso3": iso3,
            "country": ref.get("country", ""),
            "continent": get_continent(iso3),
            "emergency_type": ref.get("emergency_type", "governance"),
            "title": ref.get("title", ""),
            "declared_by": ref.get("declared_by", ""),
            "start_date": ref.get("start_date", ""),
            "status": ref.get("status", "active"),
            "confidence": ref.get("confidence", 0.6),
            "sources": [{
                "source": "reference",
                "title": ref.get("title", ""),
                "date": ref.get("last_verified", ""),
                "url": ref.get("source_url", ""),
            }],
            "recent_events": [],
            "source_urls": [{
                "title": ref.get("title", "")[:100],
                "url": ref.get("source_url", ""),
                "date": ref.get("start_date", "")[:10],
            }] if ref.get("source_url") else [],
            "notes": ref.get("notes", ""),
            "_classification_text": ref.get("title", "") + " " + ref.get("notes", ""),
        }

    # 2) Process ReliefWeb records — corroborative only (don't create new entries).
    #    ReliefWeb tracks humanitarian situations and ongoing disasters, not
    #    formal state-of-emergency declarations.
    for rec in rw_records:
        iso3 = rec.get("iso3", "")
        if not iso3:
            continue
        if iso3 not in by_country:
            continue  # Skip — no declared SoE for this country

        entry = by_country[iso3]
        entry["sources"].append({
            "source": "reliefweb",
            "title": rec.get("title", ""),
            "date": rec.get("date", ""),
            "url": rec.get("url", ""),
        })

        # Use earliest date as start_date approximation
        rec_date = rec.get("date", "")
        if rec_date and (not entry["start_date"] or rec_date < entry["start_date"]):
            entry["start_date"] = rec_date[:10]

        # Build combined text for classification
        combined_text = " ".join([
            rec.get("title", ""),
            " ".join(rec.get("disaster_types", [])),
            " ".join(rec.get("disaster_names", [])),
        ])
        if not entry["title"]:
            entry["title"] = rec.get("title", "")
        entry["_classification_text"] = entry.get("_classification_text", "") + " " + combined_text

    # 3) Process ICCPR Article 4(3) derogations
    #    Active derogations are strong evidence of an emergency regime.
    for rec in iccpr_records:
        if not rec.get("active"):
            continue
        iso3 = rec.get("iso3", "")
        if not iso3 or len(iso3) != 3:
            continue

        iccpr_source = {
            "source": "iccpr",
            "title": f"ICCPR Art. 4(3) derogation \u2013 {rec.get('country', '')}",
            "date": rec.get("latest_date", ""),
            "url": "https://treaties.un.org/Pages/ViewDetailsIII.aspx?src=TREATY&mtdsg_no=IV-4&chapter=4",
        }

        if iso3 not in by_country:
            by_country[iso3] = {
                "iso3": iso3,
                "country": rec.get("country", ""),
                "continent": get_continent(iso3),
                "emergency_type": "governance",
                "title": "ICCPR Article 4 derogation notification",
                "declared_by": "",
                "start_date": rec.get("earliest_date", ""),
                "status": "active",
                "confidence": 0.90,
                "sources": [iccpr_source],
                "recent_events": [],
                "source_urls": [{
                    "title": iccpr_source["title"][:100],
                    "url": iccpr_source["url"],
                    "date": rec.get("latest_date", "")[:10],
                }],
                "notes": rec.get("summary", ""),
                "_classification_text": f"ICCPR derogation {rec.get('country', '')}",
            }
        else:
            entry = by_country[iso3]
            entry["sources"].append(iccpr_source)
            entry["confidence"] = max(entry.get("confidence", 0), 0.90)
            entry["_classification_text"] = (
                entry.get("_classification_text", "") + " ICCPR derogation"
            )

    # 4) Process GDACS disaster alerts — ONLY boost existing entries.
    #    GDACS tracks disasters, not SoE declarations. A disaster alert
    #    does NOT mean a state of emergency was declared.
    for rec in gc_records:
        iso3 = rec.get("iso3", "")
        if not iso3 or len(iso3) != 3:
            continue
        if iso3 not in by_country:
            continue  # Skip — no declared SoE for this country

        entry = by_country[iso3]
        entry["sources"].append({
            "source": "gdacs",
            "title": rec.get("title", ""),
            "date": rec.get("date", ""),
            "url": rec.get("url", ""),
        })
        entry["_classification_text"] = (
            entry.get("_classification_text", "") + " " +
            rec.get("title", "") + " " + rec.get("event_type", "")
        )

    # 5) Process GDELT records — ONLY boost existing entries.
    #    GDELT news articles confirm that emergencies are being reported on,
    #    but a news article alone doesn't constitute a declared SoE.
    for rec in gd_records:
        countries = rec.get("mentioned_countries", [])
        if not countries:
            iso3 = rec.get("iso3", "")
            countries = [iso3] if iso3 and len(iso3) == 3 else []

        for iso3 in countries:
            if not iso3 or len(iso3) != 3:
                continue
            if iso3 not in by_country:
                continue  # Skip — no declared SoE for this country

            entry = by_country[iso3]
            entry["sources"].append({
                "source": "gdelt",
                "title": rec.get("title", ""),
                "date": rec.get("date", ""),
                "url": rec.get("url", ""),
            })
            entry["_classification_text"] = entry.get("_classification_text", "") + " " + rec.get("title", "")

    # 6) Classify and score
    reference_isos = {r["iso3"] for r in reference if r.get("iso3")}
    iccpr_isos = {r["iso3"] for r in iccpr_records if r.get("iso3") and r.get("active")}
    seeded_isos = reference_isos | iccpr_isos
    for iso3, entry in by_country.items():
        text = entry.pop("_classification_text", "")
        # Only override type from classification if not already set from reference/ICCPR
        if iso3 not in seeded_isos or not entry.get("emergency_type"):
            entry["emergency_type"] = classify_emergency_type(text)
        confidence = compute_confidence(entry)
        # Preserve seeded confidence (from reference or ICCPR)
        if iso3 in seeded_isos:
            has_live = any(
                s.get("source") in ("gdelt", "reliefweb", "gdacs", "iccpr")
                for s in entry.get("sources", [])
            )
            if has_live:
                confidence = max(confidence, entry.get("confidence", 0), 0.85)
            else:
                confidence = max(confidence, entry.get("confidence", 0))
        entry["confidence"] = confidence

        # Keep only the 5 most recent source URLs
        sources_sorted = sorted(entry["sources"], key=lambda s: s.get("date", ""), reverse=True)
        entry["source_urls"] = [
            {"title": s["title"][:100], "url": s["url"], "date": s["date"][:10]}
            for s in sources_sorted[:5]
            if s.get("url")
        ]
        # Build recent events for the news stream
        entry["recent_events"] = [
            {"title": s["title"][:120], "url": s["url"], "date": s["date"][:10], "source": s["source"]}
            for s in sources_sorted[:10]
        ]
        # Trim sources to count only
        entry["source_count"] = len(entry["sources"])
        del entry["sources"]

    # 7) Apply overrides (these take precedence, optional supplements)
    expired_count = 0
    boosted_count = 0
    for ov in overrides:
        iso3 = ov.get("iso3", "")
        if not iso3:
            continue
        ov_status = ov.get("status", "active")

        if iso3 not in by_country:
            # Don't create new entries for expired/lifted overrides
            if ov_status in ("expired", "lifted"):
                continue
            by_country[iso3] = {
                "iso3": iso3,
                "country": ov.get("country", ""),
                "continent": get_continent(iso3),
                "emergency_type": ov.get("emergency_type", "governance"),
                "title": ov.get("title", ""),
                "declared_by": ov.get("declared_by", ""),
                "start_date": ov.get("start_date", ""),
                "status": ov_status,
                "confidence": ov.get("confidence", 1.0),
                "source_urls": [{"title": "Official source", "url": ov.get("source_url", ""), "date": ""}],
                "recent_events": [],
                "source_count": 1,
                "notes": ov.get("notes", ""),
                "legal_basis": ov.get("legal_basis", ""),
                "scope": ov.get("scope", ""),
                "override": True,
            }
            boosted_count += 1
        else:
            entry = by_country[iso3]
            # Override fields where the curated data is better
            if ov.get("title"):
                entry["title"] = ov["title"]
            if ov.get("emergency_type"):
                entry["emergency_type"] = ov["emergency_type"]
            if ov.get("declared_by"):
                entry["declared_by"] = ov["declared_by"]
            if ov.get("start_date"):
                entry["start_date"] = ov["start_date"]
            if ov_status:
                entry["status"] = ov_status
            if ov.get("confidence"):
                entry["confidence"] = max(entry.get("confidence", 0), ov["confidence"])
            if ov.get("source_url"):
                entry["source_urls"].insert(0, {
                    "title": "Official source",
                    "url": ov["source_url"],
                    "date": ov.get("start_date", "")[:10],
                })
            entry["notes"] = ov.get("notes", "")
            if ov.get("legal_basis"):
                entry["legal_basis"] = ov["legal_basis"]
            if ov.get("scope"):
                entry["scope"] = ov["scope"]
            entry["override"] = True
            if not entry.get("country"):
                entry["country"] = ov.get("country", "")
            if ov_status in ("expired", "lifted"):
                expired_count += 1
            elif ov.get("confidence"):
                boosted_count += 1
    if expired_count or boosted_count:
        print(f"  Overrides applied: {expired_count} marked expired, {boosted_count} boosted")

    # Resolve country names via pycountry for any missing
    for iso3, entry in by_country.items():
        if not entry.get("country"):
            try:
                c = pycountry.countries.get(alpha_3=iso3)
                if c:
                    entry["country"] = getattr(c, "common_name", c.name)
            except (LookupError, AttributeError):
                pass

    return sorted(by_country.values(), key=lambda e: e.get("confidence", 0), reverse=True)


def build_events(
    rw_records: list[dict],
    gd_records: list[dict],
    gc_records: list[dict],
) -> list[dict]:
    """Build the recent events stream from all records."""
    events: list[dict] = []

    for rec in rw_records:
        events.append({
            "source": "reliefweb",
            "title": rec.get("title", "")[:150],
            "date": rec.get("date", "")[:10],
            "iso3": rec.get("iso3", ""),
            "country": rec.get("country", ""),
            "url": rec.get("url", ""),
            "source_name": rec.get("source_name", "ReliefWeb"),
            "emergency_type": classify_emergency_type(
                rec.get("title", "") + " " + " ".join(rec.get("disaster_types", []))
            ),
        })

    for rec in gc_records:
        iso3 = rec.get("iso3", "")
        country_name = rec.get("country", "")
        if not country_name and iso3:
            try:
                c = pycountry.countries.get(alpha_3=iso3)
                if c:
                    country_name = getattr(c, "common_name", c.name)
            except (LookupError, AttributeError):
                pass
        events.append({
            "source": "gdacs",
            "title": rec.get("title", "")[:150],
            "date": rec.get("date", "")[:10],
            "iso3": iso3,
            "country": country_name,
            "url": rec.get("url", ""),
            "source_name": "GDACS",
            "emergency_type": "disaster",
            "alert_level": rec.get("alert_level", ""),
        })

    for rec in gd_records:
        iso3 = rec.get("iso3", "")
        # Resolve country name from ISO3
        country_name = ""
        if iso3:
            try:
                c = pycountry.countries.get(alpha_3=iso3)
                if c:
                    country_name = getattr(c, "common_name", c.name)
            except (LookupError, AttributeError):
                pass
        events.append({
            "source": "gdelt",
            "title": rec.get("title", "")[:150],
            "date": rec.get("date", "")[:10],
            "iso3": iso3,
            "country": country_name,
            "url": rec.get("url", ""),
            "source_name": rec.get("domain", ""),
            "emergency_type": classify_emergency_type(rec.get("title", "")),
        })

    # Sort by date descending, take most recent 500
    events.sort(key=lambda e: e.get("date", ""), reverse=True)
    return events[:500]


def main() -> None:
    """Run merge and classify pipeline."""
    print("[03] Merging and classifying...")

    rw_records, gd_records, gc_records = load_raw_data()
    reference = load_reference()
    iccpr_records = load_iccpr()
    overrides = load_overrides()

    emergencies = build_emergencies(rw_records, gd_records, gc_records, reference, iccpr_records, overrides)
    events = build_events(rw_records, gd_records, gc_records)

    # Filter to only active emergencies with confidence >= 50%
    active = [
        e for e in emergencies
        if e.get("status") in ("active", "extended")
        and e.get("confidence", 0) >= 0.5
    ]

    now = datetime.now(timezone.utc).isoformat()

    # Write emergencies.json
    emerg_path = DATA_DIR / "emergencies.json"
    emerg_path.write_text(
        json.dumps(
            {
                "generated_at": now,
                "active_count": len(active),
                "total_count": len(emergencies),
                "emergencies": active,
                "all_emergencies": emergencies,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"  → {len(active)} active emergencies → emergencies.json")

    # Write events.json
    events_path = DATA_DIR / "events.json"
    events_path.write_text(
        json.dumps(
            {
                "generated_at": now,
                "event_count": len(events),
                "events": events,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"  → {len(events)} events → events.json")


if __name__ == "__main__":
    main()
