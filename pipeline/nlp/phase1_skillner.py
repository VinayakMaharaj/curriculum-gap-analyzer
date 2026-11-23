"""
Phase 1 — SkillNER extraction on job + course corpora.
Replicates Mohammed et al. skill extraction step.
"""

import json
import sys
import hashlib
from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────────────
ROOT         = Path(__file__).resolve().parents[2]
JOB_CORPUS   = ROOT / "data" / "raw" / "job_postings"  / "_corpus.json"
COURSE_CORPUS= ROOT / "data" / "raw" / "course_outlines" / "_corpus.json"
OUT_DIR      = ROOT / "data" / "processed"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# tmp file to normalise job corpus into list-of-dicts with a "text" field
JOB_CORPUS_TMP = OUT_DIR / "_jobs_tmp.json"


# ── SkillNER loader ──────────────────────────────────────────────────────────
def load_skillner():
    try:
        import spacy
        from spacy.matcher import PhraseMatcher
        from skillNer.skill_extractor_class import SkillExtractor
        from skillNer.general_params import SKILL_DB
    except ImportError as e:
        print(f"\n[ERROR] Missing dependency: {e}")
        print("Install with:")
        print("  pip install skillNer")
        print("  pip install ipython")
        print("  python -m spacy download en_core_web_lg")
        sys.exit(1)

    print("Loading spaCy model (en_core_web_lg)...")
    nlp = spacy.load("en_core_web_lg")
    print("Initialising SkillNER...")
    extractor = SkillExtractor(nlp, SKILL_DB, PhraseMatcher)
    return extractor


# ── Skill extraction ─────────────────────────────────────────────────────────
def extract_skills(extractor, text: str) -> list[str]:
    if not text or len(text) < 20:
        return []
    try:
        annotations = extractor.annotate(text[:5000])
        skills = []
        results = annotations.get("results", {})
        for match in results.get("full_matches", []):
            val = match.get("doc_node_value", "").lower().strip()
            if val:
                skills.append(val)
        for match in results.get("ngram_scored", []):
            if match.get("score", 0) >= 0.8:
                val = match.get("doc_node_value", "").lower().strip()
                if val:
                    skills.append(val)
        return list(set(skills))
    except Exception:
        return []


# ── Corpus processor ─────────────────────────────────────────────────────────
def process_corpus(extractor, records: list, label: str):
    """
    records: list of dicts, each must have a "text" field (and optionally "id").
    Returns:
        results  — list of {id, skills}
        freq     — {skill: count_of_docs_mentioning_it}
    """
    results = []
    freq    = {}
    total   = len(records)

    for i, rec in enumerate(records):
        if i % 100 == 0:
            print(f"  [{label}] {i}/{total} ...")

        text = rec.get("text", "") or rec.get("description", "") or ""
        doc_id = rec.get("id") or rec.get("course_id") or rec.get("job_id") or str(i)

        skills = extract_skills(extractor, text)
        results.append({"id": doc_id, "skills": skills})

        seen = set()
        for s in skills:
            if s not in seen:
                freq[s] = freq.get(s, 0) + 1
                seen.add(s)

    print(f"  [{label}] done — {total} docs, {len(freq)} unique skills")
    return results, freq


# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    extractor = load_skillner()

    # ── Job corpus ──
    print(f"\nLoading job corpus: {JOB_CORPUS}")
    raw_jobs = json.loads(JOB_CORPUS.read_text(encoding="utf-8"))

    # Corpus may be a list or a dict with a "jobs" key
    if isinstance(raw_jobs, list):
        job_records = raw_jobs
    elif isinstance(raw_jobs, dict):
        job_records = raw_jobs.get("jobs") or raw_jobs.get("postings") or []
    else:
        print("[ERROR] Unexpected job corpus format")
        sys.exit(1)

    # Normalise: each record needs a "text" field
    for rec in job_records:
        if "text" not in rec:
            # Try common field names
            rec["text"] = (
                rec.get("description", "") or
                rec.get("body", "") or
                rec.get("full_text", "") or
                rec.get("job_description", "") or
                ""
            )

    print(f"  {len(job_records)} job records loaded")

    # ── Course corpus ──
    print(f"\nLoading course corpus: {COURSE_CORPUS}")
    raw_courses = json.loads(COURSE_CORPUS.read_text(encoding="utf-8"))

    if isinstance(raw_courses, list):
        course_records = raw_courses
    elif isinstance(raw_courses, dict):
        course_records = raw_courses.get("courses") or []
    else:
        print("[ERROR] Unexpected course corpus format")
        sys.exit(1)

    for rec in course_records:
        if "text" not in rec:
            rec["text"] = (
                rec.get("description", "") or
                rec.get("body", "") or
                rec.get("content", "") or
                ""
            )

    print(f"  {len(course_records)} course records loaded")

    # ── Extract ──
    print("\n--- Extracting skills from job postings ---")
    job_results, job_freq = process_corpus(extractor, job_records, "jobs")

    print("\n--- Extracting skills from course outlines ---")
    course_results, course_freq = process_corpus(extractor, course_records, "courses")

    # ── Save outputs ──
    print("\nSaving outputs...")

    (OUT_DIR / "skills_jobs.json").write_text(
        json.dumps(job_results, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "skills_courses.json").write_text(
        json.dumps(course_results, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "skill_freq_jobs.json").write_text(
        json.dumps(job_freq, indent=2), encoding="utf-8"
    )
    (OUT_DIR / "skill_freq_courses.json").write_text(
        json.dumps(course_freq, indent=2), encoding="utf-8"
    )

    # ── Summary ──
    top_job_skills = sorted(job_freq.items(), key=lambda x: x[1], reverse=True)[:20]
    top_course_skills = sorted(course_freq.items(), key=lambda x: x[1], reverse=True)[:20]

    print("\n=== TOP 20 SKILLS IN JOB POSTINGS ===")
    for skill, count in top_job_skills:
        pct = count / len(job_records) * 100
        print(f"  {skill:<40} {count:>4} docs ({pct:.1f}%)")

    print("\n=== TOP 20 SKILLS IN COURSE OUTLINES ===")
    for skill, count in top_course_skills:
        pct = count / len(course_records) * 100
        print(f"  {skill:<40} {count:>4} docs ({pct:.1f}%)")

    print(f"\n✓ Phase 1 SkillNER complete.")
    print(f"  Jobs:    {len(job_records)} docs, {len(job_freq)} unique skills")
    print(f"  Courses: {len(course_records)} docs, {len(course_freq)} unique skills")
    print(f"  Outputs in: {OUT_DIR}")


if __name__ == "__main__":
    main()