"""Agent 1 — Resume Extraction Agent.

LLM-first structured extraction with a deterministic regex fallback so the
pipeline still produces usable data when the model is unavailable.
"""
from __future__ import annotations

import logging
import re

from utils.llm import LLMUnavailable, generate_json, is_configured
from utils.prompts import RESUME_AGENT_PROMPT

log = logging.getLogger(__name__)

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE_RE = re.compile(r"(?:\+?\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}")
GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[\w.-]+", re.I)
LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[\w.-]+", re.I)
YEARS_RE = re.compile(r"(\d{1,2}(?:\.\d)?)\+?\s*(?:years?|yrs?)", re.I)

SKILL_VOCAB = [
    "python", "java", "javascript", "typescript", "c++", "c#", "go", "rust", "r", "scala",
    "sql", "nosql", "postgresql", "mysql", "mongodb", "redis", "snowflake", "databricks",
    "azure", "aws", "gcp", "docker", "kubernetes", "terraform", "airflow", "spark", "hadoop",
    "pandas", "numpy", "scikit-learn", "pytorch", "tensorflow", "keras", "hugging face",
    "llm", "nlp", "computer vision", "rag", "langchain", "mlops", "machine learning",
    "deep learning", "data analysis", "statistics", "power bi", "tableau", "excel",
    "fastapi", "flask", "django", "react", "node.js", "streamlit", "git", "ci/cd", "rest api",
    "communication", "leadership", "teamwork", "problem solving", "stakeholder management",
]

EMPTY = {
    "name": "Unknown", "email": "Unknown", "phone": "Unknown", "location": "Unknown",
    "github": "Unknown", "linkedin": "Unknown", "summary": "Unknown", "skills": [],
    "experience": [], "education": [], "projects": [], "certifications": [],
    "languages": [], "years_experience": 0.0, "experience_confidence": "low",
}

SECTION_HEADS = {
    "skills": ("skills", "technical skills", "core competencies"),
    "education": ("education", "academic"),
    "projects": ("projects", "personal projects", "key projects"),
    "certifications": ("certifications", "certificates", "licenses"),
    "languages": ("languages",),
}


def extract_resume(text: str, filename: str = "Unknown") -> dict:
    """Return normalized candidate JSON for one resume."""
    text = (text or "").strip()
    if not text:
        return {**EMPTY, "source_file": filename, "extraction_mode": "empty"}

    if is_configured():
        try:
            data = generate_json(
                RESUME_AGENT_PROMPT,
                f"Resume file: {filename}\n\n--- RESUME TEXT ---\n{text[:24000]}",
            )
            merged = _merge(_normalize(data), _heuristic(text, filename))
            merged["extraction_mode"] = "llm"
            return merged
        except (LLMUnavailable, ValueError) as exc:
            log.warning("Resume agent LLM path failed for %s: %s", filename, exc)

    fallback = _heuristic(text, filename)
    fallback["extraction_mode"] = "heuristic"
    return fallback


def _normalize(data: dict) -> dict:
    out = {**EMPTY, **{k: v for k, v in (data or {}).items() if v not in (None, "")}}
    out["skills"] = sorted({str(s).strip().lower() for s in out.get("skills") or [] if str(s).strip()})
    for key in ("certifications", "languages"):
        out[key] = [str(v).strip() for v in out.get(key) or [] if str(v).strip()]
    for key in ("experience", "education", "projects"):
        out[key] = [v for v in out.get(key) or [] if isinstance(v, dict)]
    try:
        out["years_experience"] = round(float(out.get("years_experience") or 0), 1)
    except (TypeError, ValueError):
        out["years_experience"] = 0.0
    return out


def _merge(primary: dict, fallback: dict) -> dict:
    """Backfill contact fields the LLM missed using regex ground truth."""
    out = dict(primary)
    for key in ("email", "phone", "github", "linkedin"):
        if out.get(key) in (None, "", "Unknown") and fallback.get(key) != "Unknown":
            out[key] = fallback[key]
    if not out.get("skills"):
        out["skills"] = fallback["skills"]
    if not out.get("years_experience"):
        out["years_experience"] = fallback["years_experience"]
    out["source_file"] = fallback.get("source_file", "Unknown")
    return out


def _heuristic(text: str, filename: str) -> dict:
    lower = text.lower()
    data = dict(EMPTY)
    data["source_file"] = filename
    data["email"] = _first(EMAIL_RE, text)
    data["phone"] = _first(PHONE_RE, text)
    data["github"] = _first(GITHUB_RE, text)
    data["linkedin"] = _first(LINKEDIN_RE, text)
    data["name"] = _guess_name(text, filename)
    data["skills"] = sorted({s for s in SKILL_VOCAB if s in lower})
    data["summary"] = " ".join(text.split()[:60]) or "Unknown"

    years = [float(m) for m in YEARS_RE.findall(text)]
    if years:
        data["years_experience"] = round(max(years), 1)
        data["experience_confidence"] = "medium"
    else:
        spans = re.findall(r"(19|20)\d{2}", text)
        if len(spans) >= 2:
            nums = sorted(int(y) for y in re.findall(r"(?:19|20)\d{2}", text))
            data["years_experience"] = float(max(0, min(45, nums[-1] - nums[0])))

    for key, heads in SECTION_HEADS.items():
        section = _section(text, heads)
        if not section:
            continue
        items = [ln.strip("-•* \t") for ln in section.splitlines() if len(ln.strip()) > 2][:12]
        if key == "certifications":
            data["certifications"] = items
        elif key == "languages":
            data["languages"] = items
        elif key == "projects":
            data["projects"] = [{"name": i[:60], "description": i, "tech": []} for i in items]
        elif key == "education":
            data["education"] = [
                {"degree": i, "institution": "Unknown", "year": "Unknown", "field": "Unknown"} for i in items
            ]
    return data


def _first(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text)
    return match.group(0).strip() if match else "Unknown"


def _guess_name(text: str, filename: str) -> str:
    for line in text.splitlines()[:6]:
        candidate = line.strip()
        if 2 <= len(candidate.split()) <= 4 and not EMAIL_RE.search(candidate):
            if re.fullmatch(r"[A-Za-z.'\- ]{4,60}", candidate):
                return candidate.title()
    stem = re.sub(r"\.[a-z]+$", "", filename).replace("_", " ").replace("-", " ")
    return stem.title() if stem else "Unknown"


def _section(text: str, heads: tuple[str, ...]) -> str:
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.strip().lower().rstrip(":") in heads:
            block: list[str] = []
            for nxt in lines[i + 1 :]:
                stripped = nxt.strip().lower().rstrip(":")
                if any(stripped in group for group in SECTION_HEADS.values()):
                    break
                block.append(nxt)
                if len(block) > 20:
                    break
            return "\n".join(block)
    return ""
