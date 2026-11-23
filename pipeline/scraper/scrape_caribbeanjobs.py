"""
CaribbeanJobs.com scraper — data science / data analyst / ML / software roles
Targets Trinidad & Tobago postings (also captures other Caribbean islands for
broader Caribbean analysis).

Strategy:
  1. Build a list of search URLs covering multiple job title keywords
  2. Scrape each search results page to collect job IDs
  3. Fetch each individual job page and extract the description
  4. Save per-job JSON + manifest (same schema as UWI course scraper)

Usage:
  python scrape_caribbeanjobs.py

Output:
  data/raw/job_postings/caribbean/  *.json  (one per job)
  data/raw/job_postings/caribbean/_manifest.json
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
BASE_URL = "https://www.caribbeanjobs.com"

SEARCH_KEYWORDS = [
    "data scientist",
    "data analyst",
    "machine learning",
    "software engineer",
    "software developer",
    "data engineer",
    "business intelligence",
    "artificial intelligence",
    "python developer",
    "systems analyst",
]

# LocationId=14 → Trinidad and Tobago only
# Set to "" to get all Caribbean
LOCATION_PARAM = "&LocationId=14"

MAX_PAGES_PER_KEYWORD = 5

OUTPUT_DIR = Path("data/raw/job_postings/caribbean")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = OUTPUT_DIR / "_manifest.json"

DELAY_MIN = 1.5
DELAY_MAX = 3.0

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def sleep():
    time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))


def get(url: str) -> requests.Response | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        return r
    except requests.RequestException as e:
        print(f"  [ERROR] {url}: {e}")
        return None


def extract_job_ids_from_search(html: str) -> list[tuple[str, str]]:
    soup = BeautifulSoup(html, "html.parser")
    results = []
    slug_pattern = re.compile(r"/(.+?-Job-(\d+)\.aspx)", re.IGNORECASE)
    query_pattern = re.compile(r"/JobDesc\.aspx\?Id=(\d+)", re.IGNORECASE)
    seen = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = slug_pattern.search(href)
        if m:
            job_id = m.group(2)
            if job_id not in seen:
                seen.add(job_id)
                results.append((job_id, BASE_URL + "/" + m.group(1)))
            continue
        m = query_pattern.search(href)
        if m:
            job_id = m.group(1)
            if job_id not in seen:
                seen.add(job_id)
                results.append((job_id, BASE_URL + href))
    return results


def extract_job_detail(job_id: str, url: str, html: str) -> dict:
    soup = BeautifulSoup(html, "html.parser")

    title = ""
    for sel in ["h1.job-title", "h1", ".jobTitle", "[class*='title']"]:
        tag = soup.select_one(sel)
        if tag and tag.get_text(strip=True):
            title = tag.get_text(strip=True)
            break

    company = ""
    for sel in [".company-name", ".employer", "h2", "[class*='company']"]:
        tag = soup.select_one(sel)
        if tag and tag.get_text(strip=True):
            company = tag.get_text(strip=True)
            break

    page_text = soup.get_text(" ", strip=True)

    location = ""
    loc_pat = (
        r"(Port[- ]of[- ]Spain|San Fernando|Chaguanas|Arima|Point Lisas|Couva|"
        r"Barataria|Trincity|San Juan|Valsayn|Piarco|Tobago|Kingston|Bridgetown|"
        r"St\.?\s*Michael|Nassau|Georgetown)"
    )
    m = re.search(loc_pat, page_text, re.IGNORECASE)
    if m:
        location = m.group(0)

    country = ""
    for pat, name in [
        (r"Trinidad(?:\s+and\s+Tobago)?", "Trinidad and Tobago"),
        (r"Barbados", "Barbados"),
        (r"Jamaica", "Jamaica"),
        (r"Guyana", "Guyana"),
        (r"St\.?\s*Lucia", "Saint Lucia"),
        (r"Grenada", "Grenada"),
    ]:
        if re.search(pat, page_text, re.IGNORECASE):
            country = name
            break

    description = ""
    for sel in [
        ".job-description", "#jobDescription", ".job-desc", ".description",
        "[class*='jobDesc']", "[class*='job-content']", "article",
        ".col-sm-8", ".col-md-8", "main",
    ]:
        tag = soup.select_one(sel)
        if tag:
            text = tag.get_text(" ", strip=True)
            if len(text) > 200:
                description = text
                break

    if not description:
        body_parts = []
        capture = False
        for tag in soup.find_all(["h2", "h3", "p", "li", "ul", "ol"]):
            if tag.name in ("h2", "h3"):
                capture = True
            if capture:
                txt = tag.get_text(" ", strip=True)
                if txt:
                    body_parts.append(txt)
        description = " ".join(body_parts)

    is_expired = bool(re.search(
        r"This job is expired|job has expired", page_text, re.IGNORECASE
    ))

    return {
        "job_id": job_id,
        "url": url,
        "title": title,
        "company": company,
        "location": location,
        "country": country,
        "is_expired": is_expired,
        "description": description,
        "char_count": len(description),
        "source": "caribbeanjobs.com",
    }


def is_meaningful(job: dict) -> bool:
    return job["char_count"] > 150


# ---------------------------------------------------------------------------
# Main crawl
# ---------------------------------------------------------------------------

def collect_job_ids(location_filter: str = LOCATION_PARAM) -> list[tuple[str, str]]:
    all_ids: dict[str, str] = {}

    for keyword in SEARCH_KEYWORDS:
        kw_encoded = keyword.replace(" ", "+")
        for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
            search_url = (
                f"{BASE_URL}/ShowResults.aspx"
                f"?Keywords={kw_encoded}"
                f"&autosuggestEndpoint=%2Fautosuggest"
                f"{location_filter}"
                f"&Category="
                f"&Recruiter=Company%2CAgency"
                f"&PageNumber={page}"
                f"&btnSubmit=Search"
            )
            print(f"  Searching: {keyword!r} page {page} ...")
            resp = get(search_url)
            sleep()
            if not resp:
                break

            ids = extract_job_ids_from_search(resp.text)
            if not ids:
                break

            for job_id, url in ids:
                if job_id not in all_ids:
                    all_ids[job_id] = url

            if "No results found" in resp.text or "no results" in resp.text.lower():
                break

    return list(all_ids.items())


def scrape_jobs(job_ids: list[tuple[str, str]]) -> list[dict]:
    results = []
    for i, (job_id, url) in enumerate(job_ids, 1):
        out_path = OUTPUT_DIR / f"{job_id}.json"

        if out_path.exists():
            with open(out_path, encoding="utf-8") as f:
                job = json.load(f)
            results.append(job)
            print(f"  [{i}/{len(job_ids)}] {job_id} — cached")
            continue

        print(f"  [{i}/{len(job_ids)}] Fetching {job_id} ...")
        resp = get(url)
        sleep()
        if not resp:
            results.append({
                "job_id": job_id, "url": url, "title": "", "company": "",
                "location": "", "country": "", "is_expired": False,
                "description": "", "char_count": 0, "source": "caribbeanjobs.com",
            })
            continue

        job = extract_job_detail(job_id, url, resp.text)
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2, ensure_ascii=False)

        status = "OK" if is_meaningful(job) else "EMPTY"
        print(f"    [{status}] {job['title']!r} @ {job['company']!r} ({job['country']}) — {job['char_count']} chars")
        results.append(job)

    return results


def write_manifest(jobs: list[dict]):
    meaningful = [j for j in jobs if is_meaningful(j)]
    tt_jobs = [j for j in meaningful if "Trinidad" in j.get("country", "")]

    manifest = {
        "total_found": len(jobs),
        "meaningful": len(meaningful),
        "trinidad_tobago": len(tt_jobs),
        "other_caribbean": len(meaningful) - len(tt_jobs),
        "jobs": [
            {
                "job_id": j["job_id"],
                "title": j["title"],
                "company": j["company"],
                "location": j["location"],
                "country": j["country"],
                "is_expired": j["is_expired"],
                "char_count": j["char_count"],
                "url": j["url"],
                "has_content": is_meaningful(j),
            }
            for j in jobs
        ],
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Caribbean jobs scrape complete")
    print(f"  Total found      : {manifest['total_found']}")
    print(f"  With content     : {manifest['meaningful']}")
    print(f"  Trinidad & Tobago: {manifest['trinidad_tobago']}")
    print(f"  Other Caribbean  : {manifest['other_caribbean']}")
    print(f"  Manifest         : {MANIFEST_PATH}")


if __name__ == "__main__":
    print("Phase 1: Collecting job IDs from search results...")
    job_ids = collect_job_ids(location_filter=LOCATION_PARAM)
    print(f"  Found {len(job_ids)} unique job IDs\n")

    print("Phase 2: Fetching individual job pages...")
    jobs = scrape_jobs(job_ids)

    print("\nPhase 3: Writing manifest...")
    write_manifest(jobs)