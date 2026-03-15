"""Fetch state-of-emergency related news articles from GDELT DOC 2.0 API.

Queries the GDELT full-text search API for SOE-related phrases across
its rolling 3-month window. Extracts the country each article is ABOUT
by matching country names in article titles (not source country).
Outputs raw results to data/gdelt_raw.json.
"""

import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import pycountry
import requests

# ── Config ──────────────────────────────────────────────────────────────────
BASE_URL = "https://api.gdeltproject.org/api/v2/doc/doc"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"

# Each query searches GDELT's rolling 3-month window.
# Keep individual phrases (GDELT DOC API doesn't support OR well).
SOE_PHRASES: list[str] = [
    '"state of emergency"',
    '"national emergency"',
    '"emergency declared"',
    '"martial law"',
    '"state of exception"',
    '"emergency powers"',
    '"emergency decree"',
    '"declared an emergency"',
    '"state of disaster"',
    '"public health emergency"',
    '"emergency measures"',
    '"extends state of emergency"',
]

MAX_RECORDS = 250

# ── Country name matching ───────────────────────────────────────────────────
_COUNTRY_LOOKUP: dict[str, str] = {}

_EXTRA_NAMES: dict[str, str] = {
    "united states": "USA", "u.s.": "USA", "u.s": "USA",
    "america": "USA", "american": "USA",
    "united kingdom": "GBR", "britain": "GBR",
    "british": "GBR", "england": "GBR", "scotland": "GBR",
    "russia": "RUS", "russian": "RUS", "moscow": "RUS",
    "china": "CHN", "chinese": "CHN", "beijing": "CHN",
    "south korea": "KOR", "north korea": "PRK",
    "south sudan": "SSD", "ivory coast": "CIV",
    "dr congo": "COD", "drc": "COD",
    "czech republic": "CZE", "czechia": "CZE",
    "myanmar": "MMR", "burma": "MMR",
    "palestine": "PSE", "palestinian": "PSE", "gaza": "PSE",
    "west bank": "PSE",
    "israel": "ISR", "israeli": "ISR", "tel aviv": "ISR",
    "ukraine": "UKR", "ukrainian": "UKR", "kyiv": "UKR",
    "taiwan": "TWN", "taipei": "TWN",
    "syria": "SYR", "syrian": "SYR", "damascus": "SYR",
    "iraq": "IRQ", "iraqi": "IRQ", "baghdad": "IRQ",
    "iran": "IRN", "iranian": "IRN", "tehran": "IRN",
    "turkey": "TUR", "turkish": "TUR", "turkiye": "TUR", "ankara": "TUR",
    "egypt": "EGY", "egyptian": "EGY", "cairo": "EGY",
    "saudi arabia": "SAU", "saudi": "SAU",
    "uae": "ARE", "emirates": "ARE", "dubai": "ARE",
    "new zealand": "NZL",
    "philippines": "PHL", "filipino": "PHL", "manila": "PHL",
    "indonesia": "IDN", "indonesian": "IDN", "jakarta": "IDN",
    "japan": "JPN", "japanese": "JPN", "tokyo": "JPN",
    "india": "IND", "indian": "IND", "delhi": "IND", "mumbai": "IND",
    "pakistan": "PAK", "pakistani": "PAK",
    "bangladesh": "BGD", "bangladeshi": "BGD", "dhaka": "BGD",
    "afghanistan": "AFG", "afghan": "AFG", "kabul": "AFG",
    "ethiopia": "ETH", "ethiopian": "ETH", "addis ababa": "ETH",
    "nigeria": "NGA", "nigerian": "NGA", "lagos": "NGA", "abuja": "NGA",
    "kenya": "KEN", "kenyan": "KEN", "nairobi": "KEN",
    "sudan": "SDN", "sudanese": "SDN", "khartoum": "SDN",
    "somalia": "SOM", "somali": "SOM", "mogadishu": "SOM",
    "south africa": "ZAF",
    "haiti": "HTI", "haitian": "HTI", "port-au-prince": "HTI",
    "ecuador": "ECU", "ecuadorian": "ECU", "quito": "ECU",
    "venezuela": "VEN", "venezuelan": "VEN", "caracas": "VEN",
    "colombia": "COL", "colombian": "COL", "bogota": "COL",
    "peru": "PER", "peruvian": "PER", "lima": "PER",
    "chile": "CHL", "chilean": "CHL", "santiago": "CHL",
    "brazil": "BRA", "brazilian": "BRA",
    "mexico": "MEX", "mexican": "MEX", "mexico city": "MEX",
    "canada": "CAN", "canadian": "CAN", "ottawa": "CAN",
    "australia": "AUS", "australian": "AUS",
    "germany": "DEU", "german": "DEU", "berlin": "DEU",
    "france": "FRA", "french": "FRA", "paris": "FRA",
    "italy": "ITA", "italian": "ITA", "rome": "ITA",
    "spain": "ESP", "spanish": "ESP", "madrid": "ESP",
    "poland": "POL", "polish": "POL", "warsaw": "POL",
    "hungary": "HUN", "hungarian": "HUN", "budapest": "HUN",
    "romania": "ROU", "romanian": "ROU",
    "greece": "GRC", "greek": "GRC", "athens": "GRC",
    "serbia": "SRB", "serbian": "SRB", "belgrade": "SRB",
    "libya": "LBY", "libyan": "LBY", "tripoli": "LBY",
    "yemen": "YEM", "yemeni": "YEM", "sanaa": "YEM",
    "lebanon": "LBN", "lebanese": "LBN", "beirut": "LBN",
    "tunisia": "TUN", "tunisian": "TUN", "tunis": "TUN",
    "morocco": "MAR", "moroccan": "MAR",
    "algeria": "DZA", "algerian": "DZA",
    "mozambique": "MOZ", "mozambican": "MOZ",
    "zimbabwe": "ZWE", "zimbabwean": "ZWE",
    "zambia": "ZMB", "zambian": "ZMB",
    "malawi": "MWI", "malawian": "MWI",
    "cameroon": "CMR", "cameroonian": "CMR",
    "ghana": "GHA", "ghanaian": "GHA",
    "senegal": "SEN", "senegalese": "SEN",
    "cuba": "CUB", "cuban": "CUB", "havana": "CUB",
    "trinidad and tobago": "TTO", "trinidad": "TTO",
    "jamaica": "JAM", "jamaican": "JAM",
    "sri lanka": "LKA", "sri lankan": "LKA",
    "nepal": "NPL", "nepali": "NPL", "nepalese": "NPL",
    "thailand": "THA", "thai": "THA", "bangkok": "THA",
    "vietnam": "VNM", "vietnamese": "VNM",
    "cambodia": "KHM", "cambodian": "KHM",
    "malaysia": "MYS", "malaysian": "MYS",
    "singapore": "SGP", "singaporean": "SGP",
    "fiji": "FJI", "fijian": "FJI",
    "papua new guinea": "PNG",
    "georgia": "GEO", "tbilisi": "GEO",
    "armenia": "ARM", "armenian": "ARM", "yerevan": "ARM",
    "azerbaijan": "AZE", "azerbaijani": "AZE", "baku": "AZE",
    "kazakhstan": "KAZ", "kazakh": "KAZ",
    "uzbekistan": "UZB", "uzbek": "UZB",
    "belarus": "BLR", "belarusian": "BLR", "minsk": "BLR",
    "moldova": "MDA", "moldovan": "MDA",
    "bolivia": "BOL", "bolivian": "BOL",
    "paraguay": "PRY", "paraguayan": "PRY",
    "uruguay": "URY", "uruguayan": "URY",
    "guatemala": "GTM", "guatemalan": "GTM",
    "honduras": "HND", "honduran": "HND",
    "el salvador": "SLV", "salvadoran": "SLV",
    "nicaragua": "NIC", "nicaraguan": "NIC",
    "costa rica": "CRI",
    "panama": "PAN", "panamanian": "PAN",
    "dominican republic": "DOM",
    "burkina faso": "BFA",
    "central african republic": "CAF",
    "equatorial guinea": "GNQ",
    "sierra leone": "SLE",
    "democratic republic of congo": "COD",
    "republic of congo": "COG",
}


def _build_country_lookup() -> None:
    """Build the country name -> ISO3 lookup from pycountry + extras."""
    for c in pycountry.countries:
        _COUNTRY_LOOKUP[c.name.lower()] = c.alpha_3
        if hasattr(c, "common_name"):
            _COUNTRY_LOOKUP[c.common_name.lower()] = c.alpha_3
        if hasattr(c, "official_name"):
            _COUNTRY_LOOKUP[c.official_name.lower()] = c.alpha_3
    _COUNTRY_LOOKUP.update(_EXTRA_NAMES)


_build_country_lookup()

# Sort by length descending so longer names match first
_SORTED_NAMES = sorted(_COUNTRY_LOOKUP.keys(), key=len, reverse=True)

# Short words that are too ambiguous to match without word boundaries
_BOUNDARY_ONLY = {"us", "uk", "uae", "drc", "lao", "mali", "chad", "niger",
                  "congo", "guinea", "jordan", "georgia", "indian", "french",
                  "spanish", "german", "greek", "thai", "cuban", "saudi"}

# Names that should never match (false positives)
_EXCLUDE_NAMES = {"new mexico", "mexico city", "guinea pig", "guinea pigs",
                  "new delhi", "south bend", "west ham"}

# Emergency-related keywords for relevance filtering
_RELEVANCE_KW = [
    "emergency", "martial law", "state of exception", "curfew",
    "disaster", "evacuat", "lockdown", "quarantine", "crisis",
    "decree", "declared", "executive order", "humanitarian",
]


def extract_countries_from_text(text: str) -> list[str]:
    """Extract ISO3 codes of countries mentioned in text."""
    text_lower = text.lower()
    found: list[str] = []
    seen_iso3: set[str] = set()

    # Check exclusions first
    for excl in _EXCLUDE_NAMES:
        text_lower = text_lower.replace(excl, " " * len(excl))

    for name in _SORTED_NAMES:
        if name in _BOUNDARY_ONLY:
            pattern = r'\b' + re.escape(name) + r'\b'
            if not re.search(pattern, text_lower):
                continue
        elif name not in text_lower:
            continue

        iso3 = _COUNTRY_LOOKUP[name]
        if iso3 not in seen_iso3:
            seen_iso3.add(iso3)
            found.append(iso3)
            # Replace matched text to prevent substring matches
            text_lower = text_lower.replace(name, " " * len(name))

    return found


def _is_relevant(title: str, matched_query: str = "") -> bool:
    """Return True if the article title seems related to emergencies."""
    t = title.lower()
    if any(kw in t for kw in _RELEVANCE_KW):
        return True
    # Also relevant if the search phrase itself appears in the title
    if matched_query:
        phrase = matched_query.strip('"').lower()
        if phrase in t:
            return True
    return False


def fetch_articles(query: str) -> list[dict]:
    """Fetch articles from GDELT DOC API for a single query phrase."""
    params = {
        "query": query,
        "mode": "artlist",
        "maxrecords": str(MAX_RECORDS),
        "format": "json",
        "sort": "datedesc",
        "timespan": "3months",
    }

    for attempt in range(4):
        try:
            resp = requests.get(BASE_URL, params=params, timeout=30)
            if resp.status_code == 429:
                wait = 5 * (attempt + 1)
                print(f"    Rate-limited, waiting {wait}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()
            return data.get("articles", [])
        except requests.exceptions.JSONDecodeError:
            print(f"  [WARN] Non-JSON response for {query}", file=sys.stderr)
            return []
        except requests.RequestException as exc:
            if attempt == 3:
                print(f"  [WARN] Failed after 4 attempts: {exc}", file=sys.stderr)
                return []
            time.sleep(3 * (attempt + 1))

    return []


def normalize_article(article: dict, query: str) -> dict:
    """Normalize a GDELT article, extracting mentioned countries from title."""
    title = article.get("title", "")
    mentioned_countries = extract_countries_from_text(title)

    raw_date = article.get("seendate", "")
    try:
        if "T" in raw_date:
            dt = datetime.strptime(raw_date[:15], "%Y%m%dT%H%M%S")
        else:
            dt = datetime.strptime(raw_date[:8], "%Y%m%d")
        date_str = dt.strftime("%Y-%m-%d")
    except (ValueError, IndexError):
        date_str = raw_date

    return {
        "source": "gdelt",
        "type": "article",
        "title": title,
        "date": date_str,
        "url": article.get("url", ""),
        "domain": article.get("domain", ""),
        "language": article.get("language", ""),
        "mentioned_countries": mentioned_countries,
        "iso3": mentioned_countries[0] if mentioned_countries else "",
        "socialimage": article.get("socialimage", ""),
        "matched_query": query,
    }


def main() -> None:
    """Run GDELT fetch pipeline."""
    print("[02] Fetching GDELT data...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    all_articles: list[dict] = []
    seen_urls: set[str] = set()

    for phrase in SOE_PHRASES:
        print(f"  GDELT: {phrase}")
        articles = fetch_articles(phrase)
        count = 0
        skipped_lang = 0
        skipped_relevance = 0
        for art in articles:
            # Skip non-English articles
            lang = art.get("language", "").lower()
            if lang and lang != "english":
                skipped_lang += 1
                continue
            normalized = normalize_article(art, phrase)
            # Skip articles with no emergency keyword in title
            if not _is_relevant(normalized["title"], normalized.get("matched_query", "")):
                skipped_relevance += 1
                continue
            url = normalized.get("url", "")
            if url and url not in seen_urls:
                seen_urls.add(url)
                all_articles.append(normalized)
                count += 1
        print(f"    → {count} new ({len(articles)} raw, {skipped_lang} non-EN, {skipped_relevance} irrelevant)")
        time.sleep(5)  # GDELT rate-limits aggressively

    with_country = sum(1 for a in all_articles if a["iso3"])
    print(f"  → {len(all_articles)} unique articles, {with_country} with country identified")

    output_path = OUTPUT_DIR / "gdelt_raw.json"
    output_path.write_text(
        json.dumps(
            {
                "fetched_at": datetime.now(timezone.utc).isoformat(),
                "article_count": len(all_articles),
                "with_country_count": with_country,
                "records": all_articles,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    print(f"  Wrote {len(all_articles)} records → {output_path.name}")


if __name__ == "__main__":
    main()
