"""
Patch script: retry failed/empty courses with alternate URL patterns.
Run from repo root: python pipeline/scraper/patch_failed_courses.py
"""

import json
import time
import logging
import requests
from bs4 import BeautifulSoup
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

BASE_URL = "https://sta.uwi.edu/fst/dcit/content"
OUTPUT_DIR = Path("data/raw/course_outlines")
MANIFEST_PATH = OUTPUT_DIR / "_manifest.json"

HEADERS = {
    "User-Agent": "UWI Curriculum Research Bot - Academic project (vinayak.maharaj@mail.utoronto.ca)"
}

# Courses to retry with multiple URL pattern attempts
RETRY_TARGETS = {
    "COMP1600": ["comp-1600", "comp1600", "comp_1600"],
    "COMP1602": ["comp-1602", "comp1602", "comp_1602"],
    "COMP1603": ["comp-1603", "comp1603", "comp_1603"],
    "MATH1115": ["math-1115", "math1115", "math_1115"],
    "FOUN1105": ["foun-1105", "foun1105", "foun_1105"],
    "FOUN1301": ["foun-1301", "foun1301", "foun_1301"],
    # Also retry the near-empty ones
    "COMP2603": ["comp-2603", "comp2603"],
    "COMP2611": ["comp2611", "comp-2611"],  # already has hyphen, try without
    "INFO2602": ["info-2602", "info2602"],
}

SELECTORS = [
    "div.field-items",
    "div.field-item",
    "div.content",
    "div.region-content",
    "div#content",
    "article",
    "main",
]

def fetch_description(url: str) -> tuple[str, str]:
    """Returns (title, description) or ('', '') on failure."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return "", ""
        soup = BeautifulSoup(r.text, "html.parser")
        title = soup.title.string.strip() if soup.title else ""
        for sel in SELECTORS:
            tag = soup.select_one(sel)
            if tag:
                text = tag.get_text(" ", strip=True)
                if len(text) > 50:  # must have real content
                    return title, text
        # fallback: all <p> tags
        paras = soup.find_all("p")
        text = " ".join(p.get_text(" ", strip=True) for p in paras)
        if len(text) > 50:
            return title, text
        return title, ""
    except Exception:
        return "", ""


def is_meaningful(desc: str) -> bool:
    """True if the description has actual course content, not just ASSESSMENT boilerplate."""
    stripped = desc.strip()
    if not stripped:
        return False
    # Near-empty patterns
    junk_only = ["ASSESSMENT", "No final written examination", "Course is offered by"]
    if all(j in stripped for j in ["ASSESSMENT"]) and len(stripped) < 60:
        return False
    return len(stripped) > 80


def main():
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)

    # Build lookup by code
    course_map = {c["code"]: c for c in manifest["courses"]}

    improved = 0

    for code, slugs in RETRY_TARGETS.items():
        current = course_map.get(code, {})
        current_desc = current.get("description", "")

        if is_meaningful(current_desc):
            log.info(f"[SKIP] {code} already has good content")
            continue

        log.info(f"[RETRY] {code} — trying {len(slugs)} URL patterns")
        best_desc = current_desc
        best_url = current.get("url", "")
        found = False

        for slug in slugs:
            url = f"{BASE_URL}/{slug}"
            if url == current.get("url"):
                continue  # already tried this exact URL
            log.info(f"  → {url}")
            title, desc = fetch_description(url)
            time.sleep(1.2)

            if is_meaningful(desc):
                log.info(f"  ✓ Got content ({len(desc)} chars)")
                best_desc = desc
                best_url = url
                found = True
                break
            else:
                log.info(f"  ✗ Empty or junk ({len(desc)} chars)")

        if found:
            # Update manifest entry
            course_map[code]["description"] = best_desc
            course_map[code]["raw_text"] = best_desc
            course_map[code]["url"] = best_url
            course_map[code]["scrape_status"] = "ok"

            # Save individual JSON
            out_path = OUTPUT_DIR / f"{code}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(course_map[code], f, indent=2, ensure_ascii=False)
            log.info(f"  Saved {out_path.name}")
            improved += 1
        else:
            log.warning(f"  [FAIL] {code} — no content found on any URL pattern")

    # Recount
    ok_count = sum(1 for c in course_map.values() if is_meaningful(c.get("description", "")))
    failed = [c["code"] for c in course_map.values() if not is_meaningful(c.get("description", ""))]

    # Update manifest
    manifest["courses"] = list(course_map.values())
    manifest["ok"] = ok_count
    manifest["failed"] = failed

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    log.info(f"\nDone. Improved {improved} courses.")
    log.info(f"Final: {ok_count}/45 with meaningful content")
    if failed:
        log.warning(f"Still empty: {failed}")


if __name__ == "__main__":
    main()