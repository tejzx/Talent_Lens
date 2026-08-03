"""Ranking, filtering, and aggregate analytics over scored candidates."""
from __future__ import annotations

from collections import Counter
from typing import Any

import pandas as pd


def rank_candidates(results: list[dict]) -> list[dict]:
    """Sort by overall score, then confidence, then experience. Adds 1-based rank."""
    ordered = sorted(
        results,
        key=lambda r: (
            r["scores"]["overall_score"],
            r["scores"].get("confidence", 0),
            r["resume"].get("years_experience") or 0,
        ),
        reverse=True,
    )
    for i, item in enumerate(ordered, start=1):
        item["rank"] = i
    return ordered


def to_dataframe(results: list[dict]) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for r in results:
        resume, scores = r["resume"], r["scores"]
        rows.append(
            {
                "Rank": r.get("rank"),
                "Candidate": resume.get("name") or "Unknown",
                "File": r.get("filename", "Unknown"),
                "Score": scores["overall_score"],
                "Status": r.get("decision", "Unknown"),
                "Years Experience": resume.get("years_experience") or 0,
                "Email": resume.get("email") or "Unknown",
                "Skill Match": scores["skill_match"],
                "Experience Match": scores["experience_match"],
                "Education Match": scores["education_match"],
                "Project Match": scores["project_match"],
                "Certification Match": scores["certification_match"],
                "Soft Skill Match": scores["soft_skill_match"],
                "Keyword Match": scores["keyword_match"],
                "Semantic Similarity": scores["semantic_similarity"],
                "Confidence": scores.get("confidence", 0),
                "Matched Skills": ", ".join(scores.get("matched_skills", [])),
                "Missing Skills": ", ".join(scores.get("missing_skills", [])),
            }
        )
    return pd.DataFrame(rows)


def summary_stats(results: list[dict]) -> dict:
    if not results:
        return {"total": 0, "average_score": 0.0, "top_candidate": "Unknown", "hiring_rate": 0.0}
    scores = [r["scores"]["overall_score"] for r in results]
    hires = sum(1 for r in results if r.get("decision") == "Hire")
    top = max(results, key=lambda r: r["scores"]["overall_score"])
    return {
        "total": len(results),
        "average_score": round(sum(scores) / len(scores), 1),
        "top_candidate": top["resume"].get("name") or top.get("filename", "Unknown"),
        "top_score": top["scores"]["overall_score"],
        "hiring_rate": round(100 * hires / len(results), 1),
        "shortlisted": sum(1 for r in results if r.get("decision") in ("Hire", "Maybe")),
    }


def skill_frequency(results: list[dict], key: str = "matched_skills", top_n: int = 15) -> list[tuple[str, int]]:
    counter: Counter[str] = Counter()
    for r in results:
        counter.update(r["scores"].get(key, []))
    return counter.most_common(top_n)


def filter_results(
    results: list[dict],
    *,
    min_score: float = 0.0,
    statuses: list[str] | None = None,
    skill_query: str = "",
) -> list[dict]:
    query = (skill_query or "").strip().lower()
    out = []
    for r in results:
        if r["scores"]["overall_score"] < min_score:
            continue
        if statuses and r.get("decision") not in statuses:
            continue
        if query:
            haystack = " ".join(r["resume"].get("skills", []) + r["scores"].get("matched_skills", [])).lower()
            if not all(term in haystack for term in query.split(",") if term.strip()):
                continue
        out.append(r)
    return out
