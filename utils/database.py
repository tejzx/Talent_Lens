"""SQLite persistence for screening runs and candidate results."""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "screening.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  created_at TEXT NOT NULL,
  job_title TEXT,
  jd_profile TEXT NOT NULL,
  candidate_count INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id INTEGER NOT NULL REFERENCES runs(id) ON DELETE CASCADE,
  filename TEXT,
  name TEXT,
  email TEXT,
  score REAL NOT NULL,
  decision TEXT,
  rank INTEGER,
  payload TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS candidates_run_idx ON candidates(run_id);
"""


def connect(db_path: Path | str = DB_PATH) -> sqlite3.Connection:
    path = Path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA)
    return conn


def save_run(jd_profile: dict, results: list[dict], db_path: Path | str = DB_PATH) -> int:
    conn = connect(db_path)
    with conn:
        cur = conn.execute(
            "INSERT INTO runs (created_at, job_title, jd_profile, candidate_count) VALUES (?,?,?,?)",
            (
                datetime.now(timezone.utc).isoformat(timespec="seconds"),
                jd_profile.get("job_title", "Unknown"),
                json.dumps(jd_profile),
                len(results),
            ),
        )
        run_id = int(cur.lastrowid)
        conn.executemany(
            "INSERT INTO candidates (run_id, filename, name, email, score, decision, rank, payload)"
            " VALUES (?,?,?,?,?,?,?,?)",
            [
                (
                    run_id,
                    r.get("filename"),
                    r["resume"].get("name"),
                    r["resume"].get("email"),
                    r["scores"]["overall_score"],
                    r.get("decision"),
                    r.get("rank"),
                    json.dumps(r),
                )
                for r in results
            ],
        )
    conn.close()
    return run_id


def list_runs(limit: int = 25, db_path: Path | str = DB_PATH) -> list[dict]:
    conn = connect(db_path)
    rows = conn.execute(
        "SELECT id, created_at, job_title, candidate_count FROM runs ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def load_run(run_id: int, db_path: Path | str = DB_PATH) -> tuple[dict, list[dict]]:
    conn = connect(db_path)
    run = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
    rows = conn.execute(
        "SELECT payload FROM candidates WHERE run_id = ? ORDER BY rank", (run_id,)
    ).fetchall()
    conn.close()
    if run is None:
        return {}, []
    return json.loads(run["jd_profile"]), [json.loads(r["payload"]) for r in rows]
