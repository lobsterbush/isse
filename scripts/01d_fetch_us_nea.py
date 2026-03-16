"""Fetch US national emergency declarations from Wikipedia.

Scrapes the 'List of national emergencies in the United States' article
via the MediaWiki API, parses the table of declarations, and outputs
structured JSON with active/expired status.
"""

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parent.parent / "data"

WIKI_API = "https://en.wikipedia.org/w/api.php"
ARTICLE_TITLE = "List_of_national_emergencies_in_the_United_States"


def fetch_article_html(title: str) -> str:
    """Fetch parsed HTML of a Wikipedia article via the MediaWiki API."""
    params = {
        "action": "parse",
        "page": title,
        "format": "json",
        "prop": "text",
        "disablelimitreport": "true",
    }
    headers = {"User-Agent": "ISSE-Dashboard/1.0 (https://lobsterbush.github.io/isse/)"}
    resp = requests.get(WIKI_API, params=params, headers=headers, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return data["parse"]["text"]["*"]


def parse_emergencies(html: str) -> list[dict]:
    """Parse the emergencies table from article HTML."""
    soup = BeautifulSoup(html, "lxml")

    # Find the main table(s) — the article has a wikitable with emergency data
    tables = soup.find_all("table", class_="wikitable")
    if not tables:
        print("  [WARN] No wikitable found in article")
        return []

    records: list[dict] = []

    for table in tables:
        rows = table.find_all("tr")
        if not rows:
            continue

        # Try to identify header row
        headers = []
        header_row = rows[0]
        for th in header_row.find_all(["th", "td"]):
            headers.append(th.get_text(strip=True).lower())

        if not any("emergency" in h or "order" in h or "date" in h for h in headers):
            continue

        for row in rows[1:]:
            cells = row.find_all(["td", "th"])
            if len(cells) < 3:
                continue

            cell_texts = [c.get_text(strip=True) for c in cells]

            # Extract what we can from the row
            record = {"raw_cells": cell_texts}

            # Try to find date pattern (YYYY or Month Day, YYYY)
            date_found = False
            for i, text in enumerate(cell_texts):
                date_match = re.search(
                    r"(\w+ \d{1,2}, \d{4}|\d{4}-\d{2}-\d{2})", text
                )
                if date_match and not date_found:
                    record["date"] = date_match.group(1)
                    date_found = True

            # Look for EO/Proclamation numbers
            full_text = " ".join(cell_texts)
            eo_match = re.search(
                r"(?:Executive Order|E\.?O\.?)\s*(\d{4,5})", full_text
            )
            proc_match = re.search(
                r"(?:Proclamation|Proc\.?)\s*(\d{4,5})", full_text
            )
            if eo_match:
                record["instrument"] = f"EO {eo_match.group(1)}"
            elif proc_match:
                record["instrument"] = f"Proc. {proc_match.group(1)}"

            # Check status — look for "terminated", "revoked", "expired"
            text_lower = full_text.lower()
            if any(
                kw in text_lower
                for kw in ["terminated", "revoked", "expired", "ended"]
            ):
                record["active"] = False
            else:
                record["active"] = True

            # Title/description — usually the longest cell or one with descriptive text
            best_title = ""
            for text in cell_texts:
                if len(text) > len(best_title) and len(text) > 20:
                    best_title = text
            record["title"] = best_title[:200] if best_title else full_text[:200]

            # President — look for known president names
            presidents = [
                "Trump", "Biden", "Obama", "Bush", "Clinton",
                "Reagan", "Carter", "Ford", "Nixon",
            ]
            for pres in presidents:
                if pres in full_text:
                    record["president"] = pres
                    break

            records.append(record)

    return records


def main() -> None:
    """Run US NEA emergency scraper."""
    print("[01d] Fetching US national emergencies from Wikipedia...")
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    html = fetch_article_html(ARTICLE_TITLE)
    records = parse_emergencies(html)

    active = [r for r in records if r.get("active")]
    expired = [r for r in records if not r.get("active")]

    print(f"  Parsed {len(records)} entries ({len(active)} active, {len(expired)} expired)")

    output = {
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": f"https://en.wikipedia.org/wiki/{ARTICLE_TITLE}",
        "total_count": len(records),
        "active_count": len(active),
        "records": records,
    }

    out_path = DATA_DIR / "us_nea_emergencies.json"
    out_path.write_text(
        json.dumps(output, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"  → {out_path.name}")


if __name__ == "__main__":
    main()
