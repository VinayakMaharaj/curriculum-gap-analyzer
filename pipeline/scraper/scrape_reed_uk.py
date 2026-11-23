"""
Reed UK scraper — Mohammed et al. baseline replication.
Uses the Reed public REST API (free key at reed.co.uk/developers).
Falls back to HTML scraping if no key is set.

Usage:
  REED_API_KEY=your_key python scrape_reed_uk.py
  # Windows PowerShell:
  $env:REED_API_KEY = "your-key-here"; python scrape_reed_uk.py

Output:
  data/raw/job_postings/reed_uk/  *.json
  data/raw/job_postings/reed_uk/_manifest.json
"""

import json
import os
import re
import time
import random
import base64
from pathlib import Path
import requests
from bs4 import BeautifulSoup

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
REED_API_KEY = os.environ.get("REED_API_KEY", "")
REED_API_BASE = "https://www.reed.co.uk/api/1.0"

SEARCH_KEYWORDS = [
    "data scientist",
    "data analyst",
    "machine learning engineer",
    "data engineer",
]

RESULTS_PER_PAGE = 100
MAX_PAGES_PER_KEYWORD = 5

OUTPUT_DIR = Path("data/raw/job_postings/reed_uk")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = OUTPUT_DIR / "_manifest.json"

DELAY_MIN = 0.5
DELAY_MAX = 1.5

HEADERS_HTML = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-GB,en;q=0.9",
}

# ---------------------------------------------------------------------------
# API path
# ---------------------------------------------------------------------------

def api_headers() -> dict:
    creds = base64.b64encode(f"{REED_API_KEY}:".encode()).decode()
    return {"Authorization": f"Basic {creds}", "Content-Type": "application/json"}


def api_search(keyword: str, results_to_take: int = RESULTS_PER_PAGE, skip: int = 0) -> list[dict]:
    url = f"{REED_API_BASE}/search"
    params = {"keywords": keyword, "resultsToTake": results_to_take, "resultsToSkip": skip}
    try:
        r = requests.get(url, params=params, headers=api_headers(), timeout=15)
        r.raise_for_status()
        return r.json().get("results", [])
    except Exception as e:
        print(f"  [API ERROR] {e}")
        return []


def api_get_job(job_id: int) -> dict | None:
    url = f"{REED_API_BASE}/jobs/{job_id}"
    try:
        r = requests.get(url, headers=api_headers(), timeout=15)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [API ERROR] job {job_id}: {e}")
        return None


# ---------------------------------------------------------------------------
# HTML fallback
# ---------------------------------------------------------------------------

def html_search(keyword: str, page: int = 1) -> list[tuple[str, str]]:
    kw_encoded = keyword.replace(" ", "-")
    url = f"https://www.reed.co.uk/jobs/{kw_encoded}-jobs?pageno={page}"
    try:
        r = requests.get(url, headers=HEADERS_HTML, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  [HTML ERROR] {e}")
        return []

    soup = BeautifulSoup(r.text, "html.parser")
    results = []
    for a in soup.find_all("a", href=True):
        href = a["href"]
        m = re.search(r"/jobs/[^/]+/(\d+)", href)
        if m:
            job_id = m.group(1)
            full_url = "https://www.reed.co.uk" + href if href.startswith("/") else href
            results.append((job_id, full_url))
    return list(dict(results).items())


def html_get_job(job_id: str, url: str) -> dict | None:
    try:
        r = requests.get(url, headers=HEADERS_HTML, timeout=15)
        r.raise_for_status()
    except Exception as e:
        print(f"  [HTML ERROR] {e}")
        return None

    soup = BeautifulSoup(r.text, "html.parser")
    page_text = soup.get_text(" ", strip=True)

    description = ""
    title = ""
    company = ""
    location = ""

    # Strategy 1: JSON-LD (most reliable — Reed often embeds full JobPosting here)
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0]
            if data.get("@type") == "JobPosting":
                title = data.get("title", "")
                description = data.get("description", "")
                loc_obj = data.get("jobLocation", {})
                if isinstance(loc_obj, list):
                    loc_obj = loc_obj[0] if loc_obj else {}
                location = loc_obj.get("address", {}).get("addressLocality", "")
                company = data.get("hiringOrganization", {}).get("name", "")
                break
        except Exception:
            continue

    # Strategy 2: Embedded JSON in script tags (Next.js __NEXT_DATA__ or similar)
    if not description:
        for script in soup.find_all("script"):
            txt = script.string or ""
            if '"jobDescription"' in txt:
                m = re.search(r'"jobDescription"\s*:\s*"((?:[^"\\]|\\.)+)"', txt)
                if m:
                    try:
                        description = bytes(m.group(1), "utf-8").decode("unicode_escape")
                    except Exception:
                        description = m.group(1)
                    break
            if '"description"' in txt and '"JobPosting"' in txt:
                m = re.search(r'"description"\s*:\s*"((?:[^"\\]|\\.)+)"', txt)
                if m:
                    try:
                        description = bytes(m.group(1), "utf-8").decode("unicode_escape")
                    except Exception:
                        description = m.group(1)
                    break

    # Strategy 3: CSS selectors
    if not description:
        for sel in [
            ".job-description",
            "#jobDescription",
            "[data-qa='jobDescription']",
            ".description-container",
            "article .content",
            ".col-sm-8 .text",
            ".col-sm-8",
            ".col-md-8",
            "main article",
            "article",
        ]:
            tag = soup.select_one(sel)
            if tag:
                text = tag.get_text(" ", strip=True)
                if len(text) > 200:
                    description = text
                    break

    # Strategy 4: Largest text block heuristic
    if not description:
        candidates = []
        for tag in soup.find_all(["div", "section", "article"]):
            text = tag.get_text(" ", strip=True)
            if len(text) > 300:
                candidates.append(text)
        if candidates:
            description = max(candidates, key=len)

    # Strip HTML tags from description if it came from JSON-LD/JSON
    if description and "<" in description:
        desc_soup = BeautifulSoup(description, "html.parser")
        description = desc_soup.get_text(" ", strip=True)

    # Title fallbacks
    if not title:
        for sel in ["h1.job-header__title", "h1[data-qa='jobTitle']", "h1"]:
            tag = soup.select_one(sel)
            if tag and tag.get_text(strip=True):
                title = tag.get_text(strip=True)
                break

    # Company fallbacks
    if not company:
        for sel in [
            ".job-header__company-name",
            "[data-qa='companyName']",
            ".employer-name",
            "[class*='company']",
        ]:
            tag = soup.select_one(sel)
            if tag and tag.get_text(strip=True):
                company = tag.get_text(strip=True)
                break

    # Location fallbacks
    if not location:
        for sel in [
            "[data-qa='jobLocation']",
            ".job-header__location",
            ".location",
            "[class*='location']",
        ]:
            tag = soup.select_one(sel)
            if tag and tag.get_text(strip=True):
                location = tag.get_text(strip=True)
                break

    salary = ""
    m = re.search(r"£[\d,]+(?:\s*[-–]\s*£[\d,]+)?(?:\s*per\s+\w+)?", page_text)
    if m:
        salary = m.group(0)

    return {
        "job_id": str(job_id),
        "url": url,
        "title": title,
        "company": company,
        "location": location,
        "country": "United Kingdom",
        "salary": salary,
        "description": description,
        "char_count": len(description),
        "source": "reed.co.uk",
    }


# ---------------------------------------------------------------------------
# Unified scrape
# ---------------------------------------------------------------------------

def scrape_via_api() -> list[dict]:
    all_jobs: dict[str, dict] = {}

    for keyword in SEARCH_KEYWORDS:
        print(f"\n  Keyword: {keyword!r}")
        for page in range(MAX_PAGES_PER_KEYWORD):
            skip = page * RESULTS_PER_PAGE
            print(f"    Page {page+1} (skip={skip}) ...")
            summaries = api_search(keyword, skip=skip)
            if not summaries:
                print("    No more results.")
                break

            for s in summaries:
                job_id = str(s.get("jobId", ""))
                if not job_id or job_id in all_jobs:
                    continue

                out_path = OUTPUT_DIR / f"{job_id}.json"
                if out_path.exists():
                    with open(out_path, encoding="utf-8") as f:
                        all_jobs[job_id] = json.load(f)
                    continue

                detail = api_get_job(int(job_id))
                time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
                if not detail:
                    continue

                job = {
                    "job_id": job_id,
                    "url": f"https://www.reed.co.uk/jobs/{job_id}",
                    "title": detail.get("jobTitle", s.get("jobTitle", "")),
                    "company": detail.get("employerName", s.get("employerName", "")),
                    "location": detail.get("locationName", s.get("locationName", "")),
                    "country": "United Kingdom",
                    "salary": detail.get("salary", ""),
                    "description": detail.get("jobDescription", ""),
                    "char_count": len(detail.get("jobDescription", "")),
                    "source": "reed.co.uk",
                    "date_posted": detail.get("date", ""),
                }

                with open(out_path, "w", encoding="utf-8") as f:
                    json.dump(job, f, indent=2, ensure_ascii=False)

                print(f"      {job['title']!r} @ {job['company']!r} — {job['char_count']} chars")
                all_jobs[job_id] = job

    return list(all_jobs.values())


def scrape_via_html() -> list[dict]:
    all_ids: dict[str, str] = {}

    for keyword in SEARCH_KEYWORDS:
        print(f"\n  Keyword: {keyword!r} (HTML fallback)")
        for page in range(1, MAX_PAGES_PER_KEYWORD + 1):
            ids = html_search(keyword, page)
            if not ids:
                break
            for job_id, url in ids:
                if job_id not in all_ids:
                    all_ids[job_id] = url
            time.sleep(random.uniform(DELAY_MIN * 2, DELAY_MAX * 2))

    print(f"\n  Found {len(all_ids)} unique job IDs — fetching details...")
    jobs = []
    for i, (job_id, url) in enumerate(all_ids.items(), 1):
        out_path = OUTPUT_DIR / f"{job_id}.json"
        if out_path.exists():
            existing = json.load(open(out_path, encoding="utf-8"))
            # Re-fetch if previously empty
            if existing.get("char_count", 0) > 150:
                jobs.append(existing)
                print(f"  [{i}/{len(all_ids)}] {job_id} — cached ({existing['char_count']} chars)")
                continue
            else:
                print(f"  [{i}/{len(all_ids)}] {job_id} — re-fetching (was empty)")

        print(f"  [{i}/{len(all_ids)}] {job_id} ...")
        job = html_get_job(job_id, url)
        time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))
        if not job:
            continue
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2, ensure_ascii=False)

        status = "OK" if job["char_count"] > 150 else "EMPTY"
        print(f"    [{status}] {job['title']!r} @ {job.get('company','')!r} — {job['char_count']} chars")
        jobs.append(job)

    return jobs


def write_manifest(jobs: list[dict]):
    meaningful = [j for j in jobs if j.get("char_count", 0) > 150]
    manifest = {
        "total_found": len(jobs),
        "meaningful": len(meaningful),
        "source": "reed.co.uk",
        "keywords": SEARCH_KEYWORDS,
        "jobs": [
            {
                "job_id": j["job_id"],
                "title": j.get("title", ""),
                "company": j.get("company", ""),
                "location": j.get("location", ""),
                "country": "United Kingdom",
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
    print(f"Reed UK scrape complete")
    print(f"  Total found  : {manifest['total_found']}")
    print(f"  With content : {manifest['meaningful']}")
    print(f"  Manifest     : {MANIFEST_PATH}")


if __name__ == "__main__":
    if REED_API_KEY:
        print(f"Using Reed API (key detected: {REED_API_KEY[:8]}...)")
        jobs = scrape_via_api()
    else:
        print("No REED_API_KEY set — using HTML scraping (may be less reliable)")
        print("Get a free key: https://www.reed.co.uk/developers/jobseeker")
        jobs = scrape_via_html()

    write_manifest(jobs)