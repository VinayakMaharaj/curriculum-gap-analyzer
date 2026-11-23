"""
Indeed Canada scraper — Mohammed baseline (replaces defunct Workopolis).
HTML scraping of ca.indeed.com across Toronto / Vancouver / Remote.

Usage:
  python scrape_indeed_canada.py

Output:
  data/raw/job_postings/indeed_canada/  *.json
  data/raw/job_postings/indeed_canada/_manifest.json
"""

import json
import re
import time
import random
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
SEARCH_KEYWORDS = [
    "data scientist",
    "data analyst",
    "machine learning engineer",
    "data engineer",
    "software engineer",
]

LOCATIONS = ["Toronto, Ontario", "Vancouver, BC", "Montreal, Quebec", "Remote"]

OUTPUT_DIR = Path("data/raw/job_postings/indeed_canada")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = OUTPUT_DIR / "_manifest.json"

DELAY_MIN = 2.0
DELAY_MAX = 4.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-CA,en;q=0.9",
    "Referer": "https://ca.indeed.com/",
}

INDEED_BASE = "https://ca.indeed.com"
MAX_PAGES_PER_SEARCH = 5   # 15 results/page → 75 max per keyword+location


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sleep():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def get(url: str, session: requests.Session) -> requests.Response | None:
    try:
        r = session.get(url, timeout=20)
        r.raise_for_status()
        return r
    except requests.RequestException as e:
        print(f"  [ERROR] {url}: {e}")
        return None


def extract_jk_ids(html: str) -> list[str]:
    return list(set(re.findall(r'"jk":"([a-f0-9]{16})"', html)))


def search_indeed(keyword: str, location: str, page: int, session: requests.Session) -> list[str]:
    start = page * 15
    kw_encoded = keyword.replace(" ", "+")
    loc_encoded = location.replace(" ", "+").replace(",", "%2C")
    url = (
        f"{INDEED_BASE}/jobs"
        f"?q={kw_encoded}&l={loc_encoded}"
        f"&start={start}&sort=date"
    )
    print(f"    p{page+1}: {keyword!r} in {location} ...")
    resp = get(url, session)
    sleep()
    if not resp:
        return []
    return extract_jk_ids(resp.text)


def fetch_job_detail(jk: str, session: requests.Session) -> dict | None:
    url = f"{INDEED_BASE}/viewjob?jk={jk}"
    resp = get(url, session)
    sleep()
    if not resp:
        return None

    soup = BeautifulSoup(resp.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    title = ""
    for sel in [
        "h1[data-testid='jobsearch-JobInfoHeader-title']",
        "h1.jobsearch-JobInfoHeader-title",
        "h1",
    ]:
        tag = soup.select_one(sel)
        if tag:
            title = tag.get_text(strip=True)
            break

    company = ""
    for sel in [
        "[data-testid='inlineHeader-companyName']",
        ".jobsearch-CompanyInfoWithoutHeaderImage span",
        ".icl-u-lg-mr--sm",
    ]:
        tag = soup.select_one(sel)
        if tag:
            company = tag.get_text(strip=True)
            break

    location = ""
    for sel in [
        "[data-testid='job-location']",
        "[class*='companyLocation']",
    ]:
        tag = soup.select_one(sel)
        if tag:
            location = tag.get_text(strip=True)
            break

    description = ""
    for sel in [
        "#jobDescriptionText",
        ".jobsearch-jobDescriptionText",
        "div[data-testid='job-description']",
    ]:
        tag = soup.select_one(sel)
        if tag:
            description = tag.get_text(" ", strip=True)
            if len(description) > 200:
                break

    salary = ""
    m = re.search(r"\$[\d,]+(?:\s*[-–]\s*\$[\d,]+)?(?:\s*(?:per|a)\s+\w+)?", page_text, re.IGNORECASE)
    if m:
        salary = m.group(0)

    return {
        "job_id": jk,
        "url": url,
        "title": title,
        "company": company,
        "location": location,
        "country": "Canada",
        "salary": salary,
        "description": description,
        "char_count": len(description),
        "source": "ca.indeed.com",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_scrape() -> list[dict]:
    session = requests.Session()
    session.headers.update(HEADERS)

    try:
        session.get(INDEED_BASE, timeout=10)
        sleep()
    except Exception:
        pass

    all_jks: set[str] = set()
    for keyword in SEARCH_KEYWORDS:
        for location in LOCATIONS:
            for page in range(MAX_PAGES_PER_SEARCH):
                jks = search_indeed(keyword, location, page, session)
                if not jks:
                    break
                all_jks.update(jks)
                if len(jks) < 15:
                    break

    print(f"\n  Found {len(all_jks)} unique job IDs — fetching details...")
    jobs = []
    jk_list = list(all_jks)

    for i, jk in enumerate(jk_list, 1):
        out_path = OUTPUT_DIR / f"{jk}.json"
        if out_path.exists():
            with open(out_path, encoding="utf-8") as f:
                job = json.load(f)
            jobs.append(job)
            print(f"  [{i}/{len(jk_list)}] {jk} — cached")
            continue

        print(f"  [{i}/{len(jk_list)}] {jk} ...")
        job = fetch_job_detail(jk, session)
        if not job:
            continue

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2, ensure_ascii=False)

        status = "OK" if job["char_count"] > 150 else "EMPTY"
        print(f"    [{status}] {job['title']!r} @ {job['company']!r} — {job['char_count']} chars")
        jobs.append(job)

    return jobs


def write_manifest(jobs: list[dict]):
    meaningful = [j for j in jobs if j.get("char_count", 0) > 150]
    manifest = {
        "total_found": len(jobs),
        "meaningful": len(meaningful),
        "source": "ca.indeed.com",
        "keywords": SEARCH_KEYWORDS,
        "locations": LOCATIONS,
        "jobs": [
            {
                "job_id": j["job_id"],
                "title": j.get("title", ""),
                "company": j.get("company", ""),
                "location": j.get("location", ""),
                "country": "Canada",
                "char_count": j.get("char_count", 0),
                "url": j.get("url", ""),
                "has_content": j.get("char_count", 0) > 150,
            }
            for j in jobs
        ],
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Indeed Canada scrape complete")
    print(f"  Total found  : {manifest['total_found']}")
    print(f"  With content : {manifest['meaningful']}")
    print(f"  Manifest     : {MANIFEST_PATH}")


if __name__ == "__main__":
    jobs = run_scrape()
    write_manifest(jobs)