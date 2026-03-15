"""Fetch ICCPR Article 4(3) derogation notifications from the UN Treaty Collection.

States that formally derogate from the ICCPR must notify the UN Secretary-General.
These notifications are the gold standard for verified states of emergency.

Scrapes the ICCPR treaty page's "Notifications under Article 4(3)" section,
which lists all derogation notifications by country with dates and text.

Outputs data/iccpr_derogations.json — consumed by 03_merge_and_classify.py.
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
ICCPR_URL = (
    "https://treaties.un.org/Pages/ViewDetailsIII.aspx"
    "?src=TREATY&mtdsg_no=IV-4&chapter=4&Temp=mtdsg3&clang=_en"
)
UA = {"User-Agent": "ISSE-Dashboard/1.0 (https://statesofexception.org)"}
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data"

# Phrases indicating a derogation was terminated/withdrawn
_TERMINATION_PHRASES = [
    "terminat", "withdraw", "lifted", "revok", "end of the state of emergency",
    "ceased to apply", "no longer in effect", "restored",
    "state of emergency was not renewed", "restrictions have been removed",
    "emergency has ended", "emergency was lifted",
]

# Country name overrides for pycountry lookup
_COUNTRY_MAP: dict[str, str] = {
    "bolivia (plurinational state of)": "BOL",
    "iran (islamic republic of)": "IRN",
    "republic of korea": "KOR",
    "republic of moldova": "MDA",
    "russian federation": "RUS",
    "state of palestine": "PSE",
    "türkiye": "TUR",
    "united kingdom of great britain and northern ireland": "GBR",
    "venezuela (bolivarian republic of)": "VEN",
    "yugoslavia (former)": None,  # Skip
}


def _resolve_country(name: str) -> str | None:
    """Resolve a country name from the UN treaty page to ISO3."""
    key = name.lower().strip()
    if key in _COUNTRY_MAP:
        return _COUNTRY_MAP[key]
    try:
        c = pycountry.countries.lookup(name)
        return c.alpha_3
    except LookupError:
        pass
    try:
        results = pycountry.countries.search_fuzzy(name)
        if results:
            return results[0].alpha_3
    except LookupError:
        pass
    return None


def _extract_dates(text: str) -> list[str]:
    """Extract all dates from notification text."""
    dates = []
    # Pattern: "20 March 2020" or "3 January 2026"
    for m in re.finditer(
        r"(\d{1,2}\s+(?:January|February|March|April|May|June|July|"
        r"August|September|October|November|December)\s+\d{4})", text
    ):
        try:
            dt = datetime.strptime(m.group(1), "%d %B %Y")
            dates.append(dt.strftime("%Y-%m-%d"))
        except ValueError:
            pass
    return dates


def _is_terminated(text: str) -> bool:
    """Check if a notification indicates the derogation was terminated."""
    t = text.lower()
    return any(phrase in t for phrase in _TERMINATION_PHRASES)


def _classify_type(text: str) -> str:
    """Classify emergency type from derogation notification text."""
    t = text.lower()
    if any(kw in t for kw in ["martial law", "coup", "military", "armed conflict", "invasion", "war"]):
        return "conflict"
    if any(kw in t for kw in ["covid", "pandemic", "health", "disease"]):
        return "public_health"
    if any(kw in t for kw in ["earthquake", "flood", "hurricane", "disaster", "cyclone"]):
        return "disaster"
    return "governance"


def fetch_and_parse() -> list[dict]:
    """Fetch the ICCPR treaty page and parse Article 4(3) notifications.

    The UN Treaty Collection page structure is:
      div.heading-four
        div.bold  "Notifications under Article 4 (3) ..."
      div (sibling)
        table.structTable
          tr (one per country, 47 rows)
            td
              div.structTableHead  → country name
              div                  → notification text
    """
    print("  Fetching UN Treaty Collection ICCPR page...")
    try:
        resp = requests.get(ICCPR_URL, headers=UA, timeout=60)
        resp.raise_for_status()
    except requests.RequestException as exc:
        print(f"  [ERROR] Failed to fetch ICCPR page: {exc}", file=sys.stderr)
        return []

    print(f"  Downloaded {len(resp.text) // 1024}KB, parsing...")
    soup = BeautifulSoup(resp.text, "lxml")

    # Find the bold heading "Notifications under Article 4 (3) ..."
    bold_heading = None
    for div in soup.find_all("div", class_="bold"):
        if "Notifications under Article 4" in div.get_text():
            bold_heading = div
            break

    if not bold_heading:
        print("  [ERROR] Could not find Article 4(3) section", file=sys.stderr)
        return []

    # Navigate: bold → parent (heading-four) → next sibling → table.structTable
    heading_four = bold_heading.parent
    sibling_div = heading_four.find_next_sibling("div")
    if not sibling_div:
        print("  [ERROR] No sibling div after heading", file=sys.stderr)
        return []

    table = sibling_div.find("table", class_="structTable")
    if not table:
        print("  [ERROR] No structTable found", file=sys.stderr)
        return []

    # Parse each table row — one row per country
    records: list[dict] = []
    for row in table.find_all("tr"):
        cell = row.find("td")
        if not cell:
            continue
        head = cell.find("div", class_="structTableHead")
        if not head:
            continue

        country_name = head.get_text(strip=True)
        iso3 = _resolve_country(country_name)
        if not iso3:
            continue

        # Notification text is in the next sibling div(s) after the header
        notifications: list[str] = []
        for sib in head.find_next_siblings("div"):
            text = sib.get_text(" ", strip=True)
            if text and len(text) > 20:
                notifications.append(text)

        if notifications:
            records.append(_build_record(country_name, iso3, notifications))

    return records


def _build_record(country_name: str, iso3: str, notifications: list[str]) -> dict:
    """Build a derogation record from a country's notifications."""
    full_text = " ".join(notifications)

    # Get proper country name from pycountry
    try:
        c = pycountry.countries.get(alpha_3=iso3)
        display_name = getattr(c, "common_name", c.name) if c else country_name
    except (LookupError, AttributeError):
        display_name = country_name

    # Extract all dates
    all_dates = _extract_dates(full_text)
    first_date = min(all_dates) if all_dates else ""
    latest_date = max(all_dates) if all_dates else ""

    # Determine if still active: check the last notification block
    last_notification = notifications[-1] if notifications else ""
    terminated = _is_terminated(last_notification)

    # Also check for recent years — if no recent activity, likely terminated
    recent_years = re.findall(r"\b(202[0-6])\b", full_text)
    latest_year = max(int(y) for y in recent_years) if recent_years else 0

    # Classify emergency type
    etype = _classify_type(full_text)

    # Build title from most recent notification (first 150 chars)
    title_text = last_notification.split(".")[0][:150] if last_notification else ""
    # Clean up
    title_text = re.sub(r"\s{2,}", " ", title_text).strip()
    if title_text and not title_text.endswith("."):
        title_text += "…"

    return {
        "iso3": iso3,
        "country": display_name,
        "emergency_type": etype,
        "title": title_text,
        "first_notification": first_date,
        "latest_notification": latest_date,
        "earliest_date": first_date,
        "latest_date": latest_date,
        "notification_count": len(notifications),
        "latest_year": latest_year,
        "terminated": terminated,
        "active": not terminated and latest_year >= 2020,
        "confidence": 0.90 if (not terminated and latest_year >= 2022) else 0.70,
        "summary": title_text,
        "source_url": ICCPR_URL,
        "source_type": "iccpr",
    }


def main() -> None:
    """Run ICCPR derogation scraper."""
    print("[01c] Fetching ICCPR Article 4(3) derogation notifications...")
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    records = fetch_and_parse()

    active = [r for r in records if r.get("active")]
    terminated = [r for r in records if not r.get("active")]

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": ICCPR_URL,
        "description": (
            "ICCPR Article 4(3) derogation notifications from the "
            "UN Treaty Collection. States must formally notify the "
            "UN Secretary-General when declaring a state of emergency "
            "that derogates from ICCPR obligations."
        ),
        "total_countries": len(records),
        "active_count": len(active),
        "terminated_count": len(terminated),
        "records": records,
    }

    out_path = OUTPUT_DIR / "iccpr_derogations.json"
    out_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"  → {len(records)} countries with derogation history")
    print(f"  → {len(active)} potentially active derogations")
    for r in active:
        print(f"    {r['iso3']}  {r['country']:25s}  since {r['latest_notification'][:10]}")
    print(f"  → {len(terminated)} terminated/historical")
    print(f"  → Wrote {out_path.name}")


if __name__ == "__main__":
    main()
