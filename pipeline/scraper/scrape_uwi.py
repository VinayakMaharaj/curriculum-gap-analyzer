"""
pipeline/scraper/scrape_uwi.py

Scrapes all UWI B.Sc. Computer Science (Special) course pages and saves
raw text to data/raw/course_outlines/. One JSON file per course.

Usage:
    python pipeline/scraper/scrape_uwi.py
"""

import json
import time
import logging
from pathlib import Path
from dataclasses import dataclass, asdict

import requests
from bs4 import BeautifulSoup

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

OUTPUT_DIR = Path("data/raw/course_outlines")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

REQUEST_DELAY = 1.5  # seconds between requests — polite scraping

COURSES = [
    # Level 1
    ("COMP1600", "https://sta.uwi.edu/fst/dcit/content/comp1600"),
    ("COMP1601", "https://sta.uwi.edu/fst/dcit/content/comp-1601"),
    ("COMP1602", "https://sta.uwi.edu/fst/dcit/content/comp1602"),
    ("COMP1603", "https://sta.uwi.edu/fst/dcit/content/comp1603"),
    ("COMP1604", "https://sta.uwi.edu/fst/dcit/content/comp1604"),
    ("INFO1600", "https://sta.uwi.edu/fst/dcit/content/info1600"),
    ("INFO1601", "https://sta.uwi.edu/fst/dcit/content/info1601"),
    ("MATH1115", "https://sta.uwi.edu/fst/dcit/content/math1115"),
    # Level II/III Core
    ("COMP2601", "https://sta.uwi.edu/fst/dcit/content/comp2601"),
    ("COMP2602", "https://sta.uwi.edu/fst/dcit/content/comp2602"),
    ("COMP2603", "https://sta.uwi.edu/fst/dcit/content/comp2603"),
    ("COMP2604", "https://sta.uwi.edu/fst/dcit/content/comp2604"),
    ("COMP2605", "https://sta.uwi.edu/fst/dcit/content/comp2605"),
    ("COMP2606", "https://sta.uwi.edu/fst/dcit/content/comp2606"),
    ("COMP2611", "https://sta.uwi.edu/fst/dcit/content/comp-2611"),
    ("INFO2602", "https://sta.uwi.edu/fst/dcit/content/info2602"),
    ("INFO2604", "https://sta.uwi.edu/fst/dcit/content/info2604"),
    ("MATH2250", "https://sta.uwi.edu/fst/dcit/content/math2250"),
    ("COMP3601", "https://sta.uwi.edu/fst/dcit/content/comp3601"),
    ("COMP3602", "https://sta.uwi.edu/fst/dcit/content/comp3602"),
    ("COMP3603", "https://sta.uwi.edu/fst/dcit/content/comp3603"),
    ("COMP3991", "https://sta.uwi.edu/fst/dcit/content/comp-3991"),
    ("INFO3604", "https://sta.uwi.edu/fst/dcit/content/info3604"),
    # Level II/III Electives
    ("COMP3605", "https://sta.uwi.edu/fst/dcit/content/comp3605"),
    ("COMP3606", "https://sta.uwi.edu/fst/dcit/content/comp3606"),
    ("COMP3607", "https://sta.uwi.edu/fst/dcit/content/comp3607"),
    ("COMP3608", "https://sta.uwi.edu/fst/dcit/content/comp3608"),
    ("COMP3609", "https://sta.uwi.edu/fst/dcit/content/comp3609"),
    ("COMP3610", "https://sta.uwi.edu/fst/dcit/content/comp3610"),
    ("COMP3611", "https://sta.uwi.edu/fst/dcit/content/comp3611"),
    ("COMP3612", "https://sta.uwi.edu/fst/dcit/content/comp3612"),
    ("COMP3613", "https://sta.uwi.edu/fst/dcit/content/comp3613"),
    ("INFO2605", "https://sta.uwi.edu/fst/dcit/content/info2605"),
    ("INFO3600", "https://sta.uwi.edu/fst/dcit/content/info3600"),
    ("INFO3605", "https://sta.uwi.edu/fst/dcit/content/info3605"),
    ("INFO3606", "https://sta.uwi.edu/fst/dcit/content/info3606"),
    ("INFO3607", "https://sta.uwi.edu/fst/dcit/content/info3607"),
    ("INFO3608", "https://sta.uwi.edu/fst/dcit/content/info3608"),
    ("INFO3609", "https://sta.uwi.edu/fst/dcit/content/info3609"),
    ("INFO3610", "https://sta.uwi.edu/fst/dcit/content/info3610"),
    ("INFO3611", "https://sta.uwi.edu/fst/dcit/content/info3611"),
    ("INFO3612", "https://sta.uwi.edu/fst/dcit/content/info-3612"),
    # Foundation
    ("FOUN1101", "https://sta.uwi.edu/fst/dcit/content/foun1101"),
    ("FOUN1105", "https://sta.uwi.edu/fst/dcit/content/foun1105"),
    ("FOUN1301", "https://sta.uwi.edu/fst/dcit/content/foun1301"),
]


@dataclass
class CourseRecord:
    code: str
    url: str
    title: str
    description: str
    raw_text: str
    scrape_status: str  # "ok" | "failed" | "empty"


def extract_course_content(soup: BeautifulSoup) -> dict:
    """
    Pull title and description text from a UWI course page.
    The pages are simple — title in <h1>, body content in the main
    content region. We grab all paragraph text in the content area.
    """
    title = ""
    description = ""
    raw_text = ""

    # Title — usually in <h1> or <h2>
    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(strip=True)

    # Main content area — UWI pages use a div with class "field-items"
    # or similar Drupal content regions. Try a few selectors.
    content_selectors = [
        {"class": "field-items"},
        {"class": "field-item"},
        {"id": "content"},
        {"class": "region-content"},
    ]

    content_div = None
    for selector in content_selectors:
        content_div = soup.find("div", selector)
        if content_div:
            break

    # Fallback: grab all <p> tags on the page
    if content_div:
        paragraphs = content_div.find_all("p")
        raw_text = " ".join(p.get_text(strip=True) for p in paragraphs)
    else:
        paragraphs = soup.find_all("p")
        raw_text = " ".join(p.get_text(strip=True) for p in paragraphs)

    # Description is the full raw text — we'll clean it in preprocessing
    description = raw_text

    return {"title": title, "description": description, "raw_text": raw_text}


def scrape_course(code: str, url: str, session: requests.Session) -> CourseRecord:
    try:
        response = session.get(url, timeout=15)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        content = extract_course_content(soup)

        status = "ok" if content["raw_text"].strip() else "empty"

        return CourseRecord(
            code=code,
            url=url,
            title=content["title"],
            description=content["description"],
            raw_text=content["raw_text"],
            scrape_status=status,
        )

    except Exception as e:
        logger.error(f"Failed to scrape {code} ({url}): {e}")
        return CourseRecord(
            code=code,
            url=url,
            title="",
            description="",
            raw_text="",
            scrape_status="failed",
        )


def main():
    session = requests.Session()
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (curriculum-gap-research; academic use)"
    })

    results = []
    failed = []

    logger.info(f"Scraping {len(COURSES)} UWI course pages...")

    for i, (code, url) in enumerate(COURSES):
        logger.info(f"[{i+1}/{len(COURSES)}] {code}")
        record = scrape_course(code, url, session)
        results.append(record)

        if record.scrape_status != "ok":
            failed.append(code)

        # Save individually as we go — if it crashes midway, we keep progress
        out_path = OUTPUT_DIR / f"{code}.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(asdict(record), f, indent=2, ensure_ascii=False)

        time.sleep(REQUEST_DELAY)

    # Save a combined manifest
    manifest_path = OUTPUT_DIR / "_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "total": len(results),
                "ok": len([r for r in results if r.scrape_status == "ok"]),
                "failed": failed,
                "courses": [asdict(r) for r in results],
            },
            f,
            indent=2,
            ensure_ascii=False,
        )

    logger.info(f"Done. {len(results) - len(failed)}/{len(results)} succeeded.")
    if failed:
        logger.warning(f"Failed courses: {failed}")
    logger.info(f"Output: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    main()