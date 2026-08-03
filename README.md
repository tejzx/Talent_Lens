# Talent Lens

**A production-shaped, multi-agent resume screening system.**

Upload a job description plus a batch of resumes, click **Analyze**, and get a ranked
recruiter dashboard — per-candidate reasoning, interview questions, an interview-invite
email generator, and CSV / JSON / Markdown / PDF exports.

This is deliberately **not** a ChatGPT wrapper. Scoring is deterministic and auditable
(weighted skill coverage + MiniLM embeddings + FAISS cosine similarity). The LLM is used
for structured extraction and recruiter-facing reasoning — it never invents the score.

---

## Table of contents

- [Architecture](#architecture)
- [Scoring formula](#scoring-formula)
- [Resilience](#resilience)
- [Quick start](#quick-start)
- [Running the frontend and backend separately](#running-the-frontend-and-backend-separately)
- [Configuration](#configuration)
- [Optional OCR setup](#optional-ocr-setup)
- [Sanity check](#sanity-check)
- [Deploying](#deploying)
- [Dashboard](#dashboard)
- [API reference](#api-reference)
- [Folder structure](#folder-structure)
- [Design notes](#design-notes)
- [Troubleshooting](#troubleshooting)

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
  `Reject` < 55.

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
this to work, since that's also the port used by the Dockerfile/Procfile in production.

## Configuration

| Variable | Required | Description |
|---|---|---|
| `GROQ_API_KEY` | No | Enables LLM-powered extraction and recruiter reasoning. Without it, the app uses deterministic regex/keyword fallbacks and still works fully. |
| `GROQ_MODEL` | No | Overrides the default model (`llama-3.3-70b-versatile`). |
| `PORT` | No | Used by the Dockerfile/Procfile in hosted environments; defaults to `8000`. |

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

The repository includes a production `Dockerfile`, `Procfile`, and `render.yaml`.
The Docker image builds the React frontend and serves it from the FastAPI application
on a single port, with `/api/health` as the health-check path.

```bash
docker build -t talent-lens .
docker run -p 8000:8000 -e GROQ_API_KEY="your-key" talent-lens
```

For Render: connect the repository, set `GROQ_API_KEY` as a private environment
variable in the dashboard, and deploy from the repo root — `render.yaml` handles the
rest.

---

## Dashboard

- **Cards** — total candidates, average score, top candidate, next-round count.
- **Candidates tab** — ranked candidate list with per-candidate detail: score
  breakdown, matched/missing skills, recruiter brief, and an interview-invite email
  generator for candidates who clear the threshold.
- **Analytics tab** — score-by-candidate bar chart and Hire/Maybe/Reject decision mix.
- **Role profile tab** — weighted requirement chart and job profile summary.
- **Exports tab** — CSV, JSON, Markdown report, recruiter summary, and PDF report.
- **Pipeline history** — every screening run is persisted to SQLite and reloadable;
  "Open candidate pipeline" surfaces the most recent run first, with a picker to switch
  between past runs.

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
  Dockerfile  Procfile  render.yaml
```

## Design notes

- **Prompts** (`utils/prompts.py`) enforce internal chain-of-thought, strict JSON
  schemas, and an explicit "return `Unknown`, never guess" rule. Protected attributes
  are never inferred.
- **Auditability** — the LLM sees the computed scores and explains them; it cannot
  change them.
- **Persistence** — every run is written to SQLite and reloadable from the dashboard's
  pipeline history.

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
