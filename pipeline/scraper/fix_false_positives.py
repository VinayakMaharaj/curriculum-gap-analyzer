"""
Fix false positives: courses that got the UWI 404 error page instead of real content.
Run from repo root: python pipeline/scraper/fix_false_positives.py
"""

import json
import logging
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

OUTPUT_DIR = Path("data/raw/course_outlines")
MANIFEST_PATH = OUTPUT_DIR / "_manifest.json"

# Dead giveaway strings from the UWI 404 page
ERROR_PAGE_SIGNALS = [
    "you came across this error",
    "page you were trying to visit does not exist",
    "we've recently redesigned the site",
    "servicedesk@sta.uwi.edu",
]

def is_error_page(text: str) -> bool:
    t = text.lower()
    return any(signal in t for signal in ERROR_PAGE_SIGNALS)

def is_meaningful(desc: str) -> bool:
    if not desc or not desc.strip():
        return False
    if is_error_page(desc):
        return False
    stripped = desc.strip()
    # Near-empty assessment boilerplate
    if len(stripped) < 80:
        return False
    # Only assessment text, no actual course description
    if stripped.upper().startswith("ASSESSMENT") and len(stripped) < 100:
        return False
    return True

def main():
    with open(MANIFEST_PATH, encoding="utf-8") as f:
        manifest = json.load(f)

    reverted = []
    for course in manifest["courses"]:
        desc = course.get("description", "")
        if is_error_page(desc):
            log.warning(f"[REVERT] {course['code']} — was 404 error page, clearing")
            course["description"] = ""
            course["raw_text"] = ""
            course["scrape_status"] = "empty"
            reverted.append(course["code"])

            # Update individual JSON file too
            out_path = OUTPUT_DIR / f"{course['code']}.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(course, f, indent=2, ensure_ascii=False)

    # Recount
    ok_courses = [c for c in manifest["courses"] if is_meaningful(c.get("description", ""))]
    empty_courses = [c["code"] for c in manifest["courses"] if not is_meaningful(c.get("description", ""))]

    manifest["ok"] = len(ok_courses)
    manifest["failed"] = empty_courses

    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    log.info(f"\nReverted {len(reverted)} false positives: {reverted}")
    log.info(f"Final honest count: {len(ok_courses)}/45 with real content")
    log.warning(f"Genuinely empty: {empty_courses}")

if __name__ == "__main__":
    main()