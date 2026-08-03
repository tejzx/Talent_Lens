"""Agent 3 — Scoring Agent.

Deterministic, auditable scoring: weighted skill coverage plus embedding-based
semantic similarity. The LLM is used only to explain the numbers, never to set them.

Weights: skills 40, experience 20, projects 15, education 10,
certifications 5, soft skills 5, semantic similarity 5.
"""
from __future__ import annotations

import logging

from embeddings.embedding import cosine, embed_texts
from utils.llm import LLMUnavailable, generate_json, is_configured
from utils.prompts import SCORING_AGENT_PROMPT

log = logging.getLogger(__name__)

WEIGHTS = {
    "skill_match": 0.40,
    "experience_match": 0.20,
    "project_match": 0.15,
    "education_match": 0.10,
    "certification_match": 0.05,
    "soft_skill_match": 0.05,
    "semantic_similarity": 0.05,
}

DEGREE_RANK = {"phd": 4, "doctor": 4, "master": 3, "mba": 3, "bachelor": 2, "b.tech": 2, "associate": 1}
SEMANTIC_HIT = 0.55  # cosine threshold for counting a skill as semantically present


def score_candidate(resume: dict, jd: dict, resume_text: str = "", jd_text: str = "") -> dict:
    """Return the full score breakdown for one resume against one JD."""
    resume_blob = _resume_blob(resume, resume_text).lower()
    resume_skills = [s.lower() for s in resume.get("skills", [])]

    matched, missing, skill_match = _skill_score(jd, resume_skills, resume_blob)
    experience_match = _experience_score(resume, jd)
    project_match = _project_score(resume, jd)
    education_match = _education_score(resume, jd)
    certification_match = _certification_score(resume, jd)
    soft_skill_match = _list_coverage(jd.get("soft_skills", []), resume_blob)
    keyword_match = _list_coverage(jd.get("keywords", []), resume_blob)
    semantic = _semantic_similarity(resume_blob, jd_text or _jd_blob(jd))

    parts = {
        "skill_match": skill_match,
        "experience_match": experience_match,
        "project_match": project_match,
        "education_match": education_match,
        "certification_match": certification_match,
        "soft_skill_match": soft_skill_match,
        "semantic_similarity": semantic,
    }
    overall = round(sum(parts[k] * w for k, w in WEIGHTS.items()), 1)

    scores = {
        **{k: round(v, 1) for k, v in parts.items()},
        "keyword_match": round(keyword_match, 1),
        "overall_score": overall,
        "matched_skills": matched,
        "missing_skills": missing,
        "confidence": _confidence(resume),
        "strengths": [],
        "weaknesses": [],
        "evidence": [],
    }
    return _explain(scores, resume, jd)


# --------------------------------------------------------------------------- #
# Sub-scores
# --------------------------------------------------------------------------- #
def _skill_score(jd: dict, resume_skills: list[str], blob: str) -> tuple[list[str], list[str], float]:
    weighted = jd.get("weighted_skills") or [
        {"skill": s, "weight": 8, "category": "required"} for s in jd.get("required_skills", [])
    ]
    weighted = [w for w in weighted if w.get("category") != "soft"]
    if not weighted:
        return [], [], 0.0

    jd_skills = [w["skill"] for w in weighted]
    sem = _skill_similarity(jd_skills, resume_skills)

    matched, missing, earned, total = [], [], 0.0, 0.0
    for item in weighted:
        skill, weight = item["skill"], float(item.get("weight", 5))
        total += weight
        if skill in resume_skills or skill in blob:
            matched.append(skill)
            earned += weight
        elif sem.get(skill, 0.0) >= SEMANTIC_HIT:
            matched.append(skill)
            earned += weight * 0.7  # partial credit for a semantically adjacent skill
        else:
            missing.append(skill)
    return matched, missing, 100 * earned / total if total else 0.0


def _skill_similarity(jd_skills: list[str], resume_skills: list[str]) -> dict[str, float]:
    if not jd_skills or not resume_skills:
        return {}
    try:
        jd_vecs = embed_texts(jd_skills)
        cv_vecs = embed_texts(resume_skills)
    except Exception as exc:  # pragma: no cover
        log.warning("Embedding skill match failed: %s", exc)
        return {}
    return {
        skill: max(cosine(jd_vecs[i], cv_vecs[j]) for j in range(len(resume_skills)))
        for i, skill in enumerate(jd_skills)
    }


def _experience_score(resume: dict, jd: dict) -> float:
    required = float(jd.get("min_years_experience") or 0)
    actual = float(resume.get("years_experience") or 0)
    if required <= 0:
        return min(100.0, 40 + actual * 12)
    ratio = actual / required
    if ratio >= 1:
        return min(100.0, 90 + min(10.0, (ratio - 1) * 20))
    return max(0.0, round(ratio * 85, 1))


def _project_score(resume: dict, jd: dict) -> float:
    projects = resume.get("projects") or []
    if not projects:
        return 0.0
    text = " ".join(
        f"{p.get('name','')} {p.get('description','')} {' '.join(p.get('tech') or [])}"
        for p in projects
        if isinstance(p, dict)
    ).lower()
    relevance = _list_coverage(jd.get("priority_skills") or jd.get("required_skills", []), text)
    volume = min(100.0, len(projects) * 25.0)
    return round(0.7 * relevance + 0.3 * volume, 1)


def _education_score(resume: dict, jd: dict) -> float:
    education = resume.get("education") or []
    if not education:
        return 0.0
    have = max(
        (_degree_rank(str(e.get("degree", "")) + " " + str(e.get("field", ""))) for e in education),
        default=0,
    )
    need = _degree_rank(str(jd.get("education", "")))
    if need == 0:
        return 70.0 if have else 40.0
    if have >= need:
        return 100.0
    return round(max(20.0, 100 * have / need), 1)


def _degree_rank(text: str) -> int:
    lowered = text.lower()
    return max((rank for key, rank in DEGREE_RANK.items() if key in lowered), default=0)


def _certification_score(resume: dict, jd: dict) -> float:
    certs = [c.lower() for c in resume.get("certifications") or []]
    if not certs:
        return 0.0
    blob = " ".join(certs)
    relevant = sum(1 for s in jd.get("required_skills", []) if s in blob)
    return min(100.0, 50 + relevant * 25 + min(25, len(certs) * 5))


def _list_coverage(items: list[str], blob: str) -> float:
    items = [i.lower() for i in items or []]
    if not items:
        return 0.0
    hits = sum(1 for i in items if i in blob)
    return round(100 * hits / len(items), 1)


def _semantic_similarity(resume_blob: str, jd_blob: str) -> float:
    if not resume_blob or not jd_blob:
        return 0.0
    try:
        vecs = embed_texts([resume_blob[:8000], jd_blob[:8000]])
    except Exception as exc:  # pragma: no cover
        log.warning("Semantic similarity failed: %s", exc)
        return 0.0
    return round(max(0.0, cosine(vecs[0], vecs[1])) * 100, 1)


def _confidence(resume: dict) -> float:
    """How trustworthy the extraction was (completeness of key fields)."""
    checks = [
        resume.get("name") not in (None, "", "Unknown"),
        resume.get("email") not in (None, "", "Unknown"),
        bool(resume.get("skills")),
        bool(resume.get("experience")),
        bool(resume.get("education")),
        float(resume.get("years_experience") or 0) > 0,
        resume.get("extraction_mode") == "llm",
    ]
    return round(100 * sum(checks) / len(checks), 1)


def _resume_blob(resume: dict, raw_text: str) -> str:
    if raw_text:
        return raw_text
    parts = [str(resume.get("summary", "")), " ".join(resume.get("skills", []))]
    for role in resume.get("experience", []):
        if isinstance(role, dict):
            parts.append(f"{role.get('title','')} {role.get('company','')} {' '.join(role.get('highlights') or [])}")
    for proj in resume.get("projects", []):
        if isinstance(proj, dict):
            parts.append(f"{proj.get('name','')} {proj.get('description','')}")
    return " ".join(parts)


def _jd_blob(jd: dict) -> str:
    return " ".join(
        [
            str(jd.get("job_title", "")),
            " ".join(jd.get("required_skills", [])),
            " ".join(jd.get("preferred_skills", [])),
            " ".join(jd.get("responsibilities", [])),
        ]
    )


def _explain(scores: dict, resume: dict, jd: dict) -> dict:
    if not is_configured():
        return _fallback_explanation(scores)
    payload = {
        "job": {k: jd.get(k) for k in ("job_title", "required_skills", "priority_skills", "min_years_experience")},
        "candidate": {k: resume.get(k) for k in ("name", "skills", "years_experience", "education", "projects", "certifications")},
        "computed_scores": {k: v for k, v in scores.items() if isinstance(v, (int, float))},
        "matched_skills": scores["matched_skills"],
        "missing_skills": scores["missing_skills"],
    }
    try:
        result = generate_json(SCORING_AGENT_PROMPT, str(payload))
    except (LLMUnavailable, ValueError) as exc:
        log.warning("Scoring explanation failed: %s", exc)
        return _fallback_explanation(scores)

    scores["strengths"] = [str(s) for s in result.get("strengths", [])][:5]
    scores["weaknesses"] = [str(s) for s in result.get("weaknesses", [])][:5]
    scores["evidence"] = [str(s) for s in result.get("evidence", [])][:5]
    try:
        llm_conf = float(result.get("confidence") or 0)
        if 0 < llm_conf <= 1:
            llm_conf *= 100
        if llm_conf:
            scores["confidence"] = round((scores["confidence"] + llm_conf) / 2, 1)
    except (TypeError, ValueError):
        pass
    return scores


def _fallback_explanation(scores: dict) -> dict:
    matched = scores["matched_skills"]
    missing = scores["missing_skills"]
    scores["strengths"] = [f"Matches required skill: {s}" for s in matched[:5]] or ["Unknown"]
    scores["weaknesses"] = [f"No evidence of required skill: {s}" for s in missing[:5]] or ["Unknown"]
    scores["evidence"] = ["Deterministic scoring only — LLM reviewer unavailable."]
    return scores
