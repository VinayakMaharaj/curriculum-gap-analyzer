"""
Master runner — executes all three job scrapers and builds a unified corpus.

Usage:
  python run_job_scrapers.py                  # run all
  python run_job_scrapers.py --source caribbean
  python run_job_scrapers.py --corpus-only    # just rebuild corpus from saved files

Output:
  data/raw/job_postings/_corpus.json   ← unified file for NLP pipeline
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path

OUTPUT_DIR = Path("data/raw/job_postings")
CORPUS_PATH = OUTPUT_DIR / "_corpus.json"

SCRAPERS = {
    "caribbean": "pipeline/scraper/scrape_caribbeanjobs.py",
    "canada":    "pipeline/scraper/scrape_indeed_canada.py",
    "uk":        "pipeline/scraper/scrape_reed_uk.py",
}

SOURCE_DIRS = {
    "caribbean": OUTPUT_DIR / "caribbean",
    "canada":    OUTPUT_DIR / "indeed_canada",
    "uk":        OUTPUT_DIR / "reed_uk",
}

MARKET_LABELS = {
    "caribbean": "Caribbean",
    "canada":    "Canada",
    "uk":        "UK",
}

# ---------------------------------------------------------------------------
# Relevance filter — keeps only DS/ML/SWE-relevant jobs by title
# ---------------------------------------------------------------------------
DS_TITLE_KEYWORDS = {
    "data", "analyst", "scientist", "machine learning", "ml", "ai",
    "artificial intelligence", "analytics", "business intelligence", "bi",
    "python", "nlp", "deep learning", "llm", "software engineer",
    "software developer", "systems analyst", "platform engineer",
    "data platform", "databricks", "snowflake", "spark", "etl",
    "data warehouse", "data lake", "data architect", "mlops",
    "decision science", "quantitative", "quant", "research engineer",
    "applied scientist", "computer vision", "data science",
}

def is_ds_relevant(job: dict) -> bool:
    title = job.get("title", "").lower()
    return any(kw in title for kw in DS_TITLE_KEYWORDS)


# ---------------------------------------------------------------------------
# Corpus builder
# ---------------------------------------------------------------------------

def run_scraper(source: str):
    script = SCRAPERS[source]
    print(f"\n{'='*60}")
    print(f"Running {source} scraper: {script}")
    print('='*60)
    result = subprocess.run([sys.executable, script], check=False)
    if result.returncode != 0:
        print(f"[WARNING] {source} scraper exited with code {result.returncode}")


def build_corpus():
    corpus = []
    skipped_empty = 0
    skipped_irrelevant = 0

    for source, dir_path in SOURCE_DIRS.items():
        if not dir_path.exists():
            print(f"  [SKIP] {dir_path} not found")
            continue

        market = MARKET_LABELS[source]
        json_files = [f for f in dir_path.glob("*.json") if f.name != "_manifest.json"]

        for f in json_files:
            try:
                with open(f, encoding="utf-8") as fp:
                    job = json.load(fp)
            except Exception as e:
                print(f"  [ERROR] {f}: {e}")
                continue

            if job.get("char_count", 0) < 150:
                skipped_empty += 1
                continue

            # Caribbean jobs: skip relevance filter — corpus is small and
            # keywords were already targeted; keep everything with content.
            if market != "Caribbean" and not is_ds_relevant(job):
                skipped_irrelevant += 1
                continue

            corpus.append({
                "job_id":      job.get("job_id", f.stem),
                "source":      job.get("source", source),
                "market":      market,
                "title":       job.get("title", ""),
                "company":     job.get("company", ""),
                "location":    job.get("location", ""),
                "country":     job.get("country", ""),
                "description": job.get("description", ""),
                "char_count":  job.get("char_count", 0),
                "url":         job.get("url", ""),
            })

    by_market: dict[str, int] = {}
    for job in corpus:
        m = job["market"]
        by_market[m] = by_market.get(m, 0) + 1

    with open(CORPUS_PATH, "w", encoding="utf-8") as f:
        json.dump(corpus, f, indent=2, ensure_ascii=False)

    print(f"\n{'='*60}")
    print(f"Unified corpus: {CORPUS_PATH}")
    print(f"  Total kept       : {len(corpus)}")
    for market, count in sorted(by_market.items()):
        print(f"    {market}: {count}")
    print(f"  Skipped (empty)  : {skipped_empty}")
    print(f"  Skipped (off-topic): {skipped_irrelevant}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--source",
        choices=["caribbean", "canada", "uk", "all"],
        default="all",
    )
    parser.add_argument("--corpus-only", action="store_true")
    args = parser.parse_args()

    if not args.corpus_only:
        sources = ["caribbean", "canada", "uk"] if args.source == "all" else [args.source]
        for source in sources:
            run_scraper(source)

    print("\nBuilding unified corpus...")
    build_corpus()