"""Fetch current states of emergency from Wikipedia dynamically.

Scrapes the 'State of emergency' Wikipedia article's 'Active in YEAR'
sections (2020-2026) to build a list of declared emergencies.  Also parses
per-country sections for ongoing emergencies.

Outputs data/wiki_emergencies.json — consumed by 03_merge_and_classify.py.
"""

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pycountry
import requests
from bs4 import BeautifulSoup

# ── Config ──────────────────────────────────────────────────────────────────
WIKI_API = "https://en.wikipedia.org/w/api.php"
ARTICLE = "State_of_emergency"
UA = {"User-Agent": "ISSE-Dashboard/1.0 (https://statesofexception.org)"}
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"

# Year sections to scrape (index → year); we find these dynamically.
ACTIVE_YEARS = list(range(2020, 2027))

# Sub-national keywords — entries containing these are skipped.
_SUBNATIONAL = {
    "governor", "mayor", "premier", "county", "city of", "province of",
    "state of new", "state of west", "state of south",  # US states
    "new south wales", "victoria", "queensland", "ontario", "quebec",
    "california", "texas", "florida", "new york", "ohio",
    "los angeles", "minneapolis", "portland", "seattle", "ottawa",
    "maryland", "west virginia", "grindavík",
}

# Emergency-type keywords (same taxonomy as merge script)
_TYPE_KW: dict[str, list[str]] = {
    "disaster": [
        "earthquake", "flood", "cyclone", "hurricane", "typhoon", "tsunami",
        "volcanic", "eruption", "wildfire", "drought", "landslide", "storm",
        "disaster", "famine", "mudslide", "fire",
    ],
    "public_health": [
        "pandemic", "epidemic", "outbreak", "disease", "virus", "covid",
        "ebola", "cholera", "mpox", "health emergency", "public health",
    ],
    "conflict": [
        "conflict", "war", "armed", "military", "combat", "attack",
        "terrorism", "insurgency", "militia", "rebel", "gang", "violence",
        "martial law", "coup", "civil war", "shelling", "invasion",
    ],
    "migration": [
        "migration", "refugee", "displaced", "asylum", "border",
        "immigration", "migrant", "deportation",
    ],
    "governance": [
        "executive order", "emergency powers", "presidential decree",
        "authoritarian", "suspension of rights", "curfew", "protest",
        "constitutional", "censorship",
    ],
}

# ── Country resolution ──────────────────────────────────────────────────────
_COUNTRY_CACHE: dict[str, str | None] = {}
_EXTRA_MAP: dict[str, str] = {
    "trinidad and tobago": "TTO", "bosnia and herzegovina": "BIH",
    "north macedonia": "MKD", "south korea": "KOR", "north korea": "PRK",
    "ivory coast": "CIV", "czech republic": "CZE", "czechia": "CZE",
    "dr congo": "COD", "drc": "COD", "democratic republic of the congo": "COD",
    "republic of the congo": "COG", "south sudan": "SSD",
    "myanmar": "MMR", "burma": "MMR",
    "palestine": "PSE", "palestinian": "PSE", "gaza": "PSE",
    "united states": "USA", "hong kong": "HKG", "macau": "MAC",
    "russia": "RUS", "iran": "IRN", "syria": "SYR",
    "turkey": "TUR", "turkiye": "TUR",
    "venezuela": "VEN", "egypt": "EGY",
    "grindavík": "ISL", "iceland": "ISL",
    "south africa": "ZAF", "new zealand": "NZL",
    "sri lanka": "LKA", "papua new guinea": "PNG",
    "central african republic": "CAF", "equatorial guinea": "GNQ",
    "burkina faso": "BFA", "sierra leone": "SLE",
    "el salvador": "SLV", "costa rica": "CRI",
    "dominican republic": "DOM", "saudi arabia": "SAU",
    "united arab emirates": "ARE", "united kingdom": "GBR",
}


def _resolve_country(name: str) -> str | None:
    """Map a country name to ISO3, or None."""
    key = name.lower().strip()
    if key in _COUNTRY_CACHE:
        return _COUNTRY_CACHE[key]

    # Check extra map first
    if key in _EXTRA_MAP:
        _COUNTRY_CACHE[key] = _EXTRA_MAP[key]
        return _EXTRA_MAP[key]

    # Try pycountry
    try:
        c = pycountry.countries.lookup(name)
        _COUNTRY_CACHE[key] = c.alpha_3
        return c.alpha_3
    except LookupError:
        pass

    # Try fuzzy search
    try:
        results = pycountry.countries.search_fuzzy(name)
        if results:
            _COUNTRY_CACHE[key] = results[0].alpha_3
            return results[0].alpha_3
    except LookupError:
        pass

    _COUNTRY_CACHE[key] = None
    return None


def _is_subnational(text: str) -> bool:
    """Return True if the entry describes a sub-national emergency."""
    t = text.lower()
    return any(kw in t for kw in _SUBNATIONAL)


def _clean_text(text: str) -> str:
    """Clean Wikipedia markup artifacts from parsed text."""
    # Remove [ edit ] markers
    text = re.sub(r"\s*\[\s*edit\s*\]\s*", " ", text)
    # Remove footnote markers like [1], [2], [ 1 ]
    text = re.sub(r"\s*\[\s*\d+\s*\]\s*", "", text)
    # Remove "Main article: ..." and "Further information: ..." (anywhere)
    text = re.sub(
        r"(?:Main articles?|Further information|See also)\s*:\s*[^.]*?\.?\s*",
        "", text,
    )
    # Fix missing space after commas (but not in numbers like 93,549)
    text = re.sub(r",([A-Za-z])", r", \1", text)
    # Fix missing spaces: lowercase directly followed by uppercase
    text = re.sub(r"([a-z])([A-Z][a-z])", r"\1 \2", text)
    # Fix lowercase directly before ALL-CAPS (e.g. "theUK" → "the UK")
    text = re.sub(r"([a-z])([A-Z]{2,})", r"\1 \2", text)
    # Fix word glued to a year (e.g. "the2022" → "the 2022")
    text = re.sub(r"([a-zA-Z])(\d{4})", r"\1 \2", text)
    # Fix common verb/noun-gluing from wikitext (e.g. "Kangalooissued")
    _GLUED = (
        "declared|announced|issued|proclaimed|invoked|extended|signed|"
        "imposed|enacted|renewed|lifted|suspended|restored|introduced|"
        "flooding|following|during|after|before|because|emergency"
    )
    text = re.sub(rf"([a-zA-Z])({_GLUED})", r"\1 \2", text)
    # Collapse multiple spaces
    text = re.sub(r"\s{2,}", " ", text).strip()
    return text


def _classify(text: str) -> str:
    """Classify emergency type from text."""
    t = text.lower()
    scores: dict[str, int] = {}
    for etype, keywords in _TYPE_KW.items():
        for kw in keywords:
            if kw in t:
                scores[etype] = scores.get(etype, 0) + 1
    if not scores:
        return "governance"
    return max(scores, key=scores.get)


def _extract_date(text: str) -> str:
    """Try to extract a date like 'On 3 January 2026' from text."""
    m = re.search(
        r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|"
        r"August|September|October|November|December)\s+\d{4})",
        text,
    )
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%d %B %Y")
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            pass
    # Try just year-month
    m = re.search(r"((?:January|February|March|April|May|June|July|"
                  r"August|September|October|November|December)\s+\d{4})", text)
    if m:
        try:
            dt = datetime.strptime(m.group(1), "%B %Y")
            return dt.strftime("%Y-%m-01")
        except ValueError:
            pass
    return ""


def _extract_country_from_links(li_tag) -> tuple[str | None, str]:
    """Extract the most likely country ISO3 from <a> tags in a list item."""
    for a_tag in li_tag.find_all("a"):
        href = a_tag.get("href", "")
        if not href.startswith("/wiki/"):
            continue
        title = a_tag.get("title", "")
        # Skip person articles, date articles, etc.
        if any(skip in title.lower() for skip in [
            "president of", "prime minister", "governor of", "list of",
            "mayor of", "commander", "premier of",
        ]):
            # But extract the country FROM the title (e.g., "President of Venezuela")
            m = re.search(r"(?:of|in)\s+(?:the\s+)?(.+)", title, re.IGNORECASE)
            if m:
                iso3 = _resolve_country(m.group(1).strip())
                if iso3:
                    return iso3, m.group(1).strip()
            continue

        # Direct country match
        iso3 = _resolve_country(title)
        if iso3:
            return iso3, title

    return None, ""


def _extract_declared_by(text: str) -> str:
    """Extract who declared the emergency from the text."""
    # Look for patterns like "President X declared" or "Governor X declared"
    m = re.search(
        r"(?:President|Prime Minister|Governor|Minister|Leader|Council|"
        r"Commander|Parliament|Government)\s+(?:of\s+\w+\s+)?[A-Z][\w\s]{2,30}?"
        r"(?=\s+(?:declared|issued|announced|invoked|proclaimed))",
        text,
    )
    return m.group(0).strip() if m else ""


# ── Fetch and parse ─────────────────────────────────────────────────────────

def _api_get(params: dict) -> dict:
    """GET from Wikipedia API with retries."""
    for attempt in range(3):
        try:
            resp = requests.get(WIKI_API, params=params, headers=UA, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            if attempt == 2:
                print(f"  [WARN] Wikipedia API failed: {exc}", file=sys.stderr)
                return {}
    return {}


def fetch_sections() -> dict[str, str]:
    """Return mapping of section_index → section_title for the article."""
    data = _api_get({
        "action": "parse", "page": ARTICLE, "format": "json", "prop": "sections",
    })
    result: dict[str, str] = {}
    for s in data.get("parse", {}).get("sections", []):
        result[s["index"]] = s["line"]
    return result


def fetch_section_html(section_index: str) -> str:
    """Fetch the HTML of a specific section."""
    data = _api_get({
        "action": "parse", "page": ARTICLE, "format": "json",
        "prop": "text", "section": section_index,
    })
    return data.get("parse", {}).get("text", {}).get("*", "")


def parse_active_section(html: str, year: int) -> list[dict]:
    """Parse an 'Active in YEAR' section into emergency records."""
    soup = BeautifulSoup(html, "lxml")
    results: list[dict] = []

    for li in soup.find_all("li"):
        text = li.get_text(strip=True)

        # Skip footnotes / references
        if text.startswith("^") or len(text) < 30:
            continue

        # Skip sub-national emergencies
        if _is_subnational(text):
            continue

        # Extract country
        iso3, country_name = _extract_country_from_links(li)
        if not iso3:
            continue

        # Extract details
        date_str = _extract_date(text)
        declared_by = _extract_declared_by(text)
        etype = _classify(text)

        # Build a clean title (first sentence, truncated)
        text = _clean_text(text)
        title_text = text.split(".")[0][:150]
        if title_text and not title_text.endswith("."):
            title_text += "…"

        # Confidence based on recency
        current_year = datetime.now().year
        years_ago = current_year - year
        confidence = max(0.5, 0.95 - (years_ago * 0.08))

        results.append({
            "iso3": iso3,
            "country": country_name,
            "emergency_type": etype,
            "title": title_text,
            "declared_by": declared_by,
            "start_date": date_str,
            "status": "active",
            "confidence": round(confidence, 2),
            "source_url": f"https://en.wikipedia.org/wiki/{ARTICLE}",
            "source_type": "wikipedia",
            "last_verified": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "notes": _clean_text(text[:300]),
            "year_section": year,
        })

    return results


def parse_country_section(html: str, section_name: str) -> list[dict]:
    """Parse a per-country section for ongoing emergency info."""
    iso3 = _resolve_country(section_name)
    if not iso3:
        return []

    soup = BeautifulSoup(html, "lxml")
    text = _clean_text(soup.get_text(" ", strip=True))

    # Only include if recent activity mentioned
    recent_years = re.findall(r"\b(202[0-6])\b", text)
    if not recent_years:
        return []

    latest_year = max(int(y) for y in recent_years)
    if latest_year < 2022:
        return []

    # Check for emergency-related content
    emergency_kw = [
        "state of emergency", "martial law", "state of exception",
        "emergency powers", "emergency declared", "emergency decree",
        "state of siege",
    ]
    if not any(kw in text.lower() for kw in emergency_kw):
        return []

    # Require an activation verb near a recent date — filters out
    # sections that only describe the legal framework.
    activation_verbs = [
        "declared", "imposed", "invoked", "proclaimed", "announced",
        "enacted", "issued", "extended", "renewed",
    ]
    text_lower = text.lower()
    has_active = False
    for verb in activation_verbs:
        if verb in text_lower:
            # Check that the verb is near a recent year (within 200 chars)
            for m in re.finditer(re.escape(verb), text_lower):
                surrounding = text_lower[max(0, m.start() - 100):m.end() + 100]
                years_nearby = re.findall(r"\b(202[2-6])\b", surrounding)
                if years_nearby:
                    has_active = True
                    break
        if has_active:
            break
    if not has_active:
        return []

    date_str = _extract_date(text)
    etype = _classify(text)
    declared_by = _extract_declared_by(text)

    current_year = datetime.now().year
    years_ago = current_year - latest_year
    confidence = max(0.5, 0.90 - (years_ago * 0.08))

    # Get country common name
    try:
        c = pycountry.countries.get(alpha_3=iso3)
        country_name = getattr(c, "common_name", c.name) if c else section_name
    except (LookupError, AttributeError):
        country_name = section_name

    # Build a summary from first relevant sentence
    for line in text.split("."):
        line = line.strip()
        if any(kw in line.lower() for kw in emergency_kw) and len(line) > 20:
            title = _clean_text(line[:150])
            break
    else:
        title = f"Emergency powers in {country_name}"

    return [{
        "iso3": iso3,
        "country": country_name,
        "emergency_type": etype,
        "title": title,
        "declared_by": declared_by,
        "start_date": date_str,
        "status": "active",
        "confidence": round(confidence, 2),
        "source_url": f"https://en.wikipedia.org/wiki/{ARTICLE}#{section_name.replace(' ', '_')}",
        "source_type": "wikipedia",
        "last_verified": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "notes": "",
        "year_section": latest_year,
    }]


# ── Main ────────────────────────────────────────────────────────────────────

def main() -> None:
    """Run Wikipedia emergency scraper."""
    print("[00] Fetching emergencies from Wikipedia...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Get article section structure
    sections = fetch_sections()
    if not sections:
        print("  [ERROR] Could not fetch Wikipedia sections", file=sys.stderr)
        # Write empty output so pipeline doesn't break
        _write_empty()
        return

    # Find "Active in YEAR" section indices
    active_indices: dict[int, str] = {}
    country_indices: list[tuple[str, str]] = []

    for idx, title in sections.items():
        for year in ACTIVE_YEARS:
            if f"Active in {year}" in title:
                active_indices[year] = idx
                break
        # Also collect country sections (L3 under "Law in selected countries")
        else:
            # Country sections are typically at level 3
            iso3 = _resolve_country(title)
            if iso3:
                country_indices.append((idx, title))

    # Parse "Active in YEAR" sections
    all_entries: list[dict] = []
    seen_iso3: dict[str, dict] = {}  # Keep highest-confidence per country

    for year in sorted(active_indices.keys(), reverse=True):
        idx = active_indices[year]
        print(f"  Wikipedia: Active in {year} (section {idx})")
        html = fetch_section_html(idx)
        entries = parse_active_section(html, year)
        for e in entries:
            iso3 = e["iso3"]
            # Keep the most recent (highest confidence) entry per country
            if iso3 not in seen_iso3 or e["confidence"] > seen_iso3[iso3]["confidence"]:
                seen_iso3[iso3] = e
        print(f"    → {len(entries)} entries, {len(seen_iso3)} unique countries so far")

    # Parse country-specific sections for additional entries
    print(f"  Wikipedia: Scanning {len(country_indices)} country sections...")
    country_new = 0
    for idx, name in country_indices:
        if _resolve_country(name) in seen_iso3:
            continue  # Already have from Active sections
        html = fetch_section_html(idx)
        entries = parse_country_section(html, name)
        for e in entries:
            iso3 = e["iso3"]
            if iso3 not in seen_iso3:
                seen_iso3[iso3] = e
                country_new += 1
    print(f"    → {country_new} additional from country sections")

    all_entries = sorted(seen_iso3.values(), key=lambda e: e["confidence"], reverse=True)

    # Write output
    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": f"https://en.wikipedia.org/wiki/{ARTICLE}",
        "description": (
            "Dynamically scraped from Wikipedia's 'State of emergency' article. "
            "Each entry corresponds to a documented emergency declaration."
        ),
        "entry_count": len(all_entries),
        "emergencies": all_entries,
    }

    out_path = OUTPUT_DIR / "wiki_emergencies.json"
    out_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  → {len(all_entries)} emergencies → {out_path.name}")


def _write_empty() -> None:
    """Write an empty output file so downstream scripts don't break."""
    out_path = OUTPUT_DIR / "wiki_emergencies.json"
    out_path.write_text(
        json.dumps({
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "source": f"https://en.wikipedia.org/wiki/{ARTICLE}",
            "entry_count": 0,
            "emergencies": [],
        }, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
