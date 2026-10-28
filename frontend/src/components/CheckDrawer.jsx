import React, { useEffect, useState } from 'react';
import { X, ExternalLink, Check, CircleDashed, XCircle, Wand2, ShieldAlert, Info, ScanLine, Copy } from 'lucide-react';
import { api, errorMessage } from '../api';
import { Ring, Bar, AtsBadge, CompanyLogo, Spinner } from './ui/primitives';
import { scoreColor, verdictLabel } from '../lib/format';

const BREAKDOWN = [
  ['keywords', 'Keyword coverage'],
  ['parsing', 'Parse survival'],
  ['experience', 'Experience'],
  ['title', 'Title alignment'],
  ['education', 'Education'],
];

function Keywords({ rows, title }) {
  if (!rows?.length) return null;
  const got = rows.filter(r => r.status !== 'missing').length;
  return (
    <div>
      <div className="row" style={{ marginBottom: 8 }}>
        <div className="eyebrow">{title}</div>
        <div className="spacer" />
        <span className="mono small" style={{ color: scoreColor((got / rows.length) * 100) }}>{got}/{rows.length}</span>
      </div>
      <div className="row wrap" style={{ gap: 6 }}>
        {rows.map(r => (
          <span key={r.term} className={`kw ${r.status}`} title={
            r.status === 'matched' ? `Found ${r.mentions}× in your experience/projects` :
            r.status === 'skills_only' ? 'Only in your skills list, never shown in use' :
            r.status === 'implied' ? `You have it (${(r.via || []).join(', ')}), but not in the job's words` : 'Not on your resume'}>
            {r.status === 'matched' ? <Check size={13} /> : r.status === 'skills_only' || r.status === 'implied' ? <CircleDashed size={13} /> : <XCircle size={13} />}
            {r.term}
          </span>
        ))}
      </div>
    </div>
  );
}

function Tailor({ analysis, result, notify }) {
  const [data, setData] = useState(null);
  const [busy, setBusy] = useState(false);
  const run = async () => {
    setBusy(true);
    try {
      setData(await api.tailor({ resume_text: analysis.resume_text, jd_text: result.jd_text, check: result }));
    } catch (err) {
      notify(errorMessage(err), 'error');
    } finally {
      setBusy(false);
    }
  };
  const copy = (t) => navigator.clipboard?.writeText(t).then(() => notify('Copied'), () => {});
  if (!data) {
    return (
      <div className="card" style={{ background: 'var(--grad-soft)' }}>
        <div className="row wrap" style={{ gap: 14 }}>
          <Wand2 size={20} />
          <div style={{ flex: 1, minWidth: 200 }}>
            <div className="h3">Tailor my resume for this job</div>
            <div className="small muted">AI rewrites your headline, summary and bullets using only facts already on your resume.</div>
          </div>
          <button className="btn primary" onClick={run} disabled={busy}>{busy ? <Spinner /> : <Wand2 size={15} />} Rewrite</button>
        </div>
      </div>
    );
  }
  return (
    <div className="card">
      <div className="card-head"><Wand2 size={17} /><div className="h3">Tailored for this job</div></div>
      <div className="stack" style={{ gap: 14 }}>
        {data.headline && (
          <div>
            <div className="eyebrow">Headline</div>
            <div className="row" style={{ marginTop: 6 }}><b style={{ flex: 1 }}>{data.headline}</b><button className="btn sm ghost" onClick={() => copy(data.headline)}><Copy size={13} /></button></div>
          </div>
        )}
        {data.summary && (
          <div>
            <div className="eyebrow">Summary</div>
            <div className="row" style={{ marginTop: 6, alignItems: 'flex-start' }}><p className="small" style={{ flex: 1 }}>{data.summary}</p><button className="btn sm ghost" onClick={() => copy(data.summary)}><Copy size={13} /></button></div>
          </div>
        )}
        {(data.bullets || []).length > 0 && (
          <div className="stack" style={{ gap: 10 }}>
            <div className="eyebrow">Bullets: before → after</div>
            {data.bullets.map((b, i) => (
              <div className="compare" key={i}>
                <div className="before">{b.original}</div>
                <div className="after">{b.rewrite}</div>
              </div>
            ))}
          </div>
        )}
        {data.skills_line && (
          <div>
            <div className="eyebrow">Skills line, ordered for this job</div>
            <div className="row" style={{ marginTop: 6 }}><code className="small mono" style={{ flex: 1 }}>{data.skills_line}</code><button className="btn sm ghost" onClick={() => copy(data.skills_line)}><Copy size={13} /></button></div>
          </div>
        )}
        {(data.do_not_claim || []).length > 0 && (
          <div>
            <div className="eyebrow">Don't claim these unless you really have them</div>
            <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>{data.do_not_claim.map(t => <span key={t} className="chip sm bad">{t}</span>)}</div>
          </div>
        )}
      </div>
    </div>
  );
}

function CustomForm({ onRun }) {
  const [company, setCompany] = useState('');
  const [title, setTitle] = useState('');
  const [jd, setJd] = useState('');
  return (
    <div className="stack">
      <p className="muted small">Found a job on LinkedIn, Naukri or a careers page? Paste it here. GlassBox detects the company's ATS and runs the same check.</p>
      <div className="grid-2">
        <input className="input" placeholder="Company (e.g. Zepto)" value={company} onChange={e => setCompany(e.target.value)} />
        <input className="input" placeholder="Job title" value={title} onChange={e => setTitle(e.target.value)} />
      </div>
      <textarea className="input" placeholder="Paste the full job description…" value={jd} onChange={e => setJd(e.target.value)} style={{ minHeight: 260 }} />
      <div className="row">
        <div className="spacer" />
        <button className="btn primary" disabled={jd.trim().length < 80} onClick={() => onRun({ company, title, jd })}>
          <ScanLine size={15} /> Check my odds
        </button>
      </div>
    </div>
  );
}

export default function CheckDrawer({ job, analysis, onClose, notify, goScan }) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [custom, setCustom] = useState(job?.custom ? null : undefined);

  const run = async (body) => {
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.check({ resume_text: analysis.resume_text, profile: analysis.profile, audit: analysis.audit, ...body }));
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    if (!analysis || !job || job.custom) return;
    run({ job_id: job.id, jd_text: job.description || null, ats_id: job.ats_id, company: job.company, job_title: job.title });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id]);

  const runCustom = ({ company, title, jd }) => {
    setCustom({ company, title });
    run({ jd_text: jd, company, job_title: title });
  };

  const head = job?.custom ? { title: custom?.title || 'Check any job', company: custom?.company } : job;
  const ats = result?.ats;

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="ATS pass check">
        <div className="drawer-head">
          <div className="row" style={{ gap: 14 }}>
            {head?.company ? <CompanyLogo domain={job?.domain} name={head.company} size={42} /> : <div className="logo fallback" style={{ width: 42, height: 42 }}><ScanLine size={18} /></div>}
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="h3" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{head?.title}</div>
              <div className="row small muted" style={{ gap: 8 }}>
                {head?.company && <span>{head.company}</span>}
                {(ats || job?.ats_name) && <AtsBadge id={ats?.id || job?.ats_id} name={ats?.name || job?.ats_name} small />}
              </div>
            </div>
            {job?.url && <a className="btn sm" href={job.url} target="_blank" rel="noreferrer">Apply <ExternalLink size={13} /></a>}
            <button className="btn sm ghost" onClick={onClose} aria-label="Close"><X size={18} /></button>
          </div>
        </div>

        <div className="drawer-body">
          {!analysis && (
            <div className="empty">
              <ScanLine size={30} />
              <div className="h3" style={{ marginTop: 12 }}>Scan your resume first</div>
              <p className="small" style={{ marginTop: 6 }}>The pass check compares this job against your resume.</p>
              <button className="btn primary" style={{ marginTop: 16 }} onClick={() => { onClose(); goScan(); }}>Upload resume</button>
            </div>
          )}

          {analysis && job?.custom && !loading && !result && <CustomForm onRun={runCustom} />}

          {loading && (
            <div className="empty">
              <div className="scanner" aria-hidden style={{ width: 140, height: 170 }}>
                {Array.from({ length: 8 }).map((_, i) => <div key={i} className={`line ${i % 3 === 2 ? 'short' : ''}`} />)}
                <div className="beam" />
              </div>
              <div className="small">Reading the job description, pulling out the recruiter's keywords, and simulating {job?.ats_name || 'the ATS'}…</div>
            </div>
          )}

          {error && (
            <div className="card" style={{ borderColor: 'rgba(255,95,109,0.4)' }}>
              <div className="row"><ShieldAlert size={18} color="var(--red)" /><b>Couldn't run the check</b></div>
              <p className="small muted" style={{ marginTop: 6 }}>{error}</p>
            </div>
          )}

          {result && (
            <>
              <div className="card glow">
                <div className="verdict">
                  <Ring value={result.score} size={156} label="PASS ODDS" />
                  <div>
                    <div className="h2" style={{ color: scoreColor(result.score) }}>{verdictLabel[result.verdict]}</div>
                    <p className="small muted" style={{ marginTop: 6 }}>
                      Simulated against <b style={{ color: 'var(--text)' }}>{ats.name}</b>
                      {result.ats_source === 'company_lookup' ? ' (detected from the company name)' : result.ats_source === 'generic' ? ' (company ATS unknown, so a generic profile is used)' : ' (read directly from the job board)'}.
                    </p>
                    <div className="stack" style={{ gap: 9, marginTop: 14 }}>
                      {BREAKDOWN.map(([k, label]) => (
                        <div key={k} style={{ display: 'grid', gridTemplateColumns: '150px 1fr 34px', gap: 10, alignItems: 'center' }}>
                          <span className="small muted">{label}</span>
                          <Bar value={result.breakdown[k]} />
                          <span className="mono small" style={{ textAlign: 'right' }}>{result.breakdown[k]}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>

              <div className="card tight row" style={{ alignItems: 'flex-start', gap: 12 }}>
                <Info size={17} style={{ flexShrink: 0, marginTop: 2 }} />
                <div className="small"><b>How {ats.name} screens: </b><span className="muted">{ats.screening}</span></div>
              </div>

              {result.knockouts.length > 0 && (
                <div className="card">
                  <div className="card-head"><ShieldAlert size={17} /><div className="h3">Knockout risks</div></div>
                  <div className="stack" style={{ gap: 8 }}>
                    {result.knockouts.map((k, i) => (
                      <div key={i} className="row small" style={{ alignItems: 'flex-start' }}>
                        <span className={`sev ${k.severity === 'info' ? 'low' : k.severity}`} style={{ marginTop: 5 }} />
                        <span className={k.severity === 'info' ? 'muted' : ''}>{k.type === 'screening_question' ? 'Likely screening question: ' : ''}{k.detail}</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <div className="card stack" style={{ gap: 18 }}>
                <div className="row wrap">
                  <div className="h3">Keyword match</div>
                  <div className="spacer" />
                  <span className="tiny faint row" style={{ gap: 12 }}>
                    <span className="row" style={{ gap: 4 }}><Check size={12} color="var(--lime)" /> shown in use</span>
                    <span className="row" style={{ gap: 4 }}><CircleDashed size={12} color="var(--amber)" /> listed only</span>
                    <span className="row" style={{ gap: 4 }}><XCircle size={12} color="var(--red)" /> missing</span>
                  </span>
                </div>
                <Keywords rows={result.keywords.must_have} title="Must-have" />
                <Keywords rows={result.keywords.nice_to_have} title="Nice-to-have" />
                <Keywords rows={result.keywords.soft_skills} title="Soft skills (rarely searched)" />
              </div>

              {result.fixes.length > 0 && (
                <div className="card">
                  <div className="card-head"><div className="h3">Do these to raise your odds</div></div>
                  <div className="stack" style={{ gap: 10 }}>
                    {result.fixes.map((f, i) => (
                      <div className="fix" key={i}>
                        <span className="n">{i + 1}</span>
                        <div>
                          <b style={{ fontWeight: 600 }}>{f.title}</b>
                          <div className="small muted" style={{ marginTop: 3 }}>{f.detail}</div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              <Tailor analysis={analysis} result={result} notify={notify} />

              <details className="card">
                <summary className="row"><span className="h3">Job description</span><div className="spacer" /><span className="tiny faint">show</span></summary>
                <pre className="small muted" style={{ whiteSpace: 'pre-wrap', fontFamily: 'var(--font)', marginTop: 12 }}>{result.jd_text}</pre>
              </details>

              <p className="tiny faint">
                This score is an estimate: GlassBox simulates documented parser behaviour and recruiter keyword screening. It is not any vendor's real score.
              </p>
            </>
          )}
        </div>
      </aside>
    </>
  );
}
