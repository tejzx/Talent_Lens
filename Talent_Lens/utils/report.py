"""Export layer: CSV, JSON, Markdown report, recruiter summary, PDF."""
from __future__ import annotations

import io
import json
from datetime import date

from .ranking import skill_frequency, summary_stats, to_dataframe


def to_csv(results: list[dict]) -> bytes:
    return to_dataframe(results).to_csv(index=False).encode("utf-8")


def to_json(jd_profile: dict, results: list[dict]) -> bytes:
    payload = {
        "generated_on": date.today().isoformat(),
        "job_profile": jd_profile,
        "summary": summary_stats(results),
        "candidates": results,
    }
    return json.dumps(payload, indent=2, default=str).encode("utf-8")


def candidate_markdown(result: dict) -> str:
    resume = result["resume"]
    scores = result["scores"]
    lines = [
        f"## {resume.get('name') or 'Unknown'} — {scores['overall_score']}/100 ({result.get('decision', 'Unknown')})",
        "",
        f"- **File:** {result.get('filename', 'Unknown')}",
        f"- **Email:** {resume.get('email') or 'Unknown'} | **Phone:** {resume.get('phone') or 'Unknown'}",
        f"- **Experience:** {resume.get('years_experience', 0)} years",
        f"- **Matched skills:** {', '.join(scores.get('matched_skills', [])) or 'None'}",
        f"- **Missing skills:** {', '.join(scores.get('missing_skills', [])) or 'None'}",
        "",
        "| Dimension | Score |",
        "| --- | --- |",
    ]
    for label, key in [
        ("Skills", "skill_match"),
        ("Experience", "experience_match"),
        ("Projects", "project_match"),
        ("Education", "education_match"),
        ("Certifications", "certification_match"),
        ("Soft skills", "soft_skill_match"),
        ("Semantic similarity", "semantic_similarity"),
        ("Keywords", "keyword_match"),
    ]:
        lines.append(f"| {label} | {scores.get(key, 0)} |")
    lines += ["", result.get("brief", "_No recruiter brief generated._"), ""]
    return "\n".join(lines)


def full_markdown_report(jd_profile: dict, results: list[dict]) -> str:
    stats = summary_stats(results)
    lines = [
        f"# Screening Report — {jd_profile.get('job_title', 'Unknown role')}",
        f"_Generated {date.today().isoformat()}_",
        "",
        "## Summary",
        f"- Candidates screened: **{stats['total']}**",
        f"- Average score: **{stats['average_score']}**",
        f"- Top candidate: **{stats['top_candidate']}**",
        f"- Hiring rate: **{stats['hiring_rate']}%**",
        "",
        "## Ranking",
        "| Rank | Candidate | Score | Decision | Years |",
        "| --- | --- | --- | --- | --- |",
    ]
    for r in results:
        lines.append(
            f"| {r.get('rank')} | {r['resume'].get('name') or 'Unknown'} | "
            f"{r['scores']['overall_score']} | {r.get('decision', 'Unknown')} | "
            f"{r['resume'].get('years_experience', 0)} |"
        )
    lines += ["", "## Candidate Briefs", ""]
    lines += [candidate_markdown(r) for r in results]
    return "\n".join(lines)


def recruiter_summary(jd_profile: dict, results: list[dict]) -> str:
    stats = summary_stats(results)
    shortlist = [r for r in results if r.get("decision") in ("Hire", "Maybe")]
    gaps = skill_frequency(results, "missing_skills", top_n=8)
    lines = [
        f"# Recruiter Summary — {jd_profile.get('job_title', 'Unknown role')}",
        "",
        f"Screened **{stats['total']}** candidates. Average score **{stats['average_score']}**. "
        f"**{len(shortlist)}** advanced to shortlist.",
        "",
        "## Shortlist",
    ]
    lines += (
        [
            f"{i}. **{r['resume'].get('name') or 'Unknown'}** — {r['scores']['overall_score']}/100 "
            f"({r.get('decision')}) — {r['resume'].get('email') or 'Unknown'}"
            for i, r in enumerate(shortlist, 1)
        ]
        or ["_No candidate met the shortlist bar._"]
    )
    lines += ["", "## Most common skill gaps in this pool"]
    lines += [f"- {skill} — missing in {count} candidates" for skill, count in gaps] or ["- None"]
    return "\n".join(lines)


def to_pdf(markdown_text: str, title: str = "Screening Report") -> bytes:
    """Render a report to PDF. Returns UTF-8 text bytes if reportlab is missing."""
    try:
        from reportlab.lib.pagesizes import LETTER
        from reportlab.lib.styles import getSampleStyleSheet
        from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    except Exception:  # pragma: no cover - optional dependency
        return markdown_text.encode("utf-8")

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=LETTER, title=title)
    styles = getSampleStyleSheet()
    flow = []
    for raw_line in markdown_text.splitlines():
        line = raw_line.rstrip()
        if not line:
            flow.append(Spacer(1, 8))
            continue
        if line.startswith("### "):
            flow.append(Paragraph(_esc(line[4:]), styles["Heading3"]))
        elif line.startswith("## "):
            flow.append(Paragraph(_esc(line[3:]), styles["Heading2"]))
        elif line.startswith("# "):
            flow.append(Paragraph(_esc(line[2:]), styles["Title"]))
        else:
            flow.append(Paragraph(_esc(line.lstrip("-| ").replace("**", "")), styles["BodyText"]))
    doc.build(flow)
    return buffer.getvalue()


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
