"""FastAPI backend for the React Talent Lens workspace.

Run locally with ``uvicorn server:app --reload`` after building/starting the
frontend. The React dev server proxies /api calls to this application.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from agents.pipeline import run_pipeline
from agents.recruiter_agent import shortlist_email
from parser import extract_text
from utils import database
from utils.ranking import summary_stats

ROOT = Path(__file__).resolve().parent
FRONTEND_DIST = ROOT / "frontend" / "dist"

app = FastAPI(title="Talent Lens API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/api/runs")
def list_runs() -> list[dict]:
    return database.list_runs(limit=12)


@app.get("/api/runs/{run_id}")
def load_run(run_id: int) -> dict:
    jd, results = database.load_run(run_id)
    if not jd:
        raise HTTPException(status_code=404, detail="Screening run not found")
    return {"jd": jd, "results": results, "errors": [], "summary": summary_stats(results)}


@app.post("/api/analyze")
async def analyze(
    job_description: str = Form(""),
    jd_file: UploadFile | None = None,
    resumes: list[UploadFile] = File(...),
) -> dict:
    """Run the existing screening pipeline for uploaded candidate files."""
    jd_text = job_description.strip()
    if not jd_text and jd_file:
        jd_text = extract_text(jd_file.filename or "job-description.txt", await jd_file.read())
    if not jd_text:
        raise HTTPException(status_code=422, detail="Add a job description before analyzing candidates.")
    if not resumes:
        raise HTTPException(status_code=422, detail="Add at least one candidate resume.")

    files = [(upload.filename or "resume.txt", await upload.read()) for upload in resumes]
    output = run_pipeline(jd_text, files)
    try:
        database.save_run(output["jd"], output["results"])
    except Exception as exc:  # The analysis is still useful without persistence.
        output["errors"].append(f"Run could not be saved: {exc}")
    output.pop("store", None)  # In-memory search index is not part of the API payload.
    return {**output, "summary": summary_stats(output["results"])}


@app.post("/api/interview-email")
def interview_email(payload: dict) -> dict:
    resume, jd = payload.get("resume"), payload.get("jd")
    if not isinstance(resume, dict) or not isinstance(jd, dict):
        raise HTTPException(status_code=422, detail="Candidate and role details are required.")
    return {"email": shortlist_email(resume, jd)}


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def serve_react(path: str):
        file_path = FRONTEND_DIST / path
        if path and file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
