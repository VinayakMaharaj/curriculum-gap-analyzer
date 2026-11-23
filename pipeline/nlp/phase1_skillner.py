"""
phase1_skillner.py
──────────────────
Phase 1: Reproduce Mohammed et al. baseline.

Steps:
  1. Load job corpus + course outline corpus
  2. Run SkillNER on each document → extract skill mentions
  3. Save per-document skill lists + aggregated skill frequencies
  4. Output: data/processed/skills_jobs.json
             data/processed/skills_courses.json
             data/processed/skill_freq_jobs.json
             data/processed/skill_freq_courses.json

SkillNER uses spaCy + a curated EMSI/Lightcast skill taxonomy.
Install deps first (run once):
  pip install spacy skillner --break-system-packages
  python -m spacy download en_core_web_lg
"""

import json
import pathlib
import sys
from collections import Counter, defaultdict

# ── Paths ──────────────────────────────────────────────────────────────────────
RAW        = pathlib.Path("data/raw")
PROCESSED  = pathlib.Path("data/processed")
PROCESSED.mkdir(parents=True, exist_ok=True)

JOB_CORPUS    = RAW / "job_postings"    / "_corpus.json"
COURSE_CORPUS = RAW / "course_outlines" / "_corpus.json"

# ── Lazy imports (give helpful error if not installed) ─────────────────────────
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
        print("  python -m spacy download en_core_web_lg")
        sys.exit(1)

    print("Loading spaCy model (en_core_web_lg)...")
    try:
        import spacy
        nlp = spacy.load("en_core_web_lg")
    except OSError:
        print("[ERROR] spaCy model not found. Run:")
        print("  python -m spacy download en_core_web_lg")
        sys.exit(1)

    print("Initialising SkillNER...")
    from spacy.matcher import PhraseMatcher
    extractor = SkillExtractor(nlp, SKILL_DB, PhraseMatcher)
    return extractor


def extract_skills(extractor, text: str) -> list[str]:
    """Return list of skill strings found in text."""
    if not text or len(text) < 20:
        return []
    try:
        annotations = extractor.annotate(text[:5000])  # cap at 5k chars
        skills = []
        # skillNer returns results dict with full_matches and ngram_scored
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


def process_corpus(extractor, corpus_path: pathlib.Path, label: str):
    data = json.loads(corpus_path.read_text())
    docs = data.get("courses") or data.get("jobs") or []

    # job corpus uses a flat list; course corpus has {"courses": [...]}
    # job _corpus.json root is a flat list
    if isinstance(data, list):
        docs = data
    elif "courses" in data:
        docs = data["courses"]
    else:
        docs = data  # fallback

    results = []
    freq    = Counter()
    total   = len(docs)

    print(f"\n[{label}] Processing {total} documents...")
    for i, doc in enumerate(docs):
        if i % 100 == 0:
            print(f"  {i}/{total}", end="\r")

        text = doc.get("description", "")
        skills = extract_skills(extractor, text)

        doc_id = (
            doc.get("course_id")
            or doc.get("job_id")
            or f"{label}_{i}"
        )

        results.append({
            "id":     doc_id,
            "source": doc.get("source") or doc.get("campus_short") or label,
            "title":  doc.get("title", ""),
            "skills": skills,
            "n_skills": len(skills),
        })
        freq.update(skills)

    print(f"  {total}/{total} ✓")
    print(f"  Unique skills found: {len(freq)}")
    print(f"  Docs with ≥1 skill:  {sum(1 for r in results if r['n_skills'] > 0)}")

    return results, freq


def save(obj, path: pathlib.Path):
    path.write_text(json.dumps(obj, indent=2))
    print(f"  → {path}")


def main():
    extractor = load_skillner()

    # ── Jobs ──────────────────────────────────────────────────────────────────
    # job _corpus.json is a flat list
    job_data = json.loads(JOB_CORPUS.read_text())
    # wrap in a dict so process_corpus handles it
    JOB_CORPUS_TMP = PROCESSED / "_job_corpus_tmp.json"
    JOB_CORPUS_TMP.write_text(json.dumps(job_data))

    job_results, job_freq = process_corpus(extractor, JOB_CORPUS_TMP, "jobs")
    save(job_results, PROCESSED / "skills_jobs.json")
    save(dict(job_freq.most_common(500)), PROCESSED / "skill_freq_jobs.json")
    JOB_CORPUS_TMP.unlink()

    # ── Courses ───────────────────────────────────────────────────────────────
    course_results, course_freq = process_corpus(extractor, COURSE_CORPUS, "courses")
    save(course_results, PROCESSED / "skills_courses.json")
    save(dict(course_freq.most_common(500)), PROCESSED / "skill_freq_courses.json")

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("Phase 1 SkillNER complete.")
    print(f"  Job skills extracted  : {len(job_freq)} unique")
    print(f"  Course skills extracted: {len(course_freq)} unique")
    print("\nTop 20 job skills:")
    for skill, count in job_freq.most_common(20):
        print(f"  {count:4d}  {skill}")
    print("\nTop 20 course skills:")
    for skill, count in course_freq.most_common(20):
        print(f"  {count:4d}  {skill}")
    print("\nNext: python pipeline/nlp/phase1_lda.py")


if __name__ == "__main__":
    main()