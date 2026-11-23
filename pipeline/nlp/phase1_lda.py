"""
phase1_lda.py
─────────────
Phase 1: LDA k=17 replication of Mohammed et al.

Steps:
  1. Load skill lists from phase1_skillner output
  2. Build document-term matrix (skills as tokens)
  3. Train LDA with k=17 (Mohammed's exact setting)
  4. Compute gap table: job skills not covered by courses
  5. Save results + gap table

Output:
  data/processed/lda_model/          (saved gensim model)
  data/processed/lda_topics.json     (top terms per topic)
  data/processed/gap_table.json      (skill gap analysis)
  data/processed/gap_table.csv       (for paper table)

Install deps:
  pip install gensim pyLDAvis --break-system-packages
"""

import json
import csv
import pathlib
import sys
from collections import Counter, defaultdict

import numpy as np

PROCESSED = pathlib.Path("data/processed")
LDA_DIR   = PROCESSED / "lda_model"
LDA_DIR.mkdir(parents=True, exist_ok=True)

# Mohammed et al. parameters
K_TOPICS       = 17
LDA_PASSES     = 20
LDA_ITERATIONS = 400
RANDOM_STATE   = 42
MIN_SKILL_FREQ = 2   # ignore skills appearing < 2 times (noise reduction)
TOP_N_SKILLS   = 15  # top skills per topic to display


class NumpyEncoder(json.JSONEncoder):
    """JSON encoder that handles numpy scalar types returned by gensim."""
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def load_deps():
    try:
        import gensim
        from gensim import corpora, models
        return corpora, models
    except ImportError:
        print("[ERROR] gensim not installed. Run:")
        print("  pip install gensim --break-system-packages")
        sys.exit(1)


def load_skill_lists(path: pathlib.Path) -> list[list[str]]:
    """Load list of per-document skill lists."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [doc["skills"] for doc in data if doc.get("skills")]


def compute_gap(job_freq: Counter, course_freq: Counter,
                job_docs: list[list[str]], course_docs: list[list[str]],
                top_n: int = 50) -> list[dict]:
    """
    Mohammed gap metric:
      gap_score = job_prevalence - course_coverage
      job_prevalence  = % of job docs mentioning the skill
      course_coverage = % of course docs mentioning the skill
    """
    n_jobs    = len(job_docs)
    n_courses = len(course_docs)

    # doc-level sets for prevalence calculation
    job_skill_sets    = [set(doc) for doc in job_docs]
    course_skill_sets = [set(doc) for doc in course_docs]

    # all skills that appear in jobs
    job_skills = set(job_freq.keys())

    gap_rows = []
    for skill in job_skills:
        job_prev    = sum(1 for s in job_skill_sets    if skill in s) / n_jobs    if n_jobs    else 0
        course_cov  = sum(1 for s in course_skill_sets if skill in s) / n_courses if n_courses else 0
        gap_score   = job_prev - course_cov

        gap_rows.append({
            "skill":           skill,
            "job_count":       int(job_freq[skill]),
            "job_prevalence":  round(float(job_prev),   4),
            "course_coverage": round(float(course_cov), 4),
            "gap_score":       round(float(gap_score),  4),
            "in_courses":      skill in course_freq,
        })

    # sort by gap_score descending
    gap_rows.sort(key=lambda x: x["gap_score"], reverse=True)
    return gap_rows[:top_n]


def main():
    corpora_mod, models_mod = load_deps()

    # ── Load skills ───────────────────────────────────────────────────────────
    print("Loading skill lists...")
    job_skills_path    = PROCESSED / "skills_jobs.json"
    course_skills_path = PROCESSED / "skills_courses.json"

    if not job_skills_path.exists() or not course_skills_path.exists():
        print("[ERROR] Run phase1_skillner.py first.")
        sys.exit(1)

    job_docs    = load_skill_lists(job_skills_path)
    course_docs = load_skill_lists(course_skills_path)

    print(f"  Job docs with skills   : {len(job_docs)}")
    print(f"  Course docs with skills: {len(course_docs)}")

    # ── Frequency counts ──────────────────────────────────────────────────────
    job_freq    = Counter(s for doc in job_docs    for s in doc)
    course_freq = Counter(s for doc in course_docs for s in doc)

    # filter low-freq skills
    job_freq    = Counter({k: v for k, v in job_freq.items()    if v >= MIN_SKILL_FREQ})
    course_freq = Counter({k: v for k, v in course_freq.items() if v >= MIN_SKILL_FREQ})

    # filter doc skill lists to vocabulary
    job_vocab    = set(job_freq.keys())
    course_vocab = set(course_freq.keys())
    job_docs_f    = [[s for s in doc if s in job_vocab]    for doc in job_docs]
    course_docs_f = [[s for s in doc if s in course_vocab] for doc in course_docs]
    job_docs_f    = [d for d in job_docs_f    if d]
    course_docs_f = [d for d in course_docs_f if d]

    print(f"  Job unique skills (freq≥{MIN_SKILL_FREQ}): {len(job_vocab)}")

    # ── LDA on job skills (Mohammed approach) ─────────────────────────────────
    print(f"\nTraining LDA k={K_TOPICS} on job skills...")
    dictionary = corpora_mod.Dictionary(job_docs_f)
    corpus_bow = [dictionary.doc2bow(doc) for doc in job_docs_f]

    lda_model = models_mod.LdaModel(
        corpus          = corpus_bow,
        id2word         = dictionary,
        num_topics      = K_TOPICS,
        passes          = LDA_PASSES,
        iterations      = LDA_ITERATIONS,
        random_state    = RANDOM_STATE,
        alpha           = "auto",
        eta             = "auto",
    )

    # save model
    lda_model.save(str(LDA_DIR / "lda_k17.model"))
    print(f"  Model saved → {LDA_DIR}/lda_k17.model")

    # ── Extract topics ────────────────────────────────────────────────────────
    topics = []
    print(f"\nTop {TOP_N_SKILLS} skills per topic:")
    for t in range(K_TOPICS):
        top_terms = lda_model.show_topic(t, topn=TOP_N_SKILLS)
        terms = [{"skill": term, "weight": round(float(weight), 4)} for term, weight in top_terms]
        topics.append({"topic_id": t, "top_terms": terms})
        top_str = ", ".join(term for term, _ in top_terms[:6])
        print(f"  Topic {t:2d}: {top_str}")

    (PROCESSED / "lda_topics.json").write_text(
        json.dumps(topics, indent=2, cls=NumpyEncoder), encoding="utf-8"
    )
    print(f"\n  → {PROCESSED}/lda_topics.json")

    # ── Coherence score ───────────────────────────────────────────────────────
    try:
        from gensim.models.coherencemodel import CoherenceModel
        cm = CoherenceModel(
            model=lda_model, texts=job_docs_f,
            dictionary=dictionary, coherence="c_v"
        )
        coherence = float(cm.get_coherence())
        print(f"\n  LDA coherence (c_v): {coherence:.4f}")
    except Exception as e:
        coherence = None
        print(f"\n  Coherence skipped: {e}")

    # ── Gap table ─────────────────────────────────────────────────────────────
    print("\nComputing skill gap table...")
    gap_table = compute_gap(job_freq, course_freq, job_docs_f, course_docs_f, top_n=50)

    (PROCESSED / "gap_table.json").write_text(
        json.dumps(gap_table, indent=2, cls=NumpyEncoder), encoding="utf-8"
    )

    # CSV for paper
    csv_path = PROCESSED / "gap_table.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "skill", "job_count", "job_prevalence",
            "course_coverage", "gap_score", "in_courses"
        ])
        writer.writeheader()
        writer.writerows(gap_table)

    print(f"  → {PROCESSED}/gap_table.json")
    print(f"  → {csv_path}")

    # ── Print gap table (top 25) ───────────────────────────────────────────────
    print("\n" + "=" * 65)
    print(f"{'Skill':<35} {'Job%':>6} {'Course%':>8} {'Gap':>7}")
    print("-" * 65)
    for row in gap_table[:25]:
        print(
            f"{row['skill']:<35} "
            f"{row['job_prevalence']*100:>5.1f}% "
            f"{row['course_coverage']*100:>7.1f}% "
            f"{row['gap_score']*100:>6.1f}%"
        )

    # ── Summary JSON ──────────────────────────────────────────────────────────
    summary = {
        "lda_params": {
            "k": K_TOPICS,
            "passes": LDA_PASSES,
            "iterations": LDA_ITERATIONS,
            "random_state": RANDOM_STATE,
        },
        "coherence_cv": coherence,
        "n_job_docs": len(job_docs_f),
        "n_course_docs": len(course_docs_f),
        "n_job_skills_vocab": len(job_vocab),
        "n_course_skills_vocab": len(course_vocab),
        "top_gaps": gap_table[:10],
    }
    (PROCESSED / "phase1_summary.json").write_text(
        json.dumps(summary, indent=2, cls=NumpyEncoder), encoding="utf-8"
    )

    print("\n" + "=" * 65)
    print("Phase 1 LDA complete.")
    print("Next: python pipeline/nlp/phase2_synthetic.py")


if __name__ == "__main__":
    main()