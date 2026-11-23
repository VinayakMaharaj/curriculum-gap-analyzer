"""
Canada job scraper — Mohammed et al. baseline (via JobDataLake REST API).
Replaces the defunct Indeed HTML scraper.

API docs: https://api.jobdatalake.com
1 credit per request. Free tier: 1,000 credits.

Usage:
  python scrape_indeed_canada.py

Output:
  data/raw/job_postings/indeed_canada/  *.json
  data/raw/job_postings/indeed_canada/_manifest.json
"""

import json
import time
import re
import hashlib
from pathlib import Path
import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
JDL_API_KEY  = "jdl_9d853acd0702540ed477a9f75d98f1a70d688007dd332f57"
JDL_BASE     = "https://api.jobdatalake.com/v1"

SEARCH_KEYWORDS = [
    "data scientist",
    "data analyst",
    "machine learning engineer",
    "data engineer",
    "software engineer",
]

PER_PAGE     = 100
MAX_PAGES    = 3        # 15 credits total for search calls
COUNTRY      = "CA"

OUTPUT_DIR   = Path("data/raw/job_postings/indeed_canada")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
MANIFEST_PATH = OUTPUT_DIR / "_manifest.json"

HEADERS = {"X-API-Key": JDL_API_KEY}

DELAY = 0.15   # 10 req/sec rate limit → safe at ~6/sec


# ---------------------------------------------------------------------------
# DS relevance filter (title-based)
# ---------------------------------------------------------------------------
DS_TITLE_KEYWORDS = {
    "data scientist", "data analyst", "data engineer", "machine learning",
    "ml engineer", "ai engineer", "analytics engineer", "business intelligence",
    "bi developer", "bi engineer", "nlp", "deep learning", "llm",
    "applied scientist", "research scientist", "decision scientist",
    "data platform", "mlops", "data architect", "quantitative analyst",
    "software engineer", "software developer", "systems analyst",
}

def is_ds_relevant(title: str) -> bool:
    t = title.lower()
    return any(kw in t for kw in DS_TITLE_KEYWORDS)


def safe_filename(handle: str) -> str:
    """Return a filename-safe version of a job handle.
    Windows MAX_PATH is 260; keep it short by hashing long handles."""
    if len(handle) <= 80:
        # Sanitize any characters Windows dislikes
        safe = re.sub(r'[\\/:*?"<>|]', '_', handle)
        return safe + ".json"
    # Hash long handles to 16-char hex
    short = hashlib.md5(handle.encode()).hexdigest()[:16]
    return short + ".json"


# ---------------------------------------------------------------------------
# API calls
# ---------------------------------------------------------------------------

def search_jobs(keyword: str, page: int) -> dict:
    params = {
        "q":         keyword,
        "countries": COUNTRY,
        "page":      page,
        "per_page":  PER_PAGE,
        "sort_by":   "posted_at:desc",
    }
    try:
        r = requests.get(f"{JDL_BASE}/jobs", headers=HEADERS, params=params, timeout=15)
        if r.status_code == 402:
            print("  [!] Out of credits — stopping.")
            return {}
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [ERROR] search {keyword!r} p{page}: {e}")
        return {}


def get_job_detail(handle: str) -> dict | None:
    try:
        r = requests.get(f"{JDL_BASE}/jobs/{handle}", headers=HEADERS, timeout=15)
        if r.status_code == 404:
            return None
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  [ERROR] detail {handle}: {e}")
        return None


# ---------------------------------------------------------------------------
# Build job record from listing + optional detail
# ---------------------------------------------------------------------------

def build_job_record(listing: dict, detail: dict | None = None) -> dict:
    src = detail if detail else listing

    description = src.get("description", "") or ""

    # Strip HTML if present
    if "<" in description:
        description = re.sub(r"<[^>]+>", " ", description)
        description = re.sub(r"\s+", " ", description).strip()

    # Build pseudo-description from structured fields if no detail
    if not description:
        parts = []
        skills = listing.get("required_skills", [])
        if skills:
            parts.append("Required skills: " + ", ".join(skills))
        seniority = listing.get("seniority", [])
        if seniority:
            parts.append("Seniority: " + ", ".join(seniority))
        sal_min = listing.get("salary_min_usd")
        sal_max = listing.get("salary_max_usd")
        if sal_min:
            parts.append(f"Salary: ${sal_min}k–${sal_max}k USD" if sal_max else f"Salary from ${sal_min}k USD")
        emp_type = listing.get("employment_type", "")
        if emp_type:
            parts.append(f"Employment type: {emp_type}")
        description = " | ".join(parts)

    locations = listing.get("locations", [])
    location  = locations[0] if locations else ""

    return {
        "job_id":      listing.get("job_handle", listing.get("id", "")),
        "url":         listing.get("url", ""),
        "title":       listing.get("title", ""),
        "company":     listing.get("company_name", ""),
        "location":    location,
        "country":     "Canada",
        "salary": (
            f"${listing['salary_min_usd']}k–${listing['salary_max_usd']}k"
            if listing.get("salary_min_usd") else ""
        ),
        "skills":      listing.get("required_skills", []),
        "seniority":   listing.get("seniority", []),
        "remote_type": listing.get("remote_type", ""),
        "posted_at":   listing.get("posted_at", ""),
        "description": description,
        "char_count":  len(description),
        "source":      "jobdatalake.com/CA",
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run_scrape() -> list[dict]:
    all_listings: dict[str, dict] = {}   # handle → listing dict
    credits_used = 0

    # Phase 1: search calls
    print("Phase 1: Searching JobDataLake for Canada DS jobs...")
    for keyword in SEARCH_KEYWORDS:
        print(f"\n  Keyword: {keyword!r}")
        for page in range(1, MAX_PAGES + 1):
            print(f"    Page {page} ...")
            data = search_jobs(keyword, page)
            credits_used += 1
            time.sleep(DELAY)

            if not data:
                break

            jobs = data.get("jobs", [])
            if not jobs:
                print("    No more results.")
                break

            found_total = data.get("found", "?")
            print(f"    {len(jobs)} results (total found: {found_total})")

            for j in jobs:
                handle = j.get("job_handle") or j.get("id", "")
                if handle and handle not in all_listings:
                    if is_ds_relevant(j.get("title", "")):
                        all_listings[handle] = j

            total_pages = -(-data.get("found", 0) // PER_PAGE)
            if page >= total_pages:
                break

    print(f"\n  Search phase done. Credits used: {credits_used}")
    print(f"  Unique DS-relevant listings: {len(all_listings)}")

    # Phase 2: fetch full descriptions where needed
    print("\nPhase 2: Fetching full descriptions...")
    jobs_out = []
    handles = list(all_listings.keys())

    for i, handle in enumerate(handles, 1):
        fname    = safe_filename(handle)          # ← short, safe filename
        out_path = OUTPUT_DIR / fname

        # Use cache if already fetched and has content
        if out_path.exists():
            with open(out_path, encoding="utf-8") as f:
                job = json.load(f)
            if job.get("char_count", 0) > 50:
                jobs_out.append(job)
                print(f"  [{i}/{len(handles)}] {handle[:60]} — cached ({job['char_count']} chars)")
                continue

        listing = all_listings[handle]

        # Only fetch detail if listing is thin (< 3 skills)
        needs_detail = len(listing.get("required_skills", [])) < 3
        detail = None
        if needs_detail and credits_used < 950:
            detail = get_job_detail(handle)
            credits_used += 1
            time.sleep(DELAY)

        job = build_job_record(listing, detail)

        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(job, f, indent=2, ensure_ascii=False)

        status = "DETAIL" if detail else "LISTING"
        print(f"  [{i}/{len(handles)}] [{status}] {job['title']!r} @ {job['company']!r} — {job['char_count']} chars")
        jobs_out.append(job)

    print(f"\n  Total credits used: {credits_used}")
    return jobs_out


def write_manifest(jobs: list[dict]):
    meaningful = [j for j in jobs if j.get("char_count", 0) > 50]
    manifest = {
        "total_found":  len(jobs),
        "meaningful":   len(meaningful),
        "source":       "jobdatalake.com/CA",
        "keywords":     SEARCH_KEYWORDS,
        "country":      "Canada",
        "jobs": [
            {
                "job_id":      j["job_id"],
                "title":       j.get("title", ""),
                "company":     j.get("company", ""),
                "location":    j.get("location", ""),
                "country":     "Canada",
                "skills":      j.get("skills", []),
                "char_count":  j.get("char_count", 0),
                "url":         j.get("url", ""),
                "has_content": j.get("char_count", 0) > 50,
            }
            for j in jobs
        ],
    }
    with open(MANIFEST_PATH, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Canada scrape complete (JobDataLake)")
    print(f"  Total found  : {manifest['total_found']}")
    print(f"  With content : {manifest['meaningful']}")
    print(f"  Manifest     : {MANIFEST_PATH}")


if __name__ == "__main__":
    jobs = run_scrape()
    write_manifest(jobs)