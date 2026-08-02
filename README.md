# AI Resume Screening Agent

A production-shaped, **multi-agent** resume screening system. Upload one job
description plus a batch of resumes, click **Analyze**, and get a ranked recruiter
dashboard with per-candidate reasoning, interview questions, and CSV/JSON/Markdown/PDF exports.

This is deliberately **not** a ChatGPT wrapper: scoring is deterministic and auditable
(weighted skill coverage + MiniLM embeddings + FAISS cosine similarity). The LLM is used
for structured extraction and recruiter-facing reasoning — never to invent the score.

---

## Architecture

```
Job Description ──► Agent 2: JD Intelligence ──► weighted requirement profile
                                                     │
Resumes ──► parser (PyMuPDF / python-docx / OCR) ──► Agent 1: Resume Extraction
                                                     │
                                                     ▼
                            Agent 3: Scoring (MiniLM embeddings + FAISS + rules)
                                                     │
                                                     ▼
                            Agent 4: Recruiter Decision (Hire / Maybe / Reject)
                                                     │
                                       Ranking ──► Dashboard ──► Exports ──► SQLite
```

| Agent | File | Responsibility |
| --- | --- | --- |
| 1. Resume Extraction | `agents/resume_agent.py` | Normalized candidate JSON (contact, skills, experience, education, projects, certs, languages, years) |
| 2. JD Intelligence | `agents/jd_agent.py` | Required/preferred/soft skills, responsibilities, keywords, **weighted requirements (1-10)** |
| 3. Scoring | `agents/scoring_agent.py` | 8 sub-scores + overall score, matched/missing skills, confidence |
| 4. Recruiter Decision | `agents/recruiter_agent.py` | Decision, reasoning, strengths, concerns, 5 interview questions, salary, panel, risk |

Orchestration lives in `agents/pipeline.py`.

### Scoring formula

```
overall = 0.40 * skills        + 0.20 * experience + 0.15 * projects
        + 0.10 * education     + 0.05 * certifications
        + 0.05 * soft_skills   + 0.05 * semantic_similarity
```

- **Skills** — weight-aware coverage of the JD's weighted requirements. Exact match earns
  full weight; a semantically adjacent skill (cosine >= 0.55 on MiniLM embeddings) earns 70%.
- **Semantic similarity** — cosine similarity between full resume and full JD embeddings.
- **Decision rules** — `Hire` >= 75 with no missing priority skill, `Maybe` 55-74, `Reject` < 55.

### Resilience

Every agent has a deterministic fallback. With no `GROQ_API_KEY`, no `sentence-transformers`
download, or no `faiss` install, the pipeline still runs end to end (regex extraction, keyword
JD analysis, hashing embeddings, NumPy inner-product search) and labels the degraded mode in the UI.

---

## Setup

```bash
cd resume-agent
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
export GROQ_API_KEY="your-key"        # optional but recommended
export GROQ_MODEL="llama-3.3-70b-versatile"  # optional override
cd frontend && npm install && npm run build && cd ..
uvicorn server:app --host 127.0.0.1 --port 8501
```

Open `http://127.0.0.1:8501` to use the React dashboard. For frontend development,
run `uvicorn server:app --reload` in one terminal and `npm run dev` from `frontend/`
in another; Vite proxies API requests to the Python backend.

## Deploy

The repository includes a production `Dockerfile`, `Procfile`, and `render.yaml`.
Set `GROQ_API_KEY` as a private environment variable in your deployment provider,
then deploy from the repository root. The Docker image builds the React frontend and
serves it from the FastAPI application. Use `/api/health` as the health-check path.

Optional OCR for scanned PDFs requires system binaries:

```bash
# macOS
brew install tesseract poppler
# Debian/Ubuntu
sudo apt-get install tesseract-ocr poppler-utils
```

Sanity check without the UI:

```bash
python smoke_test.py
```

---

## Tech stack

Streamlit · Python · Groq (`llama-3.3-70b-versatile`) · sentence-transformers `all-MiniLM-L6-v2` · FAISS ·
PyMuPDF · python-docx · pytesseract + pdf2image · SQLite · pandas · NumPy · scikit-learn ·
Plotly · ReportLab.

---

## Dashboard

- **Cards** — total candidates, average score, top candidate, hiring rate.
- **Candidates tab** — filter by score, status, and skill search; interactive table; per-candidate
  detail with radar chart, recruiter brief, parsed text, and JSON/MD/PDF downloads.
- **Analytics tab** — score distribution, candidate ranking, top skills, missing skills, dimension coverage.
- **Compare tab** — multi-candidate radar overlay, side-by-side matrix, shortlisted vs rejected.
- **Job profile tab** — weighted requirement chart and raw JD JSON.
- **Exports tab** — CSV, JSON, Markdown report, PDF report, recruiter summary.

Bonus features: interview questions, recruiter notes, candidate comparison, PDF report,
radar chart, shortlist email generator, skill search, score filter.

---

## Folder structure

```
resume-agent/
  app.py                    Streamlit UI
  smoke_test.py             end-to-end pipeline check
  agents/
    resume_agent.py         Agent 1
    jd_agent.py             Agent 2
    scoring_agent.py        Agent 3
    recruiter_agent.py      Agent 4
    pipeline.py             orchestration
  parser/
    pdf_parser.py  docx_parser.py  ocr.py
  embeddings/
    embedding.py  faiss_store.py
  utils/
    prompts.py  llm.py  ranking.py  database.py  report.py
  data/
    sample_jd/  sample_resumes/  screening.db
  output/
  requirements.txt
```

---

## Design notes

- **Prompts** (`utils/prompts.py`) enforce internal chain-of-thought, strict JSON schemas,
  and an explicit "return Unknown, never guess" rule. Protected attributes are never inferred.
- **Auditability** — the LLM sees the computed scores and explains them; it cannot change them.
- **Persistence** — every run is written to SQLite and reloadable from the sidebar.
