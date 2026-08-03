# Talent Lens

**A production-shaped, multi-agent resume screening system with a full recruiting pipeline.**

Upload a job description plus a batch of resumes, click **Analyze**, and get a ranked
shortlist with per-candidate reasoning — automatically tracked through your pipeline
from Applied to Hired, with funnel analytics and one-click exports.

This is deliberately **not** a ChatGPT wrapper. Scoring is deterministic and auditable
(weighted skill coverage + MiniLM embeddings + FAISS cosine similarity). The LLM is used
for structured extraction and recruiter-facing reasoning — it never invents the score.

---

## Demo
Video Link: https://www.loom.com/share/bdb2d55c06844a799ef8a898d0acdde1
Note: Please do ignore the background noise. 
---

## Table of contents

- [Features](#features)
- [Architecture](#architecture)
- [Scoring formula](#scoring-formula)
- [Resilience](#resilience)
- [Quick start](#quick-start)
- [Running the frontend and backend separately](#running-the-frontend-and-backend-separately)
- [Configuration](#configuration)
- [Optional OCR setup](#optional-ocr-setup)
- [Sanity check](#sanity-check)
- [Deploying](#deploying)
- [Product walkthrough](#product-walkthrough)
- [API reference](#api-reference)
- [Folder structure](#folder-structure)
- [Design notes](#design-notes)
- [Troubleshooting](#troubleshooting)

---

## Features

- **Multi-agent screening pipeline** — four specialized agents handle resume
  extraction, JD intelligence, scoring, and recruiter decisioning.
- **Auditable scoring** — every score is a weighted formula over 7 dimensions, not a
  black-box LLM number.
- **Recruiting pipeline board** — candidates flow through Applied → Screening →
  Interview → Offer → Hired (or Rejected), tracked on a Kanban-style board.
- **Funnel analytics** — see how many candidates are progressing, stalled mid-pipeline,
  or rejected, at a glance.
- **Interview email generator** — one click to draft an interview invitation for any
  shortlisted candidate.
- **Exports** — CSV, JSON, Markdown report, recruiter summary, and PDF report.
- **Resilient by design** — runs fully without an LLM key, using deterministic
  fallbacks for every stage.

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
                                       Ranking ──► Pipeline board ──► Exports ──► SQLite
```

| Agent | File | Responsibility |
|---|---|---|
| 1. Resume Extraction | `agents/resume_agent.py` | Normalized candidate JSON — contact, skills, experience, education, projects, certifications, languages, years of experience |
| 2. JD Intelligence | `agents/jd_agent.py` | Required / preferred / soft skills, responsibilities, keywords, weighted requirements (1–10) |
| 3. Scoring | `agents/scoring_agent.py` | 8 sub-scores + overall score, matched/missing skills, confidence |
| 4. Recruiter Decision | `agents/recruiter_agent.py` | Decision, reasoning, strengths, concerns, 5 interview questions, salary band, panel suggestion, risk notes |

Orchestration lives in `agents/pipeline.py`, which runs all four agents in sequence for
every uploaded resume and hands the ranked results to the FastAPI layer.

## Scoring formula

```
overall = 0.40 * skills        + 0.20 * experience + 0.15 * projects
        + 0.10 * education     + 0.05 * certifications
        + 0.05 * soft_skills   + 0.05 * semantic_similarity
```

- **Skills** — weight-aware coverage of the JD's weighted requirements. An exact match
  earns full weight; a semantically adjacent skill (cosine ≥ 0.55 on MiniLM embeddings)
  earns 70% credit.
- **Semantic similarity** — cosine similarity between the full resume embedding and the
  full JD embedding.
- **Decision rules** — `Hire` ≥ 75 with no missing priority skill · `Maybe` 55–74 ·
  `Reject` < 55. Newly screened candidates are placed on the pipeline board
  automatically using the same thresholds (Hire → Interview, Maybe → Screening,
  Reject → Rejected).

## Resilience

Every agent has a deterministic fallback. With no `GROQ_API_KEY`, no
`sentence-transformers` model download, or no `faiss` install, the pipeline still runs
end to end:

| Component | With dependency | Fallback |
|---|---|---|
| Extraction / reasoning | Groq LLM (`llama-3.3-70b-versatile`) | Regex-based extraction |
| JD analysis | LLM structured parsing | Keyword-based JD analysis |
| Embeddings | `sentence-transformers` (MiniLM) | Hashing-based embeddings |
| Similarity search | FAISS | NumPy inner-product search |

Degraded mode is labelled in the results payload (`analysis_mode`) so you always know
which path produced a given result.

---

## Quick start

Requires **Python 3.10+** and **Node.js 18+**.

```bash
git clone https://github.com/tejzx/Talent_Lens.git
cd Talent_Lens

python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate.bat

pip install -r requirements.txt

# optional but recommended — enables LLM-powered extraction and reasoning
export GROQ_API_KEY="your-key"       # Windows: set GROQ_API_KEY=your-key

cd frontend
npm install
npm run build
cd ..

uvicorn server:app --host 127.0.0.1 --port 8000
```

Open **http://127.0.0.1:8000** — this single command serves both the built React
dashboard and the API from one process, the same way it runs in production.

## Running the frontend and backend separately

Useful when you're actively editing the React app and want hot reload.

**Terminal 1 — backend:**
```bash
uvicorn server:app --reload --port 8000
```

**Terminal 2 — frontend:**
```bash
cd frontend
npm install
npm run dev
```

Open **http://localhost:5173**. Vite proxies every `/api/*` request to the backend on
port 8000 (see `frontend/vite.config.js`) — the backend must be running on **8000** for
this to work, since that's also the port used by the Dockerfile in production.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | No | Enables LLM-powered extraction and recruiter reasoning. Without it, the app uses deterministic regex/keyword fallbacks and still works fully. |
| `GROQ_MODEL` | No | Overrides the default model (`llama-3.3-70b-versatile`). |
| `PORT` | No | Used by the Dockerfile/hosted environments; defaults to `8000`. |

## Optional OCR setup

Only needed if you plan to screen **scanned/image-only PDF** resumes. Regular
text-based PDFs, DOCX, and TXT resumes work without this.

```bash
# macOS
brew install tesseract poppler

# Debian/Ubuntu
sudo apt-get install tesseract-ocr poppler-utils

# Windows
# Tesseract: https://github.com/UB-Mannheim/tesseract/wiki (installer adds it to PATH)
# Poppler:   https://github.com/oschwartz10612/poppler-windows/releases
#            (add the extracted bin/ folder to your PATH manually)
```

## Sanity check

Runs the full pipeline against the bundled sample resumes without touching the UI —
useful for confirming your environment is set up correctly:

```bash
python smoke_test.py
```

---

## Deploying

The repository includes a production `Dockerfile` and `render.yaml`. The Docker image
builds the React frontend and serves it from the FastAPI application on a single port,
with `/api/health` as the health-check path.

**Render (recommended, no card required):**
1. Push your repo to GitHub.
2. On [render.com](https://render.com), sign in with GitHub → **New +** → **Web
   Service** → select this repo.
3. Render detects `render.yaml`/`Dockerfile` automatically.
4. Add `GROQ_API_KEY` under Environment Variables.
5. Deploy — future pushes to your main branch redeploy automatically.

**Docker (self-hosted / any VPS):**
```bash
docker build -t talent-lens .
docker run -p 8000:8000 -e GROQ_API_KEY="your-key" talent-lens
```

---

## Product walkthrough

- **Overview** — pipeline funnel, key metrics (active candidates, in interview, offers
  extended, average score), recent activity feed, and your most recent screenings.
- **Pipeline** — a Kanban board across Applied / Screening / Interview / Offer / Hired
  / Rejected. Click any candidate to open a detail panel with their score breakdown,
  matched/missing skills, recruiter brief, and an interview-email generator. Move
  candidates between stages directly from the panel.
- **New screening** — upload a job description (paste or file) and one or more
  resumes. Results are scored, ranked, and automatically added to the pipeline board.
- **Screening results** — the ranked shortlist for your most recent (or any saved) run,
  with score analytics, the parsed role profile, and export options.
- **Analytics** — pipeline-wide funnel, candidates by stage, overall decision mix, and
  candidate volume by role.

## API reference

All endpoints are served under `/api` by `server.py`.

| Method | Path | Description |
|---|---|---|
| `GET` | `/api/health` | Health check for deploy platforms. |
| `POST` | `/api/analyze` | Multipart form: `job_description` (text), optional `jd_file`, and one or more `resumes` files. Runs the full pipeline and returns `{ jd, results, summary }`. |
| `GET` | `/api/runs` | Lists saved screening runs, most recent first. |
| `GET` | `/api/runs/{id}` | Loads a specific saved run's full `{ jd, results, summary }` payload. |
| `POST` | `/api/interview-email` | Body: `{ resume, jd }`. Returns a drafted interview-invite email for a candidate. |
| `POST` | `/api/export/csv` | Body: `{ jd, results }`. Returns a CSV file. |
| `POST` | `/api/export/markdown` | Body: `{ jd, results }`. Returns a full Markdown report. |
| `POST` | `/api/export/recruiter-summary` | Body: `{ jd, results }`. Returns a condensed Markdown recruiter summary. |
| `POST` | `/api/export/pdf` | Body: `{ jd, results }`. Returns a formatted PDF report. |

## Folder structure

```
Talent_Lens/
  server.py                 FastAPI backend (serves the API + built React app)
  smoke_test.py             End-to-end pipeline check
  frontend/                 React + Vite dashboard
    src/App.jsx  src/styles.css  src/main.jsx
    vite.config.js
  agents/
    resume_agent.py         Agent 1 — resume extraction
    jd_agent.py              Agent 2 — JD intelligence
    scoring_agent.py         Agent 3 — scoring
    recruiter_agent.py       Agent 4 — recruiter decision
    pipeline.py              Orchestration
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
  Dockerfile  render.yaml
```

## Design notes

- **Prompts** (`utils/prompts.py`) enforce internal chain-of-thought, strict JSON
  schemas, and an explicit "return `Unknown`, never guess" rule. Protected attributes
  are never inferred.
- **Auditability** — the LLM sees the computed scores and explains them; it cannot
  change them.
- **Persistence** — every screening run is written to SQLite and reloadable. Pipeline
  stage tracking (Kanban board position, activity log) is stored client-side so
  recruiters can freely reorganize candidates without mutating the underlying scored
  results.

## Troubleshooting

**"Couldn't reach the Talent Lens backend" / no analysis appears after clicking
Analyze.**
The frontend and backend are running on mismatched ports. Confirm the backend is on
`:8000` and, if using `npm run dev`, that `frontend/vite.config.js` proxies to
`http://127.0.0.1:8000`.

**`Could not open requirements file: No such file or directory`**
You're not in the project root. Run `cd` (or `pwd` on macOS/Linux) to check your
current directory, then `cd` into the folder containing `requirements.txt` before
re-running `pip install -r requirements.txt`.

**Resume text isn't extracted from a PDF.**
If the PDF is a scanned image rather than text, you need the OCR system dependencies —
see [Optional OCR setup](#optional-ocr-setup).

**No `GROQ_API_KEY` set.**
This is fine — the app runs in fully deterministic fallback mode. Set the key later at
any time to switch to LLM-powered extraction and reasoning.

**Pipeline board looks empty after cloning fresh.**
The Kanban board seeds itself with demo candidates on first load in a new browser (or
after clearing site data), since it's stored in that browser's local storage. Run a
real screening to add your own candidates alongside the demo data.

## Contact
I am down to collaborations and suggestions on making the platform better. 
Mail: reachteju10@gmail.com
