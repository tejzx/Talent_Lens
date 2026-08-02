"""Agent 2 — Job Description Intelligence Agent."""
from __future__ import annotations

import logging
import re

from agents.resume_agent import SKILL_VOCAB
from utils.llm import LLMUnavailable, generate_json, is_configured
from utils.prompts import JD_AGENT_PROMPT

log = logging.getLogger(__name__)

SOFT_SKILLS = {
    "communication", "leadership", "teamwork", "collaboration", "problem solving",
    "ownership", "adaptability", "stakeholder management", "mentoring", "presentation",
}

EMPTY = {
    "job_title": "Unknown", "industry": "Unknown", "seniority": "Unknown",
    "required_skills": [], "preferred_skills": [], "soft_skills": [], "responsibilities": [],
    "education": "Unknown", "min_years_experience": 0.0, "keywords": [],
    "priority_skills": [], "weighted_skills": [],
}


def analyze_jd(text: str) -> dict:
    text = (text or "").strip()
    if not text:
        return {**EMPTY, "analysis_mode": "empty"}

    if is_configured():
        try:
            data = generate_json(JD_AGENT_PROMPT, f"--- JOB DESCRIPTION ---\n{text[:20000]}")
            profile = _normalize(data)
            profile["analysis_mode"] = "llm"
            return profile
        except (LLMUnavailable, ValueError) as exc:
            log.warning("JD agent LLM path failed: %s", exc)

    profile = _heuristic(text)
    profile["analysis_mode"] = "heuristic"
    return profile


def _normalize(data: dict) -> dict:
    out = {**EMPTY, **{k: v for k, v in (data or {}).items() if v not in (None, "")}}
    for key in ("required_skills", "preferred_skills", "soft_skills", "keywords", "priority_skills"):
        out[key] = sorted({str(s).strip().lower() for s in out.get(key) or [] if str(s).strip()})
    out["responsibilities"] = [str(r).strip() for r in out.get("responsibilities") or [] if str(r).strip()]

    weighted: list[dict] = []
    seen: set[str] = set()
    for item in out.get("weighted_skills") or []:
        if not isinstance(item, dict):
            continue
        skill = str(item.get("skill", "")).strip().lower()
        if not skill or skill in seen:
            continue
        seen.add(skill)
        try:
            weight = int(round(float(item.get("weight", 5))))
        except (TypeError, ValueError):
            weight = 5
        weighted.append({
            "skill": skill,
            "weight": max(1, min(10, weight)),
            "category": item.get("category", "required"),
        })
    if not weighted:
        weighted = _auto_weights(out["required_skills"], out["preferred_skills"], out["soft_skills"])
    out["weighted_skills"] = sorted(weighted, key=lambda w: w["weight"], reverse=True)
    if not out["priority_skills"]:
        out["priority_skills"] = [
            w["skill"] for w in out["weighted_skills"] if w["category"] == "required"
        ][:6]
    try:
        out["min_years_experience"] = float(out.get("min_years_experience") or 0)
    except (TypeError, ValueError):
        out["min_years_experience"] = 0.0
    return out


def _auto_weights(required: list[str], preferred: list[str], soft: list[str]) -> list[dict]:
    weighted = []
    for i, skill in enumerate(required):
        weighted.append({"skill": skill, "weight": max(7, 10 - i), "category": "required"})
    for skill in preferred:
        weighted.append({"skill": skill, "weight": 6, "category": "preferred"})
    for skill in soft:
        weighted.append({"skill": skill, "weight": 4, "category": "soft"})
    return weighted


def _heuristic(text: str) -> dict:
    lower = text.lower()
    out = dict(EMPTY)
    first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "Unknown")
    out["job_title"] = first_line[:80]

    found = [s for s in SKILL_VOCAB if s in lower]
    required, preferred = [], []
    for skill in found:
        window = _window(lower, skill)
        if any(tok in window for tok in ("prefer", "nice to have", "bonus", "plus")):
            preferred.append(skill)
        else:
            required.append(skill)
    out["required_skills"] = sorted(set(required) - SOFT_SKILLS)
    out["preferred_skills"] = sorted(set(preferred) - SOFT_SKILLS)
    out["soft_skills"] = sorted(SOFT_SKILLS.intersection(found))
    out["responsibilities"] = [
        ln.strip("-•* \t") for ln in text.splitlines() if ln.strip().startswith(("-", "•", "*"))
    ][:12]
    match = re.search(r"(\d{1,2})\+?\s*(?:years?|yrs?)", lower)
    out["min_years_experience"] = float(match.group(1)) if match else 0.0
    for degree in ("phd", "master", "bachelor", "b.tech", "m.tech"):
        if degree in lower:
            out["education"] = degree.title()
            break
    out["keywords"] = sorted({w for w in re.findall(r"[a-z][a-z+.#-]{3,}", lower)} & set(SKILL_VOCAB))
    return _normalize(out)


def _window(text: str, term: str, radius: int = 80) -> str:
    idx = text.find(term)
    if idx == -1:
        return ""
    return text[max(0, idx - radius) : idx + radius]
