import { useEffect, useMemo, useRef, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

const decisionColor = { Hire: '#16826c', Maybe: '#d88918', Reject: '#c55353' }
const scoreKeys = [
  ['skill_match', 'Skills'],
  ['experience_match', 'Experience'],
  ['project_match', 'Projects'],
  ['education_match', 'Education'],
  ['certification_match', 'Certifications'],
  ['soft_skill_match', 'Soft skills'],
  ['semantic_similarity', 'Semantic'],
]

function formatFileName(file) {
  return file ? file.name : 'No file selected'
}

function formatBytes(bytes) {
  if (!bytes) return '0 KB'
  const kb = bytes / 1024
  return kb < 1024 ? `${kb.toFixed(0)} KB` : `${(kb / 1024).toFixed(1)} MB`
}

function formatDate(iso) {
  if (!iso) return ''
  try {
    return new Date(iso).toLocaleString(undefined, {
      month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit',
    })
  } catch {
    return iso
  }
}

async function readError(response, fallback) {
  try {
    const body = await response.json()
    return body.detail || fallback
  } catch {
    return fallback
  }
}

async function triggerDownload(path, payload, filename) {
  const response = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) throw new Error(await readError(response, 'The export could not be generated.'))
  const blob = await response.blob()
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

export default function App() {
  const [view, setView] = useState('welcome')
  const [jd, setJd] = useState('')
  const [jdFile, setJdFile] = useState(null)
  const [resumes, setResumes] = useState([])
  const [screening, setScreening] = useState(null)
  const [activeTab, setActiveTab] = useState('Candidates')
  const [selected, setSelected] = useState(null)
  const [loading, setLoading] = useState(false)
  const [notice, setNotice] = useState(null) // { kind: 'error' | 'success' | 'info', text }
  const [runs, setRuns] = useState([])
  const [runsLoading, setRunsLoading] = useState(true)
  const [pipelineLoading, setPipelineLoading] = useState(false)
  const resumeInput = useRef(null)

  useEffect(() => { if (screening?.results?.length) setSelected(screening.results[0]) }, [screening])
  const results = screening?.results || []
  const shown = useMemo(() => [...results].sort((a, b) => a.rank - b.rank), [results])

  useEffect(() => { refreshRuns() }, [])

  async function refreshRuns() {
    setRunsLoading(true)
    try {
      const response = await fetch('/api/runs')
      if (!response.ok) throw new Error('runs unavailable')
      setRuns(await response.json())
    } catch {
      setRuns([])
    } finally {
      setRunsLoading(false)
    }
  }

  async function loadRun(runId) {
    const response = await fetch(`/api/runs/${runId}`)
    if (!response.ok) throw new Error(await readError(response, 'That screening run could not be loaded.'))
    return response.json()
  }

  async function analyze() {
    if (!jd.trim() && !jdFile) return setNotice({ kind: 'error', text: 'Add a job description to begin.' })
    if (!resumes.length) return setNotice({ kind: 'error', text: 'Add at least one candidate resume to begin.' })
    setLoading(true)
    setNotice(null)
    const form = new FormData()
    form.append('job_description', jd)
    if (jdFile) form.append('jd_file', jdFile)
    resumes.forEach(file => form.append('resumes', file))
    try {
      const response = await fetch('/api/analyze', { method: 'POST', body: form })
      const body = await response.json().catch(() => ({}))
      if (!response.ok) throw new Error(body.detail || 'The screening run could not be completed.')
      setScreening(body)
      setView('dashboard')
      setActiveTab('Candidates')
      setNotice({ kind: 'success', text: `Screening complete — ${body.results.length} candidate${body.results.length === 1 ? '' : 's'} reviewed.` })
      refreshRuns()
    } catch (error) {
      const isNetworkError = error instanceof TypeError
      setNotice({
        kind: 'error',
        text: isNetworkError
          ? "Couldn't reach the Talent Lens backend. Make sure the API server is running."
          : error.message,
      })
    } finally {
      setLoading(false)
    }
  }

  async function openPipeline() {
    setPipelineLoading(true)
    setNotice(null)
    try {
      const response = await fetch('/api/runs')
      if (!response.ok) throw new Error('runs unavailable')
      const list = await response.json()
      setRuns(list)
      if (!list.length) {
        setNotice({ kind: 'info', text: 'No screenings yet — run your first one to build the pipeline.' })
        setView('intake')
        return
      }
      const latest = list[0]
      const body = await loadRun(latest.id)
      setScreening(body)
      setView('dashboard')
      setActiveTab('Candidates')
      setNotice({ kind: 'info', text: `Showing the most recent screening — ${latest.job_title || 'Untitled role'} (${formatDate(latest.created_at)}).` })
    } catch (error) {
      const isNetworkError = error instanceof TypeError
      setNotice({
        kind: 'error',
        text: isNetworkError
          ? "Couldn't reach the Talent Lens backend. Make sure the API server is running."
          : error.message,
      })
    } finally {
      setPipelineLoading(false)
    }
  }

  async function switchRun(runId) {
    setNotice(null)
    try {
      const body = await loadRun(runId)
      setScreening(body)
      setActiveTab('Candidates')
      setNotice({ kind: 'info', text: `Loaded screening for ${body.jd.job_title || 'Untitled role'}.` })
    } catch (error) {
      setNotice({ kind: 'error', text: error.message })
    }
  }

  function addResumes(fileList) {
    const incoming = Array.from(fileList || [])
    if (!incoming.length) return
    setResumes(prev => {
      const seen = new Set(prev.map(f => `${f.name}-${f.size}`))
      const merged = [...prev]
      for (const file of incoming) {
        const key = `${file.name}-${file.size}`
        if (!seen.has(key)) { merged.push(file); seen.add(key) }
      }
      return merged
    })
  }

  function removeResume(index) {
    setResumes(prev => prev.filter((_, i) => i !== index))
  }

  async function download(kind) {
    if (!screening) return
    try {
      if (kind === 'csv') {
        const content = csv(results)
        const blob = new Blob([content], { type: 'text/csv' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = 'talent-lens-results.csv'
        link.click()
        URL.revokeObjectURL(url)
        return
      }
      if (kind === 'json') {
        const content = JSON.stringify(screening, null, 2)
        const blob = new Blob([content], { type: 'application/json' })
        const url = URL.createObjectURL(blob)
        const link = document.createElement('a')
        link.href = url
        link.download = 'talent-lens-results.json'
        link.click()
        URL.revokeObjectURL(url)
        return
      }
      const routes = {
        markdown: ['/api/export/markdown', 'talent-lens-report.md'],
        pdf: ['/api/export/pdf', 'talent-lens-report.pdf'],
        summary: ['/api/export/recruiter-summary', 'recruiter-summary.md'],
      }
      const [path, filename] = routes[kind]
      await triggerDownload(path, { jd: screening.jd, results: screening.results }, filename)
    } catch (error) {
      setNotice({ kind: 'error', text: error.message || 'The export could not be generated.' })
    }
  }

  return (
    <main className="app-shell">
      <header className="topbar">
        <a className="brand" href="/" onClick={e => { e.preventDefault(); setView('welcome'); setScreening(null) }}>
          <span>◆</span> Talent Lens
        </a>
        <div className="topbar-note">Evidence-led candidate screening</div>
        {view !== 'welcome' && (
          <nav className="topbar-nav">
            <button className={view === 'intake' ? 'active' : ''} onClick={() => { setView('intake'); setNotice(null) }}>New screening</button>
            <button className={view === 'dashboard' ? 'active' : ''} onClick={openPipeline} disabled={pipelineLoading}>
              {pipelineLoading ? 'Loading…' : 'Pipeline'}
            </button>
          </nav>
        )}
      </header>

      {view === 'welcome' && (
        <Welcome
          start={() => { setView('intake'); setNotice(null) }}
          openPipeline={openPipeline}
          pipelineLoading={pipelineLoading}
          runs={runs}
          runsLoading={runsLoading}
        />
      )}

      {view === 'intake' && (
        <Intake
          jd={jd} setJd={setJd}
          jdFile={jdFile} setJdFile={setJdFile}
          resumes={resumes} addResumes={addResumes} removeResume={removeResume}
          resumeInput={resumeInput}
          analyze={analyze} loading={loading} notice={notice}
        />
      )}

      {view === 'dashboard' && screening && (
        <Dashboard
          screening={screening} results={shown}
          selected={selected} setSelected={setSelected}
          activeTab={activeTab} setActiveTab={setActiveTab}
          newScreening={() => { setScreening(null); setView('intake'); setNotice(null) }}
          download={download} notice={notice}
          runs={runs} switchRun={switchRun}
        />
      )}
    </main>
  )
}

function Welcome({ start, openPipeline, pipelineLoading, runs, runsLoading }) {
  const total = runs.reduce((sum, r) => sum + (r.candidate_count || 0), 0)
  const latest = runs[0]
  return (
    <section className="welcome">
      <div className="welcome-copy">
        <p className="eyebrow">Talent Lens recruiting portal</p>
        <h1>Welcome, recruiters.</h1>
        <p>Make every shortlist clearer, more consistent, and easier to defend. Talent Lens turns resumes into evidence-led hiring decisions.</p>
        <div className="welcome-actions">
          <button className="primary welcome-primary" onClick={start}>Start a screening</button>
          <button className="secondary" onClick={openPipeline} disabled={pipelineLoading}>
            {pipelineLoading ? 'Loading…' : 'Open candidate pipeline'}
          </button>
        </div>
      </div>
      <aside className="welcome-panel">
        <p className="eyebrow">Candidate pipeline</p>
        {runsLoading ? (
          <h2>Loading your screening history…</h2>
        ) : runs.length ? (
          <h2>{total} candidate{total === 1 ? '' : 's'} across {runs.length} screening{runs.length === 1 ? '' : 's'}.</h2>
        ) : (
          <h2>No screenings yet — run your first one to build a pipeline.</h2>
        )}
        <div className="mini-candidates">
          {runs.length ? runs.slice(0, 3).map(run => (
            <div key={run.id}>
              <span className="avatar">{run.candidate_count}</span>
              <p><b>{run.job_title || 'Untitled role'}</b><small>{formatDate(run.created_at)}</small></p>
            </div>
          )) : (
            <div>
              <span className="avatar">–</span>
              <p><b>No runs yet</b><small>Upload a JD and resumes to get started</small></p>
            </div>
          )}
        </div>
        {latest && <button className="text-button" onClick={openPipeline}>Open most recent screening →</button>}
      </aside>
    </section>
  )
}

function Intake({ jd, setJd, jdFile, setJdFile, resumes, addResumes, removeResume, resumeInput, analyze, loading, notice }) {
  const [dragging, setDragging] = useState(false)
  return (
    <section className="onboarding">
      <div className="hero-copy">
        <p className="eyebrow">New screening</p>
        <h1>Find the right signal, faster.</h1>
        <p>Build a consistent shortlist from resumes and role requirements, with transparent scores your team can stand behind.</p>
        <div className="signal-row">
          <span>Structured extraction</span>
          <span>Auditable scoring</span>
          <span>Recruiter-ready briefs</span>
        </div>
      </div>
      <section className="intake-card">
        <div className="step">
          <span>01</span>
          <div><h2>Define the role</h2><p>Paste the job description or attach a file.</p></div>
        </div>
        <textarea value={jd} onChange={e => setJd(e.target.value)} placeholder="Paste the role overview, required skills, responsibilities, and experience level..." />
        <label className="file-control">
          <input type="file" accept=".pdf,.docx,.txt,.md" onChange={e => setJdFile(e.target.files[0] || null)} />
          Attach job description <small>{formatFileName(jdFile)}</small>
        </label>

        <div className="step">
          <span>02</span>
          <div><h2>Add candidates</h2><p>Select one or more resumes to compare.</p></div>
        </div>
        <button
          type="button"
          className={`dropzone ${dragging ? 'dragging' : ''}`}
          onClick={() => resumeInput.current?.click()}
          onDragOver={e => { e.preventDefault(); setDragging(true) }}
          onDragLeave={() => setDragging(false)}
          onDrop={e => { e.preventDefault(); setDragging(false); addResumes(e.dataTransfer.files) }}
        >
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

function Dashboard({ screening, results, selected, setSelected, activeTab, setActiveTab, newScreening, download, notice, runs, switchRun }) {
  const [email, setEmail] = useState('')
  const [emailLoading, setEmailLoading] = useState(false)
  const tabs = ['Candidates', 'Analytics', 'Role profile', 'Exports']

  async function generateEmail(candidate) {
    setEmailLoading(true)
    setEmail('')
    try {
      const response = await fetch('/api/interview-email', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ resume: candidate.resume, jd: screening.jd }),
      })
      const body = await response.json()
      if (!response.ok) throw new Error(body.detail || 'Could not create the interview email.')
      setEmail(body.email)
    } catch {
      setEmail('Unable to generate the email right now. Please try again.')
    } finally {
      setEmailLoading(false)
    }
  }

  return (
    <>
      <section className="dashboard-hero">
        <div>
          <p className="eyebrow">Screening results</p>
          <h1>{screening.jd.job_title || 'Candidate screening'}</h1>
          <p>Review the shortlist and investigate the evidence behind every decision.</p>
        </div>
        <div className="dashboard-hero-actions">
          {runs.length > 1 && (
            <select className="run-picker" defaultValue="" onChange={e => { if (e.target.value) switchRun(Number(e.target.value)); e.target.value = '' }}>
              <option value="" disabled>Switch screening…</option>
              {runs.map(run => <option key={run.id} value={run.id}>{run.job_title || 'Untitled role'} — {formatDate(run.created_at)}</option>)}
            </select>
          )}
          <button className="secondary" onClick={newScreening}>New screening</button>
        </div>
      </section>
      {notice && <p className={`toast ${notice.kind}`}>{notice.text}</p>}
      <section className="metrics">
        <Metric label="Candidates reviewed" value={screening.summary.total} />
        <Metric label="Average match" value={`${screening.summary.average_score}%`} />
        <Metric label="Top candidate" value={screening.summary.top_candidate} />
        <Metric label="Next round" value={screening.summary.shortlisted} />
      </section>
      <nav className="tabs">
        {tabs.map(tab => <button className={tab === activeTab ? 'active' : ''} key={tab} onClick={() => setActiveTab(tab)}>{tab}</button>)}
      </nav>
      {activeTab === 'Candidates' && (
        <CandidateTab results={results} selected={selected} setSelected={setSelected} email={email} emailLoading={emailLoading} generateEmail={generateEmail} />
      )}
      {activeTab === 'Analytics' && <Analytics results={results} />}
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

function CandidateTab({ results, selected, setSelected, email, emailLoading, generateEmail }) {
  return (
    <section className="candidate-layout">
      <div className="candidate-list">
        <div className="list-heading"><h2>Candidate ranking</h2><span>{results.length} total</span></div>
        {results.map(candidate => (
          <button
            key={candidate.filename}
            className={`candidate-row ${selected?.filename === candidate.filename ? 'selected' : ''}`}
            onClick={() => setSelected(candidate)}
          >
            <span className="rank">{candidate.rank}</span>
            <span><b>{candidate.resume.name || candidate.filename}</b><small>{candidate.resume.years_experience || 0} years experience</small></span>
            <span className="score">{candidate.scores.overall_score}<small>/100</small></span>
            <span className="decision" style={{ color: decisionColor[candidate.decision] }}>{candidate.decision} — next round</span>
          </button>
        ))}
      </div>
      {selected && <CandidateDetail candidate={selected} email={email} emailLoading={emailLoading} generateEmail={generateEmail} />}
    </section>
  )
}

function CandidateDetail({ candidate, email, emailLoading, generateEmail }) {
  const { resume, scores } = candidate
  const nextRound = scores.overall_score > 75
  return (
    <article className="detail">
      <div className="detail-header">
        <div>
          <p className="eyebrow">Candidate profile</p>
          <h2>{resume.name || candidate.filename}</h2>
          <p>{resume.email && resume.email !== 'Unknown' ? resume.email : 'No contact detail available'} — {resume.years_experience || 0} years experience</p>
        </div>
        <div className="big-score">{scores.overall_score}<span>/100</span></div>
      </div>
      {nextRound && (
        <section className="next-round">
          <div><b>Ready for the next round</b><span>This candidate has met the interview threshold.</span></div>
          <button className="primary compact" onClick={() => generateEmail(candidate)} disabled={emailLoading}>
            {emailLoading ? 'Generating…' : 'Generate interview mail'}
          </button>
        </section>
      )}
      {email && <section className="email-preview"><b>Interview invitation draft</b><pre>{email}</pre></section>}
      <div className="chips">
        <Chip title="Matched" values={scores.matched_skills} kind="match" />
        <Chip title="Focus areas" values={scores.missing_skills} kind="missing" />
      </div>
      <h3>Score breakdown</h3>
      <div className="breakdown">
        {scoreKeys.map(([key, label]) => (
          <div key={key}>
            <span>{label}</span><b>{Math.round(scores[key] || 0)}%</b>
            <i><em style={{ width: `${scores[key] || 0}%` }} /></i>
          </div>
        ))}
      </div>
      <h3>Recruiter brief</h3>
      <div className="brief">{candidate.brief ? candidate.brief.replace(/###\s*/g, '') : 'No recruiter brief available.'}</div>
    </article>
  )
}

function Analytics({ results }) {
  const statuses = ['Hire', 'Maybe', 'Reject'].map(name => ({ name, value: results.filter(r => r.decision === name).length }))
  const ranks = results.map(r => ({ name: r.resume.name?.split(' ')[0] || r.filename, score: r.scores.overall_score, decision: r.decision }))
  return (
    <section className="analytics">
      <ChartCard title="Candidate match scores">
        <ResponsiveContainer width="100%" height={310}>
          <BarChart data={ranks}>
            <CartesianGrid vertical={false} stroke="#e5e7eb" />
            <XAxis dataKey="name" />
            <YAxis domain={[0, 100]} />
            <Tooltip />
            <Bar dataKey="score" radius={[6, 6, 0, 0]}>
              {ranks.map(item => <Cell key={item.name} fill={decisionColor[item.decision]} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </ChartCard>
      <ChartCard title="Decision mix">
        <ResponsiveContainer width="100%" height={310}>
          <PieChart>
            <Pie data={statuses} dataKey="value" nameKey="name" innerRadius={72} outerRadius={106} paddingAngle={3}>
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
      <div className="skill-grid">
        {(jd.weighted_skills || []).map(item => <div key={item.skill}><span>{item.skill}</span><b>{item.weight}/10</b></div>)}
      </div>
    </section>
  )
}

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

function csv(results) {
  const headers = ['Rank', 'Candidate', 'Score', 'Decision', 'Years experience', 'Matched skills', 'Missing skills']
  const rows = results.map(r => [
    r.rank, r.resume.name || r.filename, r.scores.overall_score, r.decision,
    r.resume.years_experience || 0,
    (r.scores.matched_skills || []).join('; '),
    (r.scores.missing_skills || []).join('; '),
  ])
  return [headers, ...rows].map(row => row.map(value => `"${String(value).replaceAll('"', '""')}"`).join(',')).join('\n')
}
