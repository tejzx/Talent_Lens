"""End-to-end pipeline smoke test (runs without an API key)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from agents.pipeline import run_pipeline  # noqa: E402
from utils import report  # noqa: E402
from utils.ranking import summary_stats  # noqa: E402


def main() -> int:
    jd_path = next((ROOT / "data" / "sample_jd").iterdir())
    jd_text = jd_path.read_text(encoding="utf-8")
    files = [(p.name, p.read_bytes()) for p in sorted((ROOT / "data" / "sample_resumes").iterdir())]

    output = run_pipeline(jd_text, files, progress=lambda f, m: print(f"[{f:5.0%}] {m}"))
    results = output["results"]
    assert results, "pipeline produced no results"

    print("\nJD mode:", output["jd"].get("analysis_mode"))
    print("Weighted skills:", output["jd"]["weighted_skills"][:5])
    for r in results:
        print(
            f"#{r['rank']} {r['resume']['name']:<20} {r['scores']['overall_score']:>5} "
            f"{r['decision']:<7} missing={r['scores']['missing_skills'][:3]}"
        )
    print("\nSummary:", summary_stats(results))

    out_dir = ROOT / "output"
    out_dir.mkdir(exist_ok=True)
    (out_dir / "results.csv").write_bytes(report.to_csv(results))
    (out_dir / "results.json").write_bytes(report.to_json(output["jd"], results))
    (out_dir / "report.md").write_text(report.full_markdown_report(output["jd"], results), encoding="utf-8")
    (out_dir / "report.pdf").write_bytes(report.to_pdf(report.full_markdown_report(output["jd"], results)))
    print("Exports written to", out_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
