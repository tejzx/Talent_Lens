import { useEffect, useMemo, useRef, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

/* ---------------------------------------------------------------- */
/* Constants & helpers                                               */
/* ---------------------------------------------------------------- */

const STAGES = ['Applied', 'Screening', 'Interview', 'Offer', 'Hired']
const STAGE_COLOR = {
  Applied: '#8291a4', Screening: '#3d7ff0', Interview: '#d88918',
  Offer: '#7a4fd1', Hired: '#16826c', Rejected: '#c55353',
}
const decisionColor = { Hire: '#16826c', Maybe: '#d88918', Reject: '#c55353' }
const scoreKeys = [
  ['skill_match', 'Skills'], ['experience_match', 'Experience'], ['project_match', 'Projects'],
  ['education_match', 'Education'], ['certification_match', 'Certifications'],
  ['soft_skill_match', 'Soft skills'], ['semantic_similarity', 'Semantic'],
]
const PIPELINE_KEY = 'talent-lens-pipeline-v1'
const ACTIVITY_KEY = 'talent-lens-activity-v1'

function uid() { return `c-${Date.now()}-${Math.random().toString(36).slice(2, 8)}` }
function initials(name = '') { return name.split(' ').filter(Boolean).slice(0, 2).map(w => w[0]).join('').toUpperCase() || '—' }
function formatFileName(file) { return file ? file.name : 'No file selected' }
function formatBytes(bytes) { if (!bytes) return '0 KB'; const kb = bytes / 1024; return kb < 1024 ? `${kb.toFixed(0)} KB` : `${(kb / 1024).toFixed(1)} MB` }
function formatDate(iso) {
  if (!iso) return ''
  try { return new Date(iso).toLocaleString(undefined, { month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }) }
  catch { return iso }
}
function timeAgo(iso) {
  const diff = Date.now() - new Date(iso).getTime()
  const mins = Math.round(diff / 60000)
  if (mins < 1) return 'just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.round(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return `${Math.round(hrs / 24)}d ago`
}
async function readError(response, fallback) {
  try { const body = await response.json(); return body.detail || fallback } catch { return fallback }
}
async function triggerDownload(path, payload, filename) {
  const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
  if (!response.ok) throw new Error(await readError(response, 'The export could not be generated.'))
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = filename; link.click()
  URL.revokeObjectURL(url)
}
function stageForScore(score) {
  if (score >= 75) return 'Interview'
  if (score >= 55) return 'Screening'
  return 'Rejected'
}

/* ---------------------------------------------------------------- */
/* Seed / persistence                                                */
/* ---------------------------------------------------------------- */

const SEED_CANDIDATES = [
  { name: 'Ananya Sharma', role: 'Senior Data Analyst', score: 88, stage: 'Hired', days: 21 },
  { name: 'Rahul Menon', role: 'Backend Engineer', score: 81, stage: 'Offer', days: 9 },
  { name: 'Sofia Alvarez', role: 'Product Designer', score: 79, stage: 'Offer', days: 6 },
  { name: 'David Okafor', role: 'Backend Engineer', score: 77, stage: 'Interview', days: 5 },
  { name: 'Meera Iyer', role: 'Senior Data Analyst', score: 74, stage: 'Interview', days: 4 },
  { name: 'James Whitfield', role: 'Data Engineer', score: 72, stage: 'Interview', days: 3 },
  { name: 'Priya Raghavan', role: 'Data Engineer', score: 68, stage: 'Screening', days: 2 },
  { name: 'Lucas Bergmann', role: 'Product Designer', score: 64, stage: 'Screening', days: 2 },
  { name: 'Nadia Hussain', role: 'Backend Engineer', score: 60, stage: 'Screening', days: 1 },
  { name: 'Tomás Rivera', role: 'Senior Data Analyst', score: 58, stage: 'Applied', days: 1 },
  { name: 'Grace Lin', role: 'Data Engineer', score: 55, stage: 'Applied', days: 1 },
  { name: 'Owen Brooks', role: 'Product Designer', score: 52, stage: 'Applied', days: 0 },
  { name: 'Farah Aziz', role: 'Backend Engineer', score: 41, stage: 'Rejected', days: 8 },
  { name: 'Ken Watanabe', role: 'Data Engineer', score: 37, stage: 'Rejected', days: 6 },
  { name: 'Isla Fraser', role: 'Senior Data Analyst', score: 33, stage: 'Rejected', days: 3 },
]

function seedPipeline() {
  const now = Date.now()
  return SEED_CANDIDATES.map(seed => ({
    id: uid(),
    name: seed.name,
    email: `${seed.name.toLowerCase().replace(/[^a-z]+/g, '.')}@example.com`,
    role: seed.role,
    score: seed.score,
    decision: seed.score >= 75 ? 'Hire' : seed.score >= 55 ? 'Maybe' : 'Reject',
    stage: seed.stage,
    source: 'demo',
    matched: [],
    missing: [],
    brief: '',
    addedAt: new Date(now - seed.days * 86400000).toISOString(),
    updatedAt: new Date(now - Math.max(seed.days - 1, 0) * 86400000).toISOString(),
  }))
}

function loadPipeline() {
  try {
    const raw = localStorage.getItem(PIPELINE_KEY)
    if (raw) return JSON.parse(raw)
  } catch { /* ignore corrupt storage */ }
  const seeded = seedPipeline()
  try { localStorage.setItem(PIPELINE_KEY, JSON.stringify(seeded)) } catch { /* storage unavailable */ }
  return seeded
}
function savePipeline(list) { try { localStorage.setItem(PIPELINE_KEY, JSON.stringify(list)) } catch { /* storage unavailable */ } }

function loadActivity() {
  try { const raw = localStorage.getItem(ACTIVITY_KEY); if (raw) return JSON.parse(raw) } catch { /* ignore */ }
  return []
}
function saveActivity(list) { try { localStorage.setItem(ACTIVITY_KEY, JSON.stringify(list.slice(0, 40))) } catch { /* ignore */ } }

function resultsToCandidates(jd, results) {
  return results.map(candidate => ({
    id: uid(),
    name: candidate.resume.name || candidate.filename,
    email: candidate.resume.email && candidate.resume.email !== 'Unknown' ? candidate.resume.email : '',
    role: jd.job_title || 'Untitled role',
    score: candidate.scores.overall_score,
    decision: candidate.decision,
    stage: stageForScore(candidate.scores.overall_score),
    source: 'screening',
    matched: candidate.scores.matched_skills || [],
    missing: candidate.scores.missing_skills || [],
    brief: candidate.brief || '',
    addedAt: new Date().toISOString(),
    updatedAt: new Date().toISOString(),
  }))
}

/* ---------------------------------------------------------------- */
/* Root app                                                          */
/* ---------------------------------------------------------------- */

const NAV = [
  { id: 'overview', label: 'Overview', icon: '◧' },
  { id: 'pipeline', label: 'Pipeline', icon: '☰' },
  { id: 'intake', label: 'New screening', icon: '＋' },
  { id: 'results', label: 'Screening results', icon: '▤' },
  { id: 'analytics', label: 'Analytics', icon: '◔' },
]

export default function App() {
  const [page, setPage] = useState('overview')
  const [pipeline, setPipeline] = useState(loadPipeline)
  const [activity, setActivity] = useState(loadActivity)
  const [runs, setRuns] = useState([])
  const [runsLoading, setRunsLoading] = useState(true)

  const [jd, setJd] = useState('')
  const [jdFile, setJdFile] = useState(null)
  const [resumes, setResumes] = useState([])
  const [screening, setScreening] = useState(null)
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState(null)
  const resumeInput = useRef(null)

  const [drawerCandidate, setDrawerCandidate] = useState(null)

  useEffect(() => { savePipeline(pipeline) }, [pipeline])
  useEffect(() => { saveActivity(activity) }, [activity])
  useEffect(() => { refreshRuns() }, [])

  async function refreshRuns() {
    setRunsLoading(true)
    try {
      const response = await fetch('/api/runs')
      if (!response.ok) throw new Error('runs unavailable')
      setRuns(await response.json())
    } catch { setRuns([]) } finally { setRunsLoading(false) }
  }

  function logActivity(text) {
    setActivity(prev => [{ id: uid(), text, at: new Date().toISOString() }, ...prev])
  }

  function addResumes(fileList) {
    const incoming = Array.from(fileList || [])
    if (!incoming.length) return
    setResumes(prev => {
      const seen = new Set(prev.map(f => `${f.name}-${f.size}`))
      const merged = [...prev]
      for (const file of incoming) { const key = `${file.name}-${file.size}`; if (!seen.has(key)) { merged.push(file); seen.add(key) } }
      return merged
    })
  }
  function removeResume(index) { setResumes(prev => prev.filter((_, i) => i !== index)) }

  async function analyze() {
    if (!jd.trim() && !jdFile) return setNotice({ kind: 'error', text: 'Add a job description to begin.' })
    if (!resumes.length) return setNotice({ kind: 'error', text: 'Add at least one candidate resume to begin.' })
    setLoading(true); setNotice(null)
    const form = new FormData()
    form.append('job_description', jd)
    if (jdFile) form.append('jd_file', jdFile)
    resumes.forEach(file => form.append('resumes', file))
    try {
      const response = await fetch('/api/analyze', { method: 'POST', body: form })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || 'The screening run could not be completed.')
      setScreening(body)

      const added = resultsToCandidates(body.jd, body.results)
      setPipeline(prev => [...added, ...prev])
      const counts = added.reduce((acc, c) => { acc[c.stage] = (acc[c.stage] || 0) + 1; return acc }, {})
      const breakdown = Object.entries(counts).map(([stage, n]) => `${n} → ${stage}`).join(', ')
      logActivity(`New screening "${body.jd.job_title || 'Untitled role'}" added ${added.length} candidate${added.length === 1 ? '' : 's'} to the pipeline (${breakdown}).`)

      setPage('results')
      setNotice({ kind: 'success', text: `Screening complete — ${body.results.length} candidate${body.results.length === 1 ? '' : 's'} added to your pipeline.` })
      refreshRuns()
    } catch (error) {
      const isNetworkError = error instanceof TypeError
      setNotice({ kind: 'error', text: isNetworkError ? "Couldn't reach the Talent Lens backend. Make sure the API server is running." : error.message })
    } finally { setLoading(false) }
  }

  async function loadRun(runId) {
    const response = await fetch(`/api/runs/${runId}`)
    if (!response.ok) throw new Error(await readError(response, 'That screening run could not be loaded.'))
    return response.json()
  }
  async function switchRun(runId) {
    setNotice(null)
    try { setScreening(await loadRun(runId)); setPage('results') }
    catch (error) { setNotice({ kind: 'error', text: error.message }) }
  }

  function moveStage(id, stage) {
    setPipeline(prev => prev.map(c => c.id === id ? { ...c, stage, updatedAt: new Date().toISOString() } : c))
    const candidate = pipeline.find(c => c.id === id)
    if (candidate) logActivity(`${candidate.name} moved to ${stage}.`)
    setDrawerCandidate(current => current && current.id === id ? { ...current, stage } : current)
  }

  async function download(kind) {
    if (!screening) return
    const { jd: currentJd, results } = screening
    try {
      if (kind === 'csv') return downloadClientFile(csv(results), 'talent-lens-results.csv', 'text/csv')
      if (kind === 'json') return downloadClientFile(JSON.stringify(screening, null, 2), 'talent-lens-results.json', 'application/json')
      const routes = {
        markdown: ['/api/export/markdown', 'talent-lens-report.md'],
        pdf: ['/api/export/pdf', 'talent-lens-report.pdf'],
        summary: ['/api/export/recruiter-summary', 'recruiter-summary.md'],
      }
      const [path, filename] = routes[kind]
      await triggerDownload(path, { jd: currentJd, results }, filename)
    } catch (error) { setNotice({ kind: 'error', text: error.message || 'The export could not be generated.' }) }
  }

  return (
    <div className="app-shell-v2">
      <Sidebar page={page} setPage={setPage} pipelineCount={pipeline.length} />
      <div className="main-column">
        <Topbar page={page} runs={runs} switchRun={switchRun} startScreening={() => setPage('intake')} />
        <div className="page-body">
          {page === 'overview' && (
            <Overview pipeline={pipeline} activity={activity} runs={runs} runsLoading={runsLoading}
              startScreening={() => setPage('intake')} openPipeline={() => setPage('pipeline')} switchRun={switchRun} />
          )}
          {page === 'pipeline' && (
            <Pipeline pipeline={pipeline} moveStage={moveStage} openDrawer={setDrawerCandidate} startScreening={() => setPage('intake')} />
          )}
          {page === 'intake' && (
            <Intake jd={jd} setJd={setJd} jdFile={jdFile} setJdFile={setJdFile}
              resumes={resumes} addResumes={addResumes} removeResume={removeResume} resumeInput={resumeInput}
              analyze={analyze} loading={loading} notice={notice} />
          )}
          {page === 'results' && (
            screening
              ? <Results screening={screening} download={download} notice={notice} runs={runs} switchRun={switchRun} goToPipeline={() => setPage('pipeline')} />
              : <EmptyState title="No screening open yet" body="Run a new screening or open a saved one from Overview to see results here." action={{ label: 'Start a screening', onClick: () => setPage('intake') }} />
          )}
          {page === 'analytics' && <Analytics pipeline={pipeline} />}
        </div>
      </div>
      {drawerCandidate && (
        <CandidateDrawer candidate={drawerCandidate} close={() => setDrawerCandidate(null)} moveStage={moveStage} jd={screening?.jd} />
      )}
    </div>
  )
}

function downloadClientFile(content, filename, type) {
  const blob = new Blob([content], { type })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = filename; link.click()
  URL.revokeObjectURL(url)
}

/* ---------------------------------------------------------------- */
/* Sidebar & Topbar                                                   */
/* ---------------------------------------------------------------- */

function Sidebar({ page, setPage, pipelineCount }) {
  return (
    <aside className="sidebar">
      <div className="sidebar-brand"><span>◆</span> Talent Lens</div>
      <nav className="sidebar-nav">
        {NAV.map(item => (
          <button key={item.id} className={page === item.id ? 'active' : ''} onClick={() => setPage(item.id)}>
            <span className="nav-icon">{item.icon}</span>{item.label}
            {item.id === 'pipeline' && <span className="nav-badge">{pipelineCount}</span>}
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">
        <p>Talent Lens</p>
        <small>Recruiting workspace</small>
      </div>
    </aside>
  )
}

function Topbar({ page, runs, switchRun, startScreening }) {
  const titles = {
    overview: ['Overview', 'A snapshot of your hiring pipeline'],
    pipeline: ['Candidate pipeline', 'Track every candidate from application to offer'],
    intake: ['New screening', 'Upload a role and resumes to generate a ranked shortlist'],
    results: ['Screening results', 'Ranked candidates from your latest screening'],
    analytics: ['Analytics', 'How candidates are progressing through your pipeline'],
  }
  const [title, subtitle] = titles[page] || ['Talent Lens', '']
  return (
    <header className="topbar-v2">
      <div><h1>{title}</h1><p>{subtitle}</p></div>
      <div className="topbar-actions">
        {runs.length > 0 && (
          <select className="run-picker" defaultValue="" onChange={e => { if (e.target.value) switchRun(Number(e.target.value)); e.target.value = '' }}>
            <option value="" disabled>Saved screenings…</option>
            {runs.map(run => <option key={run.id} value={run.id}>{run.job_title || 'Untitled role'} — {formatDate(run.created_at)}</option>)}
          </select>
        )}
        <button className="primary compact" onClick={startScreening}>＋ New screening</button>
      </div>
    </header>
  )
}

/* ---------------------------------------------------------------- */
/* Overview                                                           */
/* ---------------------------------------------------------------- */

function Overview({ pipeline, activity, runs, runsLoading, startScreening, openPipeline, switchRun }) {
  const active = pipeline.filter(c => c.stage !== 'Rejected')
  const interviewing = pipeline.filter(c => c.stage === 'Interview').length
  const offers = pipeline.filter(c => c.stage === 'Offer' || c.stage === 'Hired').length
  const rejected = pipeline.filter(c => c.stage === 'Rejected').length
  const avgScore = pipeline.length ? Math.round(pipeline.reduce((sum, c) => sum + c.score, 0) / pipeline.length) : 0

  return (
    <>
      <section className="metrics">
        <Metric label="Total candidates" value={pipeline.length} />
        <Metric label="Active in pipeline" value={active.length} />
        <Metric label="In interview" value={interviewing} />
        <Metric label="Offers extended" value={offers} />
        <Metric label="Average score" value={`${avgScore}%`} />
      </section>

      <section className="overview-grid">
        <article className="panel">
          <div className="panel-head"><h2>Pipeline funnel</h2><span>{active.length} active · {rejected} rejected</span></div>
          <Funnel pipeline={pipeline} />
        </article>

        <article className="panel">
          <div className="panel-head"><h2>Recent activity</h2></div>
          {activity.length ? (
            <ul className="activity-list">
              {activity.slice(0, 8).map(item => (
                <li key={item.id}><span className="activity-dot" /><div><p>{item.text}</p><small>{timeAgo(item.at)}</small></div></li>
              ))}
            </ul>
          ) : <p className="muted">No activity yet — run a screening to get started.</p>}
        </article>
      </section>

      <section className="panel">
        <div className="panel-head">
          <h2>Saved screenings</h2>
          <button className="text-button" onClick={openPipeline}>View full pipeline →</button>
        </div>
        {runsLoading ? <p className="muted">Loading…</p> : runs.length ? (
          <ul className="run-list">
            {runs.slice(0, 5).map(run => (
              <li key={run.id} onClick={() => switchRun(run.id)}>
                <span className="avatar">{run.candidate_count}</span>
                <div><b>{run.job_title || 'Untitled role'}</b><small>{formatDate(run.created_at)}</small></div>
                <span className="chev">→</span>
              </li>
            ))}
          </ul>
        ) : (
          <EmptyState compact title="No screenings run yet" body="Start your first screening to populate this list." action={{ label: 'Start a screening', onClick: startScreening }} />
        )}
      </section>
    </>
  )
}

function Funnel({ pipeline }) {
  const counts = STAGES.map(stage => ({ stage, count: pipeline.filter(c => c.stage === stage).length }))
  const rejectedCount = pipeline.filter(c => c.stage === 'Rejected').length
  const max = Math.max(1, ...counts.map(c => c.count))
  return (
    <div className="funnel">
      {counts.map(({ stage, count }) => (
        <div className="funnel-row" key={stage}>
          <span className="funnel-label">{stage}</span>
          <div className="funnel-track">
            <div className="funnel-fill" style={{ width: `${(count / max) * 100}%`, background: STAGE_COLOR[stage] }} />
          </div>
          <span className="funnel-count">{count}</span>
        </div>
      ))}
      <div className="funnel-row rejected">
        <span className="funnel-label">Rejected</span>
        <div className="funnel-track">
          <div className="funnel-fill" style={{ width: `${(rejectedCount / max) * 100}%`, background: STAGE_COLOR.Rejected }} />
        </div>
        <span className="funnel-count">{rejectedCount}</span>
      </div>
    </div>
  )
}

/* ---------------------------------------------------------------- */
/* Pipeline (Kanban)                                                  */
/* ---------------------------------------------------------------- */

function Pipeline({ pipeline, moveStage, openDrawer, startScreening }) {
  if (!pipeline.length) {
    return <EmptyState title="Your pipeline is empty" body="Run a screening to start adding candidates." action={{ label: 'Start a screening', onClick: startScreening }} />
  }
  return (
    <>
      <div className="kanban">
        {STAGES.map(stage => {
          const items = pipeline.filter(c => c.stage === stage).sort((a, b) => b.score - a.score)
          return (
            <div className="kanban-column" key={stage}>
              <div className="kanban-head"><span className="dot" style={{ background: STAGE_COLOR[stage] }} />{stage}<b>{items.length}</b></div>
              <div className="kanban-body">
                {items.map(candidate => (
                  <button className="kanban-card" key={candidate.id} onClick={() => openDrawer(candidate)}>
                    <span className="avatar small">{initials(candidate.name)}</span>
                    <div>
                      <b>{candidate.name}</b>
                      <small>{candidate.role}</small>
                    </div>
                    <span className="score-pill" style={{ color: decisionColor[candidate.decision] }}>{candidate.score}</span>
                  </button>
                ))}
                {!items.length && <p className="kanban-empty">No candidates</p>}
              </div>
            </div>
          )
        })}
        <div className="kanban-column rejected-column">
          <div className="kanban-head"><span className="dot" style={{ background: STAGE_COLOR.Rejected }} />Rejected<b>{pipeline.filter(c => c.stage === 'Rejected').length}</b></div>
          <div className="kanban-body">
            {pipeline.filter(c => c.stage === 'Rejected').map(candidate => (
              <button className="kanban-card muted-card" key={candidate.id} onClick={() => openDrawer(candidate)}>
                <span className="avatar small">{initials(candidate.name)}</span>
                <div><b>{candidate.name}</b><small>{candidate.role}</small></div>
                <span className="score-pill" style={{ color: decisionColor.Reject }}>{candidate.score}</span>
              </button>
            ))}
          </div>
        </div>
      </div>
    </>
  )
}

function CandidateDrawer({ candidate, close, moveStage, jd }) {
  const [email, setEmail] = useState('')
  const [emailLoading, setEmailLoading] = useState(false)
  const currentIndex = STAGES.indexOf(candidate.stage)

  async function generateEmail() {
    setEmailLoading(true); setEmail('')
    try {
      const response = await fetch('/api/interview-email', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume: { name: candidate.name, email: candidate.email }, jd: jd || { job_title: candidate.role } }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail)
      setEmail(body.email)
    } catch { setEmail('Unable to generate the email right now.') } finally { setEmailLoading(false) }
  }

  return (
    <div className="drawer-overlay" onClick={close}>
      <aside className="drawer" onClick={e => e.stopPropagation()}>
        <button className="drawer-close" onClick={close}>✕</button>
        <div className="drawer-head">
          <span className="avatar large">{initials(candidate.name)}</span>
          <h2>{candidate.name}</h2>
          <p>{candidate.role}{candidate.email ? ` · ${candidate.email}` : ''}</p>
          <div className="big-score">{candidate.score}<span>/100</span></div>
        </div>

        <h3>Stage</h3>
        <div className="stage-track">
          {STAGES.map((stage, i) => (
            <button key={stage} className={`stage-step ${i <= currentIndex && candidate.stage !== 'Rejected' ? 'done' : ''} ${candidate.stage === stage ? 'current' : ''}`}
              onClick={() => moveStage(candidate.id, stage)}>{stage}</button>
          ))}
        </div>
        <button className="reject-link" onClick={() => moveStage(candidate.id, 'Rejected')}>Mark as rejected</button>

        {(candidate.matched.length > 0 || candidate.missing.length > 0) && (
          <div className="chips">
            <Chip title="Matched" values={candidate.matched} kind="match" />
            <Chip title="Focus areas" values={candidate.missing} kind="missing" />
          </div>
        )}

        {candidate.brief && (
          <>
            <h3>Recruiter brief</h3>
            <div className="brief">{candidate.brief.replace(/###\s*/g, '')}</div>
          </>
        )}

        <h3>Interview invite</h3>
        <button className="primary compact" onClick={generateEmail} disabled={emailLoading}>{emailLoading ? 'Generating…' : 'Generate interview email'}</button>
        {email && <section className="email-preview"><pre>{email}</pre></section>}
      </aside>
    </div>
  )
}

/* ---------------------------------------------------------------- */
/* New screening intake                                               */
/* ---------------------------------------------------------------- */

function Intake({ jd, setJd, jdFile, setJdFile, resumes, addResumes, removeResume, resumeInput, analyze, loading, notice }) {
  const [dragging, setDragging] = useState(false)
  return (
    <section className="intake-grid">
      <div className="intake-side">
        <p className="eyebrow">New screening</p>
        <h2>Find the right signal, faster.</h2>
        <p>Build a consistent shortlist from resumes and role requirements, with transparent scores your team can stand behind. Results are added straight to your pipeline.</p>
        <div className="signal-row">
          <span>Structured extraction</span><span>Auditable scoring</span><span>Recruiter-ready briefs</span>
        </div>
      </div>
      <section className="intake-card">
        <div className="step"><span>01</span><div><h2>Define the role</h2><p>Paste the job description or attach a file.</p></div></div>
        <textarea value={jd} onChange={e => setJd(e.target.value)} placeholder="Paste the role overview, required skills, responsibilities, and experience level..." />
        <label className="file-control">
          <input type="file" accept=".pdf,.docx,.txt,.md" onChange={e => setJdFile(e.target.files[0] || null)} />
          Attach job description <small>{formatFileName(jdFile)}</small>
        </label>

        <div className="step"><span>02</span><div><h2>Add candidates</h2><p>Select one or more resumes to compare.</p></div></div>
        <button type="button" className={`dropzone ${dragging ? 'dragging' : ''}`} onClick={() => resumeInput.current?.click()}
          onDragOver={e => { e.preventDefault(); setDragging(true) }} onDragLeave={() => setDragging(false)}
          onDrop={e => { e.preventDefault(); setDragging(false); addResumes(e.dataTransfer.files) }}>
          <b>{dragging ? 'Drop resumes to add them' : 'Upload resumes'}</b>
          <small>Drag and drop, or click to browse — PDF, DOCX, TXT, or Markdown</small>
        </button>
        <input ref={resumeInput} className="hidden" type="file" accept=".pdf,.docx,.txt,.md" multiple onChange={e => { addResumes(e.target.files); e.target.value = '' }} />

        {resumes.length > 0 && (
          <ul className="resume-list">
            {resumes.map((file, i) => (
              <li key={`${file.name}-${file.size}`}>
                <span className="resume-name">{file.name}</span>
                <span className="resume-size">{formatBytes(file.size)}</span>
                <button type="button" className="resume-remove" onClick={() => removeResume(i)} aria-label={`Remove ${file.name}`}>✕</button>
              </li>
            ))}
          </ul>
        )}

        {notice && <p className={`notice ${notice.kind}`}>{notice.text}</p>}
        <button className="primary" disabled={loading} onClick={analyze}>
          {loading ? 'Analyzing candidates…' : `Analyze ${resumes.length || ''} candidate${resumes.length === 1 ? '' : 's'} →`}
        </button>
      </section>
    </section>
  )
}

/* ---------------------------------------------------------------- */
/* Results (per-run detail — candidates / analytics / role / exports) */
/* ---------------------------------------------------------------- */

function Results({ screening, download, notice, runs, switchRun, goToPipeline }) {
  const [activeTab, setActiveTab] = useState('Candidates')
  const [selected, setSelected] = useState(screening.results[0] || null)
  const [email, setEmail] = useState('')
  const [emailLoading, setEmailLoading] = useState(false)
  const tabs = ['Candidates', 'Score analytics', 'Role profile', 'Exports']
  const shown = useMemo(() => [...screening.results].sort((a, b) => a.rank - b.rank), [screening])

  useEffect(() => { setSelected(screening.results[0] || null); setEmail('') }, [screening])

  async function generateEmail(candidate) {
    setEmailLoading(true); setEmail('')
    try {
      const response = await fetch('/api/interview-email', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ resume: candidate.resume, jd: screening.jd }) })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail)
      setEmail(body.email)
    } catch { setEmail('Unable to generate the email right now.') } finally { setEmailLoading(false) }
  }

  return (
    <>
      <section className="results-banner">
        <div><b>{screening.jd.job_title || 'Candidate screening'}</b><span>{screening.results.length} candidates were added to your pipeline</span></div>
        <button className="secondary" onClick={goToPipeline}>View in pipeline →</button>
      </section>
      {notice && <p className={`toast ${notice.kind}`}>{notice.text}</p>}
      <section className="metrics">
        <Metric label="Candidates reviewed" value={screening.summary.total} />
        <Metric label="Average match" value={`${screening.summary.average_score}%`} />
        <Metric label="Top candidate" value={screening.summary.top_candidate} />
        <Metric label="Next round" value={screening.summary.shortlisted} />
      </section>
      {runs.length > 1 && (
        <select className="run-picker" defaultValue="" onChange={e => { if (e.target.value) switchRun(Number(e.target.value)); e.target.value = '' }}>
          <option value="" disabled>Switch to another saved screening…</option>
          {runs.map(run => <option key={run.id} value={run.id}>{run.job_title || 'Untitled role'} — {formatDate(run.created_at)}</option>)}
        </select>
      )}
      <nav className="tabs">{tabs.map(tab => <button className={tab === activeTab ? 'active' : ''} key={tab} onClick={() => setActiveTab(tab)}>{tab}</button>)}</nav>

      {activeTab === 'Candidates' && (
        <section className="candidate-layout">
          <div className="candidate-list">
            <div className="list-heading"><h2>Candidate ranking</h2><span>{shown.length} total</span></div>
            {shown.map(candidate => (
              <button key={candidate.filename} className={`candidate-row ${selected?.filename === candidate.filename ? 'selected' : ''}`} onClick={() => { setSelected(candidate); setEmail('') }}>
                <span className="rank">{candidate.rank}</span>
                <span><b>{candidate.resume.name || candidate.filename}</b><small>{candidate.resume.years_experience || 0} years experience</small></span>
                <span className="score">{candidate.scores.overall_score}<small>/100</small></span>
                <span className="decision" style={{ color: decisionColor[candidate.decision] }}>{candidate.decision}</span>
              </button>
            ))}
          </div>
          {selected && (
            <article className="detail">
              <div className="detail-header">
                <div>
                  <p className="eyebrow">Candidate profile</p>
                  <h2>{selected.resume.name || selected.filename}</h2>
                  <p>{selected.resume.email && selected.resume.email !== 'Unknown' ? selected.resume.email : 'No contact detail available'} — {selected.resume.years_experience || 0} years experience</p>
                </div>
                <div className="big-score">{selected.scores.overall_score}<span>/100</span></div>
              </div>
              {selected.scores.overall_score > 75 && (
                <section className="next-round">
                  <div><b>Ready for the next round</b><span>This candidate has met the interview threshold.</span></div>
                  <button className="primary compact" onClick={() => generateEmail(selected)} disabled={emailLoading}>{emailLoading ? 'Generating…' : 'Generate interview mail'}</button>
                </section>
              )}
              {email && <section className="email-preview"><b>Interview invitation draft</b><pre>{email}</pre></section>}
              <div className="chips">
                <Chip title="Matched" values={selected.scores.matched_skills} kind="match" />
                <Chip title="Focus areas" values={selected.scores.missing_skills} kind="missing" />
              </div>
              <h3>Score breakdown</h3>
              <div className="breakdown">
                {scoreKeys.map(([key, label]) => (
                  <div key={key}><span>{label}</span><b>{Math.round(selected.scores[key] || 0)}%</b><i><em style={{ width: `${selected.scores[key] || 0}%` }} /></i></div>
                ))}
              </div>
              <h3>Recruiter brief</h3>
              <div className="brief">{selected.brief ? selected.brief.replace(/###\s*/g, '') : 'No recruiter brief available.'}</div>
            </article>
          )}
        </section>
      )}

      {activeTab === 'Score analytics' && <RunAnalytics results={shown} />}
      {activeTab === 'Role profile' && <Role jd={screening.jd} />}
      {activeTab === 'Exports' && (
        <section className="export-card">
          <h2>Share the outcome</h2>
          <p>Export the complete screening payload, a score table, or a formatted report for your hiring team.</p>
          <div>
            <button className="secondary" onClick={() => download('csv')}>Download CSV</button>
            <button className="secondary" onClick={() => download('json')}>Download JSON</button>
            <button className="secondary" onClick={() => download('markdown')}>Download Markdown report</button>
            <button className="secondary" onClick={() => download('summary')}>Download recruiter summary</button>
            <button className="primary compact" onClick={() => download('pdf')}>Download PDF report</button>
          </div>
        </section>
      )}
    </>
  )
}

function RunAnalytics({ results }) {
  const statuses = ['Hire', 'Maybe', 'Reject'].map(name => ({ name, value: results.filter(r => r.decision === name).length }))
  const ranks = results.map(r => ({ name: r.resume.name?.split(' ')[0] || r.filename, score: r.scores.overall_score, decision: r.decision }))
  return (
    <section className="analytics">
      <ChartCard title="Candidate match scores">
        <ResponsiveContainer width="100%" height={300}>
          <BarChart data={ranks}>
            <CartesianGrid vertical={false} stroke="#e5e7eb" /><XAxis dataKey="name" /><YAxis domain={[0, 100]} /><Tooltip />
            <Bar dataKey="score" radius={[6, 6, 0, 0]}>{ranks.map(item => <Cell key={item.name} fill={decisionColor[item.decision]} />)}</Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
      <ChartCard title="Decision mix">
        <ResponsiveContainer width="100%" height={300}>
          <PieChart>
            <Pie data={statuses} dataKey="value" nameKey="name" innerRadius={70} outerRadius={102} paddingAngle={3}>
              {statuses.map(item => <Cell key={item.name} fill={decisionColor[item.name]} />)}
            </Pie>
            <Tooltip />
          </PieChart>
        </ResponsiveContainer>
        <div className="legend">{statuses.map(s => <span key={s.name}><i style={{ background: decisionColor[s.name] }} />{s.name}: {s.value}</span>)}</div>
      </ChartCard>
    </section>
  )
}

function Role({ jd }) {
  return (
    <section className="role-card">
      <p className="eyebrow">Role requirements</p>
      <h2>{jd.job_title}</h2>
      <div className="role-meta">
        <span><b>Industry</b>{jd.industry || 'Not specified'}</span>
        <span><b>Seniority</b>{jd.seniority || 'Not specified'}</span>
        <span><b>Minimum experience</b>{jd.min_years_experience || 0} years</span>
      </div>
      <h3>Weighted skills</h3>
      <div className="skill-grid">{(jd.weighted_skills || []).map(item => <div key={item.skill}><span>{item.skill}</span><b>{item.weight}/10</b></div>)}</div>
    </section>
  )
}

/* ---------------------------------------------------------------- */
/* Analytics (aggregate, whole pipeline)                              */
/* ---------------------------------------------------------------- */

function Analytics({ pipeline }) {
  const byStage = STAGES.map(stage => ({ name: stage, value: pipeline.filter(c => c.stage === stage).length }))
  const rejected = pipeline.filter(c => c.stage === 'Rejected').length
  const byRole = Object.values(pipeline.reduce((acc, c) => {
    acc[c.role] = acc[c.role] || { name: c.role, value: 0 }
    acc[c.role].value += 1
    return acc
  }, {}))
  const decisions = ['Hire', 'Maybe', 'Reject'].map(name => ({ name, value: pipeline.filter(c => c.decision === name).length }))

  return (
    <>
      <section className="panel">
        <div className="panel-head"><h2>Pipeline funnel</h2><span>{pipeline.length - rejected} active · {rejected} rejected</span></div>
        <Funnel pipeline={pipeline} />
      </section>
      <section className="analytics">
        <ChartCard title="Candidates by stage">
          <ResponsiveContainer width="100%" height={300}>
            <BarChart data={byStage}>
              <CartesianGrid vertical={false} stroke="#e5e7eb" /><XAxis dataKey="name" /><YAxis allowDecimals={false} /><Tooltip />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>{byStage.map(item => <Cell key={item.name} fill={STAGE_COLOR[item.name]} />)}</Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>
        <ChartCard title="Overall decision mix">
          <ResponsiveContainer width="100%" height={300}>
            <PieChart>
              <Pie data={decisions} dataKey="value" nameKey="name" innerRadius={70} outerRadius={102} paddingAngle={3}>
                {decisions.map(item => <Cell key={item.name} fill={decisionColor[item.name]} />)}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
          <div className="legend">{decisions.map(s => <span key={s.name}><i style={{ background: decisionColor[s.name] }} />{s.name}: {s.value}</span>)}</div>
        </ChartCard>
      </section>
      <section className="panel">
        <div className="panel-head"><h2>Open roles by candidate volume</h2></div>
        <div className="role-bars">
          {byRole.sort((a, b) => b.value - a.value).map(role => (
            <div key={role.name} className="role-bar-row">
              <span>{role.name}</span>
              <div className="funnel-track"><div className="funnel-fill" style={{ width: `${(role.value / Math.max(...byRole.map(r => r.value))) * 100}%`, background: '#3d7ff0' }} /></div>
              <b>{role.value}</b>
            </div>
          ))}
        </div>
      </section>
    </>
  )
}

/* ---------------------------------------------------------------- */
/* Shared bits                                                        */
/* ---------------------------------------------------------------- */

function Metric({ label, value }) { return <div className="metric"><span>{label}</span><b>{value}</b></div> }
function Chip({ title, values = [], kind }) {
  return (
    <div className={`chip-group ${kind}`}>
      <span>{title}</span>
      <div>{values.length ? values.map(value => <i key={value}>{value}</i>) : <small>None identified</small>}</div>
    </div>
  )
}
function ChartCard({ title, children }) { return <article className="chart-card"><h2>{title}</h2>{children}</article> }
function EmptyState({ title, body, action, compact }) {
  return (
    <div className={`empty-state ${compact ? 'compact' : ''}`}>
      <h2>{title}</h2><p>{body}</p>
      {action && <button className="primary compact" onClick={action.onClick}>{action.label}</button>}
    </div>
  )
}

function csv(results) {
  const headers = ['Rank', 'Candidate', 'Score', 'Decision', 'Years experience', 'Matched skills', 'Missing skills']
  const rows = results.map(r => [
    r.rank, r.resume.name || r.filename, r.scores.overall_score, r.decision,
    r.resume.years_experience || 0, (r.scores.matched_skills || []).join('; '), (r.scores.missing_skills || []).join('; '),
  ])
  return [headers, ...rows].map(row => row.map(value => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n')
}
