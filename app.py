"""AI Resume Screening Agent — Streamlit application.

Run:  streamlit run app.py
"""
from __future__ import annotations

import os
from pathlib import Path

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from agents.pipeline import run_pipeline
from agents.recruiter_agent import shortlist_email
from parser import extract_text
from utils import database, report
from utils.llm import is_configured
from utils.ranking import filter_results, skill_frequency, summary_stats, to_dataframe

ROOT = Path(__file__).resolve().parent
SAMPLE_JD = ROOT / "data" / "sample_jd"
SAMPLE_RESUMES = ROOT / "data" / "sample_resumes"

DECISION_COLORS = {"Hire": "#16a34a", "Maybe": "#f59e0b", "Reject": "#dc2626"}

st.set_page_config(page_title="Talent Lens | AI screening", page_icon="◈", layout="wide", initial_sidebar_state="expanded")

st.markdown(
    """
    <style>
      :root {--ink:#102a43; --muted:#627d98; --line:#d9e2ec; --canvas:#f6f9fc; --teal:#087f8c; --navy:#102a43;}
      .stApp {background: var(--canvas); color:var(--ink);}
      .block-container {padding: 1.4rem 2rem 3rem; max-width: 1450px;}
      [data-testid="stSidebar"] {background: linear-gradient(180deg,#102a43 0%,#163f5f 100%);}
      [data-testid="stSidebar"] * {color:#f4f9ff;}
      [data-testid="stSidebar"] [data-testid="stAlert"] * {color:inherit;}
      .hero {padding:2rem 2.1rem; margin:0 0 1.5rem; border-radius:22px; color:#fff;
             background: radial-gradient(circle at 90% 10%,#38b2ac 0%,transparent 32%), linear-gradient(120deg,#102a43,#1a4b6e);
             box-shadow:0 16px 35px rgba(16,42,67,.18);}
      .hero .eyebrow {margin:0 0 .55rem; color:#91f5df; text-transform:uppercase; letter-spacing:.14em; font-size:.75rem; font-weight:700;}
      .hero h1 {margin:0; color:#fff; font-size:clamp(2rem,3.6vw,3rem); line-height:1.08; letter-spacing:-.04em;}
      .hero p {margin:.7rem 0 0; color:#d9eff4; font-size:1.03rem; max-width:650px;}
      .section-label {margin:1.5rem 0 .55rem; color:var(--muted); font-size:.76rem; font-weight:700; letter-spacing:.1em; text-transform:uppercase;}
      .metric-card {background:#fff; border:1px solid var(--line); border-radius:16px; min-height:108px;
                    padding:17px 19px; box-shadow:0 4px 12px rgba(16,42,67,.045);}
      .metric-card h3 {margin:0; font-size:.7rem; letter-spacing:.09em; text-transform:uppercase; color:var(--muted); font-weight:700;}
      .metric-card p {margin:8px 0 0; font-size:1.72rem; line-height:1.05; font-weight:750; color:var(--ink); overflow-wrap:anywhere;}
      .pill {display:inline-block; padding:4px 10px; border-radius:999px; font-size:.72rem; font-weight:700; color:#fff; vertical-align:middle;}
      .info-card {background:#fff; border:1px solid var(--line); border-radius:16px; padding:1.1rem 1.2rem; margin:.45rem 0 1rem;}
      .info-card h3 {margin:0 0 .35rem; color:var(--ink); font-size:1rem;}
      .info-card p {margin:0; color:var(--muted); line-height:1.55;}
      .stButton > button, .stDownloadButton > button {border-radius:10px; font-weight:650; min-height:2.55rem;}
      .stButton > button[kind="primary"] {background:var(--teal); border-color:var(--teal);}
      [data-testid="stDataFrame"] {border:1px solid var(--line); border-radius:12px; overflow:hidden;}
      .stTabs [data-baseweb="tab-list"] {gap:.35rem; border-bottom:1px solid var(--line);}
      .stTabs [data-baseweb="tab"] {border-radius:9px 9px 0 0; padding:.65rem 1rem; font-weight:650;}
      .stTabs [aria-selected="true"] {background:#e6fffa; color:#065f63;}
    </style>
    """,
    unsafe_allow_html=True,
)


# --------------------------------------------------------------------------- #
# Sidebar
# --------------------------------------------------------------------------- #
def sidebar() -> None:
    with st.sidebar:
        st.title("◈ Talent Lens")
        st.caption("Structured, explainable hiring intelligence.")

        st.subheader("Model")
        if is_configured():
            st.success("Groq connected")
            st.caption("Model: " + os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"))
        else:
            st.warning("No GROQ_API_KEY — using deterministic fallback analysis.")
            key = st.text_input("Groq API key", type="password", help="Used only for this session unless you add it to .env.")
            if key:
                os.environ["GROQ_API_KEY"] = key
                st.rerun()

        st.subheader("Pipeline")
        st.markdown(
            "01. **Resume extraction**\n"
            "02. **Role intelligence**\n"
            "03. **Auditable scoring**\n"
            "04. **Recruiter decision brief**"
        )

        st.subheader("Score weights")
        st.markdown(
            "Skills 40% · Experience 20% · Projects 15% · Education 10% · "
            "Certifications 5% · Soft skills 5% · Semantic 5%"
        )

        runs = database.list_runs(limit=10)
        if runs:
            st.subheader("Past runs")
            labels = {f"#{r['id']} · {r['job_title']} ({r['candidate_count']})": r["id"] for r in runs}
            picked = st.selectbox("Load a saved run", ["—"] + list(labels))
            if picked != "—" and st.button("Load run", use_container_width=True):
                jd, results = database.load_run(labels[picked])
                st.session_state.update(jd=jd, results=results, errors=[])
                st.rerun()


# --------------------------------------------------------------------------- #
# Inputs
# --------------------------------------------------------------------------- #
def read_uploads(uploads) -> list[tuple[str, bytes]]:
    return [(f.name, f.getvalue()) for f in uploads or []]


def sample_files(folder: Path) -> list[tuple[str, bytes]]:
    if not folder.exists():
        return []
    return [(p.name, p.read_bytes()) for p in sorted(folder.iterdir()) if p.is_file()]


def input_section() -> None:
    st.markdown(
        """<section class='hero'>
          <p class='eyebrow'>Recruiting workspace</p>
          <h1>Turn a resume pile into a confident shortlist.</h1>
          <p>Upload a role and candidate resumes to get evidence-backed scores, interview focus areas, and export-ready decisions.</p>
        </section>""",
        unsafe_allow_html=True,
    )
    st.markdown("<p class='section-label'>Build your screening batch</p>", unsafe_allow_html=True)

    left, right = st.columns(2, gap="large")
    with left:
        st.markdown("<div class='info-card'><h3>1 · Define the role</h3><p>Add the job description as a file or paste it directly. The role requirements become the scoring rubric.</p></div>", unsafe_allow_html=True)
        jd_file = st.file_uploader("Job description file", type=["pdf", "docx", "txt", "md"], help="PDF, DOCX, TXT, or Markdown")
        jd_text = st.text_area("Or paste the job description", height=210, key="jd_text_input", placeholder="Paste the role overview, required skills, responsibilities, and experience level…")
        if st.button("Use sample JD", use_container_width=True):
            samples = sample_files(SAMPLE_JD)
            if samples:
                st.session_state.jd_text_input = extract_text(*samples[0])
                st.rerun()
            st.warning("No sample JD found in data/sample_jd/.")

    with right:
        st.markdown("<div class='info-card'><h3>2 · Add candidates</h3><p>Select one or many resumes. Their names and contact details are extracted from the source files.</p></div>", unsafe_allow_html=True)
        uploads = st.file_uploader(
            "Candidate resumes",
            type=["pdf", "docx", "txt", "md"],
            accept_multiple_files=True,
        )
        use_samples = st.checkbox("Include sample resumes from data/sample_resumes/")
        files = read_uploads(uploads) + (sample_files(SAMPLE_RESUMES) if use_samples else [])
        st.info(f"{len(files)} candidate{'s' if len(files) != 1 else ''} ready for review.")

    if jd_file is not None and not jd_text.strip():
        jd_text = extract_text(jd_file.name, jd_file.getvalue())

    st.divider()
    st.caption("Your scores remain deterministic and auditable. The LLM only improves extraction and recruiter-facing context.")
    if st.button("Analyze candidates", type="primary", use_container_width=True):
        if not jd_text.strip():
            st.error("Add a job description first.")
            return
        if not files:
            st.error("Add at least one resume.")
            return
        bar = st.progress(0.0, text="Preparing your screening run…")
        output = run_pipeline(jd_text, files, progress=lambda f, m: bar.progress(f, text=m))
        bar.empty()
        st.session_state.update(jd=output["jd"], results=output["results"], errors=output["errors"])
        try:
            database.save_run(output["jd"], output["results"])
        except Exception as exc:  # pragma: no cover
            st.warning(f"Run not saved to database: {exc}")
        st.rerun()


# --------------------------------------------------------------------------- #
# Dashboard
# --------------------------------------------------------------------------- #
def metric_card(label: str, value: str) -> None:
    st.markdown(f"<div class='metric-card'><h3>{label}</h3><p>{value}</p></div>", unsafe_allow_html=True)


def charts(results: list[dict]) -> None:
    df = to_dataframe(results)
    c1, c2 = st.columns(2, gap="large")

    with c1:
        fig = px.histogram(df, x="Score", nbins=10, title="Score distribution",
                           color_discrete_sequence=["#2563eb"])
        fig.update_layout(bargap=0.08, height=340)
        st.plotly_chart(fig, use_container_width=True, key="score-distribution-chart")

        matched = skill_frequency(results, "matched_skills", 10)
        if matched:
            mdf = pd.DataFrame(matched, columns=["Skill", "Candidates"])
            st.plotly_chart(
                px.bar(mdf, x="Candidates", y="Skill", orientation="h",
                       title="Top skills present in the pool",
                       color_discrete_sequence=["#16a34a"]).update_layout(height=340),
                use_container_width=True, key="matched-skills-chart",
            )

    with c2:
        ranking = df.sort_values("Score")
        fig = px.bar(ranking, x="Score", y="Candidate", orientation="h", color="Status",
                     title="Candidate ranking", color_discrete_map=DECISION_COLORS)
        fig.update_layout(height=340)
        st.plotly_chart(fig, use_container_width=True, key="candidate-ranking-chart")

        missing = skill_frequency(results, "missing_skills", 10)
        if missing:
            mdf = pd.DataFrame(missing, columns=["Skill", "Candidates"])
            st.plotly_chart(
                px.bar(mdf, x="Candidates", y="Skill", orientation="h",
                       title="Most common skill gaps",
                       color_discrete_sequence=["#dc2626"]).update_layout(height=340),
                use_container_width=True, key="missing-skills-chart",
            )

    dims = ["Skill Match", "Experience Match", "Project Match", "Education Match",
            "Certification Match", "Soft Skill Match", "Semantic Similarity"]
    coverage = df[dims].mean().reset_index()
    coverage.columns = ["Dimension", "Average"]
    st.plotly_chart(
        px.bar(coverage, x="Dimension", y="Average", title="Average coverage by dimension",
               color_discrete_sequence=["#7c3aed"]).update_layout(height=320),
        use_container_width=True, key="coverage-chart",
    )


def radar(results: list[dict], names: list[str]) -> go.Figure:
    dims = ["skill_match", "experience_match", "project_match", "education_match",
            "certification_match", "soft_skill_match", "semantic_similarity"]
    labels = ["Skills", "Experience", "Projects", "Education", "Certs", "Soft skills", "Semantic"]
    fig = go.Figure()
    for r in results:
        name = r["resume"].get("name") or r["filename"]
        if name not in names:
            continue
        fig.add_trace(go.Scatterpolar(
            r=[r["scores"].get(d, 0) for d in dims] + [r["scores"].get(dims[0], 0)],
            theta=labels + [labels[0]], fill="toself", name=name))
    fig.update_layout(polar={"radialaxis": {"visible": True, "range": [0, 100]}},
                      height=430, title="Capability radar")
    return fig


def candidate_detail(result: dict, jd: dict) -> None:
    resume, scores = result["resume"], result["scores"]
    color = DECISION_COLORS.get(result.get("decision", ""), "#6b7280")
    st.markdown(
        f"### {resume.get('name') or 'Unknown'} "
        f"<span class='pill' style='background:{color}'>{result.get('decision')}</span>",
        unsafe_allow_html=True,
    )
    a, b, c, d = st.columns(4)
    a.metric("Overall score", scores["overall_score"])
    b.metric("Experience", f"{resume.get('years_experience', 0)} yrs")
    c.metric("Confidence", scores.get("confidence", 0))
    d.metric("Rank", result.get("rank", "—"))

    st.caption(
        f"Email: {resume.get('email') or 'Unknown'}  |  Phone: {resume.get('phone') or 'Unknown'}  |  "
        f"GitHub: {resume.get('github') or 'Unknown'}  |  LinkedIn: {resume.get('linkedin') or 'Unknown'}"
    )
    m1, m2 = st.columns(2)
    m1.success("**Matched skills**\n\n" + (", ".join(scores.get("matched_skills", [])) or "None"))
    m2.error("**Missing skills**\n\n" + (", ".join(scores.get("missing_skills", [])) or "None"))

    st.plotly_chart(radar([result], [resume.get("name") or result["filename"]]), use_container_width=True,
                    key=f"candidate-radar-{result['filename']}")
    st.markdown(result.get("brief", "_No brief available._"))

    with st.expander("Structured resume JSON"):
        st.json(resume)
    with st.expander("View parsed resume text"):
        st.text(result.get("resume_text", "")[:20000] or "Unknown")

    e1, e2, e3 = st.columns(3)
    e1.download_button("Download JSON", report.to_json(jd, [result]),
                       file_name=f"{resume.get('name','candidate')}.json", mime="application/json",
                       use_container_width=True)
    e2.download_button("Download report (MD)", report.candidate_markdown(result).encode(),
                       file_name=f"{resume.get('name','candidate')}.md", mime="text/markdown",
                       use_container_width=True)
    e3.download_button("Download report (PDF)",
                       report.to_pdf(report.candidate_markdown(result), "Candidate report"),
                       file_name=f"{resume.get('name','candidate')}.pdf", mime="application/pdf",
                       use_container_width=True)

    if result.get("decision") in ("Hire", "Maybe"):
        if st.button("Generate interview invitation email", key=f"email-{result['filename']}"):
            st.code(shortlist_email(resume, jd), language="text")


def dashboard() -> None:
    jd = st.session_state["jd"]
    results = st.session_state["results"]
    stats = summary_stats(results)

    st.markdown(
        f"""<section class='hero'>
          <p class='eyebrow'>Screening results</p>
          <h1>{jd.get('job_title', 'Unknown role')}</h1>
          <p>Review the shortlist, investigate candidates, and share a decision-ready report.</p>
        </section>""",
        unsafe_allow_html=True,
    )
    for err in st.session_state.get("errors", []):
        st.warning(err)

    st.markdown("<p class='section-label'>At a glance</p>", unsafe_allow_html=True)
    cols = st.columns(4, gap="medium")
    with cols[0]:
        metric_card("Total candidates", str(stats["total"]))
    with cols[1]:
        metric_card("Average score", str(stats["average_score"]))
    with cols[2]:
        metric_card("Top candidate", stats["top_candidate"])
    with cols[3]:
        metric_card("Hiring rate", f"{stats['hiring_rate']}%")

    st.divider()
    tabs = st.tabs(["Candidate review", "Analytics", "Compare", "Role profile", "Exports"])

    with tabs[0]:
        f1, f2, f3 = st.columns([1, 1, 2])
        min_score = f1.slider("Minimum score", 0, 100, 0)
        statuses = f2.multiselect("Status", ["Hire", "Maybe", "Reject"], default=["Hire", "Maybe", "Reject"])
        skill_query = f3.text_input("Search by skill (comma separated)", placeholder="python, sql")
        shown = filter_results(results, min_score=min_score, statuses=statuses, skill_query=skill_query)
        st.caption(f"Showing {len(shown)} of {len(results)} candidates.")

        if shown:
            table = to_dataframe(shown)[
                ["Rank", "Candidate", "Score", "Status", "Years Experience", "Matched Skills", "Missing Skills"]
            ]
            st.dataframe(table, use_container_width=True, hide_index=True)
            names = {f"{r['resume'].get('name') or r['filename']} — {r['scores']['overall_score']}": r for r in shown}
            picked = st.selectbox("Open candidate profile", list(names))
            st.divider()
            candidate_detail(names[picked], jd)
        else:
            st.info("No candidates match the current filters.")

    with tabs[1]:
        charts(results)

    with tabs[2]:
        options = [r["resume"].get("name") or r["filename"] for r in results]
        chosen = st.multiselect("Compare candidates", options, default=options[: min(3, len(options))])
        if chosen:
            st.plotly_chart(radar(results, chosen), use_container_width=True, key="comparison-radar")
            compare_df = to_dataframe([r for r in results if (r["resume"].get("name") or r["filename"]) in chosen])
            st.dataframe(compare_df.set_index("Candidate").T, use_container_width=True)

        st.subheader("Shortlisted vs rejected")
        shortlisted = [r for r in results if r.get("decision") in ("Hire", "Maybe")]
        rejected = [r for r in results if r.get("decision") == "Reject"]
        s1, s2 = st.columns(2)
        s1.metric("Shortlisted", len(shortlisted))
        s2.metric("Rejected", len(rejected))
        if shortlisted or rejected:
            comparison = pd.DataFrame(
                {
                    "Group": ["Shortlisted", "Rejected"],
                    "Average score": [
                        round(sum(r["scores"]["overall_score"] for r in shortlisted) / len(shortlisted), 1) if shortlisted else 0,
                        round(sum(r["scores"]["overall_score"] for r in rejected) / len(rejected), 1) if rejected else 0,
                    ],
                    "Average experience": [
                        round(sum(r["resume"].get("years_experience") or 0 for r in shortlisted) / len(shortlisted), 1) if shortlisted else 0,
                        round(sum(r["resume"].get("years_experience") or 0 for r in rejected) / len(rejected), 1) if rejected else 0,
                    ],
                }
            )
            st.plotly_chart(
                px.bar(comparison, x="Group", y=["Average score", "Average experience"], barmode="group",
                       title="Shortlisted vs rejected"),
                use_container_width=True, key="shortlist-comparison-chart",
            )

    with tabs[3]:
        st.subheader(jd.get("job_title", "Unknown role"))
        c1, c2, c3 = st.columns(3)
        c1.metric("Industry", jd.get("industry") or "Unknown")
        c2.metric("Seniority", jd.get("seniority") or "Unknown")
        c3.metric("Min experience", f"{jd.get('min_years_experience', 0)} yrs")
        weighted = jd.get("weighted_skills") or []
        if weighted:
            wdf = pd.DataFrame(weighted)
            st.plotly_chart(
                px.bar(wdf.sort_values("weight"), x="weight", y="skill", color="category",
                       orientation="h", title="Weighted requirements").update_layout(height=460),
                use_container_width=True, key="weighted-skills-chart",
            )
        st.json(jd)

    with tabs[4]:
        st.subheader("Share the screening outcome")
        st.caption("Download structured data, candidate reports, or a recruiter-ready summary.")
        e1, e2 = st.columns(2)
        e1.download_button("⬇️ CSV (all candidates)", report.to_csv(results),
                           file_name="screening_results.csv", mime="text/csv", use_container_width=True)
        e2.download_button("⬇️ JSON (full payload)", report.to_json(jd, results),
                           file_name="screening_results.json", mime="application/json", use_container_width=True)
        e3, e4 = st.columns(2)
        markdown_report = report.full_markdown_report(jd, results)
        e3.download_button("⬇️ Markdown report", markdown_report.encode(),
                           file_name="screening_report.md", mime="text/markdown", use_container_width=True)
        e4.download_button("⬇️ PDF report", report.to_pdf(markdown_report, "Screening report"),
                           file_name="screening_report.pdf", mime="application/pdf", use_container_width=True)
        st.download_button("⬇️ Recruiter summary", report.recruiter_summary(jd, results).encode(),
                           file_name="recruiter_summary.md", mime="text/markdown", use_container_width=True)
        st.markdown("---")
        st.markdown(report.recruiter_summary(jd, results))

    st.divider()
    if st.button("Start a new screening run"):
        for key in ("jd", "results", "errors"):
            st.session_state.pop(key, None)
        st.rerun()


def main() -> None:
    sidebar()
    if st.session_state.get("results"):
        dashboard()
    else:
        input_section()


if __name__ == "__main__":
    main()
