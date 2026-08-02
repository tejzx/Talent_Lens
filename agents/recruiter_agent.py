"""Agent 4 — Recruiter Decision Agent."""
from __future__ import annotations

import logging
import re

from utils.llm import LLMUnavailable, generate, is_configured
from utils.prompts import EMAIL_PROMPT, RECRUITER_AGENT_PROMPT

log = logging.getLogger(__name__)

HIRE_THRESHOLD = 75.0
MAYBE_THRESHOLD = 55.0


def rule_based_decision(scores: dict, jd: dict) -> str:
    overall = scores.get("overall_score", 0)
    priority = set(jd.get("priority_skills") or [])
    missing_priority = priority.intersection(scores.get("missing_skills", []))
    if overall >= HIRE_THRESHOLD:
        return "Maybe" if missing_priority else "Hire"
    if overall >= MAYBE_THRESHOLD:
        return "Maybe"
    return "Reject"


def recruiter_brief(resume: dict, jd: dict, scores: dict) -> tuple[str, str]:
    """Return (decision, markdown brief)."""
    decision = rule_based_decision(scores, jd)
    if not is_configured():
        return decision, _fallback_brief(resume, jd, scores, decision)

    payload = f"""JOB PROFILE
title: {jd.get('job_title')}
industry: {jd.get('industry')}
seniority: {jd.get('seniority')}
required_skills: {jd.get('required_skills')}
priority_skills: {jd.get('priority_skills')}
min_years_experience: {jd.get('min_years_experience')}

CANDIDATE
name: {resume.get('name')}
years_experience: {resume.get('years_experience')}
skills: {resume.get('skills')}
education: {resume.get('education')}
projects: {resume.get('projects')}
certifications: {resume.get('certifications')}

SCORES
overall: {scores.get('overall_score')}
skills: {scores.get('skill_match')} | experience: {scores.get('experience_match')} | projects: {scores.get('project_match')} | education: {scores.get('education_match')} | certifications: {scores.get('certification_match')} | soft_skills: {scores.get('soft_skill_match')} | semantic: {scores.get('semantic_similarity')}
matched_skills: {scores.get('matched_skills')}
missing_skills: {scores.get('missing_skills')}
rule_based_decision: {decision}

Honor the rule-based decision above in the ### Decision section."""

    try:
        brief = generate(RECRUITER_AGENT_PROMPT, payload, temperature=0.3)
    except LLMUnavailable as exc:
        log.warning("Recruiter agent failed: %s", exc)
        return decision, _fallback_brief(resume, jd, scores, decision)

    match = re.search(r"###\s*Decision\s*\n+\**\s*(Hire|Maybe|Reject)", brief, re.I)
    if match:
        decision = match.group(1).title()
    return decision, brief.strip()


def shortlist_email(resume: dict, jd: dict) -> str:
    if not is_configured():
        name = resume.get("name") or "there"
        return (
            f"Subject: Interview invitation — {jd.get('job_title', 'the role')}\n\n"
            f"Hi {name},\n\nThank you for applying for the {jd.get('job_title', 'open')} role. "
            "Your background stood out during our review and we would like to schedule an interview.\n\n"
            "Please share your availability for [dates].\n\nBest regards,\n[Recruiter name]"
        )
    try:
        return generate(
            EMAIL_PROMPT,
            f"Candidate: {resume.get('name')}\nRole: {jd.get('job_title')}\n"
            f"Standout skills: {resume.get('skills', [])[:8]}",
            temperature=0.5,
        )
    except LLMUnavailable:
        return "Unknown"


def _fallback_brief(resume: dict, jd: dict, scores: dict, decision: str) -> str:
    strengths = scores.get("strengths") or ["Unknown"]
    weaknesses = scores.get("weaknesses") or ["Unknown"]
    missing = scores.get("missing_skills") or []
    questions = [
        f"Walk me through a project where you used {s}."
        for s in (scores.get("matched_skills") or ["your strongest skill"])[:2]
    ] + [
        f"You have limited visible experience with {s} — how would you ramp up?" for s in missing[:2]
    ]
    questions.append("Describe a time you had to deliver under an unclear specification.")
    return "\n".join(
        [
            "### Decision",
            decision,
            "",
            "### Reasoning",
            f"Overall score {scores.get('overall_score')} / 100 against {jd.get('job_title', 'the role')}, "
            f"driven by {scores.get('skill_match')} skill coverage and "
            f"{scores.get('experience_match')} experience fit.",
            "",
            "### Top Strengths",
            *[f"- {s}" for s in strengths[:5]],
            "",
            "### Concerns",
            *[f"- {w}" for w in weaknesses[:5]],
            "",
            "### Interview Questions",
            *[f"{i}. {q}" for i, q in enumerate(questions[:5], 1)],
            "",
            "### Salary Recommendation",
            "Unknown",
            "",
            "### Suggested Department",
            jd.get("industry") or "Unknown",
            "",
            "### Suggested Interview Panel",
            "- Hiring manager\n- Senior engineer on the team\n- Recruiter (culture screen)",
            "",
            "### Risk Analysis",
            f"- Skill gap risk: {'high' if len(missing) > 3 else 'moderate' if missing else 'low'}"
            f" ({len(missing)} required skills unverified)",
            f"- Extraction confidence: {scores.get('confidence')} — verify details in the source resume.",
        ]
    )
