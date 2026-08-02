"""Multi-agent orchestration pipeline: parse -> extract -> analyze -> score -> decide."""
from __future__ import annotations

import logging
from typing import Callable, Iterable

from agents.jd_agent import analyze_jd
from agents.recruiter_agent import recruiter_brief
from agents.resume_agent import extract_resume
from agents.scoring_agent import score_candidate
from embeddings.faiss_store import FaissStore
from parser import extract_text
from utils.ranking import rank_candidates

log = logging.getLogger(__name__)

ProgressFn = Callable[[float, str], None]


def run_pipeline(
    jd_text: str,
    files: Iterable[tuple[str, bytes]],
    progress: ProgressFn | None = None,
) -> dict:
    """Run the full 4-agent screening pipeline.

    Args:
        jd_text: raw job description text.
        files: iterable of (filename, file_bytes).
        progress: optional callback(fraction 0-1, message).

    Returns:
        {"jd": profile, "results": ranked results, "store": FaissStore, "errors": [...]}
    """
    files = list(files)
    errors: list[str] = []
    step = 0.0

    def emit(fraction: float, message: str) -> None:
        if progress:
            progress(min(1.0, max(0.0, fraction)), message)

    emit(0.05, "Agent 2 — analyzing job description")
    jd_profile = analyze_jd(jd_text)

    store = FaissStore()
    results: list[dict] = []
    total = max(1, len(files))

    for i, (filename, data) in enumerate(files):
        base = 0.1 + 0.85 * (i / total)
        emit(base, f"Agent 1 — parsing {filename}")
        try:
            text = extract_text(filename, data)
        except Exception as exc:
            log.exception("Parse failed for %s", filename)
            errors.append(f"{filename}: could not be parsed ({exc})")
            continue
        if not text.strip():
            errors.append(f"{filename}: no extractable text (scanned file without OCR support?)")
            continue

        resume = extract_resume(text, filename)
        emit(base + 0.3 / total, f"Agent 3 — scoring {resume.get('name') or filename}")
        scores = score_candidate(resume, jd_profile, resume_text=text, jd_text=jd_text)
        emit(base + 0.6 / total, f"Agent 4 — recruiter brief for {resume.get('name') or filename}")
        decision, brief = recruiter_brief(resume, jd_profile, scores)

        store.add([filename], [text], [{"name": resume.get("name")}])
        results.append(
            {
                "filename": filename,
                "resume": resume,
                "scores": scores,
                "decision": decision,
                "brief": brief,
                "resume_text": text,
            }
        )

    emit(0.97, "Ranking candidates")
    ranked = rank_candidates(results)
    emit(1.0, "Done")
    return {"jd": jd_profile, "results": ranked, "store": store, "errors": errors}
