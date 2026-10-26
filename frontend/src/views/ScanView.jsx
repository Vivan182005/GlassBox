import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  UploadCloud, FileText, ArrowRight, Check, X, Sparkles, MapPin, Briefcase, GraduationCap, RotateCcw,
  Mail, Phone, Linkedin, Github, AlertTriangle, ScanLine, Eye,
} from 'lucide-react';
import { api, errorMessage } from '../api';
import { Ring, Bar, Spinner, Chip, AddInput } from '../components/ui/primitives';
import { scoreColor, initials } from '../lib/format';

const STEPS = ['Reading layout & fonts', 'Extracting your profile', 'Running 15 ATS parser simulations', 'Writing your X-ray'];
const SEV_ORDER = { critical: 0, high: 1, medium: 2, low: 3 };

function Upload({ onAnalyzed, notify, health }) {
  const [over, setOver] = useState(false);
  const [busy, setBusy] = useState(false);
  const [step, setStep] = useState(0);
  const [pasteMode, setPasteMode] = useState(false);
  const [text, setText] = useState('');
  const inputRef = useRef(null);

  const run = useCallback(async (payload) => {
    setBusy(true);
    setStep(0);
    const timers = STEPS.map((_, i) => setTimeout(() => setStep(i), i * 900));
    try {
      const res = await api.analyze(payload);
      onAnalyzed(res);
    } catch (err) {
      notify(errorMessage(err), 'error');
    } finally {
      timers.forEach(clearTimeout);
      setBusy(false);
    }
  }, [onAnalyzed, notify]);

  const onFile = (file) => {
    if (!file) return;
    if (!/\.(pdf|docx|txt)$/i.test(file.name)) {
      notify('Upload a PDF, DOCX or TXT resume.', 'error');
      return;
    }
    run({ file });
  };

  if (busy) {
    return (
      <div className="hero">
        <div className="scanner" aria-hidden>
          <div className="line short" style={{ marginTop: 22 }} />
          <div className="line mid" />
          {Array.from({ length: 9 }).map((_, i) => <div key={i} className={`line ${i % 3 === 2 ? 'short' : ''}`} />)}
          <div className="beam" />
        </div>
        <div className="steps">
          {STEPS.map((s, i) => (
            <div key={s} className={`s ${i < step ? 'done' : i === step ? 'now' : ''}`}>
              {i < step ? <Check size={16} color="var(--lime)" /> : i === step ? <Spinner /> : <span style={{ width: 16 }} />}
              {s}
            </div>
          ))}
        </div>
      </div>
    );
  }

  const companies = health?.network?.companies || 119;
  return (
    <>
      <section className="hero">
        <div className="eyebrow">ATS reality check · built for job seekers in India</div>
        <h1 className="h1" style={{ marginTop: 18 }}>
          See your resume<br />the way the <span className="serif grad-text">machine</span> does.
        </h1>
        <p className="lede">
          Upload your resume. GlassBox reads it like Workday, Greenhouse, Lever and 12 other ATS parsers do,
          finds companies hiring in India for your keywords, and tells you whether you'd get through their ATS.
        </p>

        {!pasteMode ? (
          <div
            className={`drop ${over ? 'over' : ''}`}
            onDragOver={e => { e.preventDefault(); setOver(true); }}
            onDragLeave={() => setOver(false)}
            onDrop={e => { e.preventDefault(); setOver(false); onFile(e.dataTransfer.files?.[0]); }}
            onClick={() => inputRef.current?.click()}
            role="button"
            tabIndex={0}
            onKeyDown={e => (e.key === 'Enter' || e.key === ' ') && inputRef.current?.click()}
          >
            <div className="drop-icon"><UploadCloud size={28} /></div>
            <div className="h3">Drop your resume here</div>
            <div className="muted small" style={{ marginTop: 6 }}>PDF or DOCX, up to 8 MB. It's analysed in memory and never stored.</div>
            <div className="row" style={{ justifyContent: 'center', marginTop: 20 }}>
              <span className="btn primary"><FileText size={16} /> Choose file</span>
              <button className="btn ghost" onClick={e => { e.stopPropagation(); setPasteMode(true); }}>or paste text</button>
            </div>
            <input ref={inputRef} type="file" accept=".pdf,.docx,.txt" hidden onChange={e => onFile(e.target.files?.[0])} />
          </div>
        ) : (
          <div className="card" style={{ maxWidth: 760, margin: '36px auto 0', textAlign: 'left' }}>
            <textarea className="input" placeholder="Paste your resume text…" value={text} onChange={e => setText(e.target.value)} style={{ minHeight: 220 }} />
            <div className="row" style={{ marginTop: 12 }}>
              <button className="btn ghost" onClick={() => setPasteMode(false)}>Upload a file instead</button>
              <div className="spacer" />
              <button className="btn primary" disabled={text.trim().length < 80} onClick={() => run({ text })}>
                <ScanLine size={16} /> X-ray it
              </button>
            </div>
            <div className="tiny faint" style={{ marginTop: 8 }}>Pasted text skips the layout checks (columns, tables, icons). Upload the file for the full X-ray.</div>
          </div>
        )}

        <div className="stats-strip">
          <div className="stat"><b>{companies}</b><span>company career sites scanned live</span></div>
          <div className="stat"><b>15</b><span>ATS parsers simulated</span></div>
          <div className="stat"><b>14</b><span>Indian cities + remote</span></div>
        </div>
      </section>

      <section className="how">
        {[
          ['01', 'X-ray', 'Find out exactly what columns, tables, icons and creative headings do to your resume inside each ATS.'],
          ['02', 'Match', 'Live openings in India from company career sites, with the ATS behind each one already known.'],
          ['03', 'Pass check', 'Per-job keyword coverage, knockouts and parse survival, plus the fixes that move your score.'],
        ].map(([n, t, d]) => (
          <div className="card" key={n}>
            <div className="num">{n}</div>
            <div className="h3" style={{ marginTop: 10 }}>{t}</div>
            <p className="muted small" style={{ marginTop: 6 }}>{d}</p>
          </div>
        ))}
      </section>
    </>
  );
}

function ProfileCard({ profile, audit }) {
  const c = audit.contact || {};
  const edu = profile.education || {};
  const contactItems = [
    [Mail, 'Email', c.email], [Phone, 'Phone', c.phone], [Linkedin, 'LinkedIn', c.linkedin], [Github, 'GitHub', c.github],
  ];
  return (
    <div className="card">
      <div className="row" style={{ alignItems: 'flex-start', gap: 14 }}>
        <div className="logo fallback" style={{ width: 52, height: 52, borderRadius: '50%', fontSize: 18 }}>{initials(profile.name || 'You')}</div>
        <div style={{ minWidth: 0 }}>
          <div className="h3" style={{ fontSize: 19 }}>{profile.name || 'Name not found'}</div>
          <div className="muted small">{profile.headline || 'Role not detected'}</div>
        </div>
      </div>
      <div className="stack" style={{ gap: 8, marginTop: 16 }}>
        {profile.location && <div className="row small muted"><MapPin size={15} /> {profile.location}</div>}
        <div className="row small muted"><Briefcase size={15} /> {profile.years_experience} yrs · {profile.seniority}</div>
        {(edu.degree || edu.college) && (
          <div className="row small muted" style={{ alignItems: 'flex-start' }}>
            <GraduationCap size={15} style={{ flexShrink: 0, marginTop: 2 }} />
            <span>{[edu.degree, edu.field].filter(Boolean).join(', ')}{edu.college ? ` · ${edu.college}` : ''}{edu.graduation_year ? ` · ${edu.graduation_year}` : ''}</span>
          </div>
        )}
      </div>
      <div className="row wrap" style={{ marginTop: 14, gap: 6 }}>
        {contactItems.map(([Icon, label, val]) => (
          <span key={label} className={`chip sm ${val ? 'good' : ''}`} title={val || `${label} not found`}>
            <Icon size={12} /> {label} {val ? <Check size={12} /> : <X size={12} />}
          </span>
        ))}
      </div>
      {profile.summary && <p className="small muted" style={{ marginTop: 14 }}>{profile.summary}</p>}
      <div className="row" style={{ marginTop: 14 }}>
        <span className="badge badge-neutral">{profile.method === 'ai' ? 'AI-parsed + verified' : 'Rule-based parse'}</span>
      </div>
      {(profile.warnings || []).map(w => <div key={w} className="tiny" style={{ color: 'var(--amber)', marginTop: 8 }}>{w}</div>)}
    </div>
  );
}

function SkillsCard({ skills }) {
  const groups = {};
  for (const s of skills) (groups[s.category] = groups[s.category] || []).push(s);
  const order = Object.keys(groups).sort((a, b) => (a === 'Soft Skills') - (b === 'Soft Skills') || groups[b].length - groups[a].length);
  return (
    <div className="card">
      <div className="card-head">
        <div className="h3">Keywords on your resume</div>
        <div className="spacer" />
        <span className="badge badge-neutral">{skills.length}</span>
      </div>
      {skills.length === 0 && <div className="muted small">No recognisable skills found. That's a big problem for ATS keyword search.</div>}
      <div className="stack" style={{ gap: 12 }}>
        {order.map(cat => (
          <div key={cat}>
            <div className="eyebrow" style={{ marginBottom: 6 }}>{cat}</div>
            <div className="row wrap" style={{ gap: 6 }}>
              {groups[cat].map(s => (
                <span key={s.name} className="chip sm" title={`${s.mentions} mention(s)`}>
                  {s.name}{s.mentions > 1 && <span className="faint mono">×{s.mentions}</span>}
                </span>
              ))}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function XRay({ analysis, atsId, atsName }) {
  const [view, setView] = useState(analysis.ats_view?.ats_id === atsId ? analysis.ats_view : null);
  const [loading, setLoading] = useState(false);
  useEffect(() => {
    if (analysis.ats_view?.ats_id === atsId) {
      setView(analysis.ats_view);
      return;
    }
    let live = true;
    setLoading(true);
    api.atsView(analysis, atsId).then(v => live && setView(v)).catch(() => {}).finally(() => live && setLoading(false));
    return () => { live = false; };
  }, [analysis, atsId]);

  const original = analysis.resume_text.split('\n').filter(l => l.trim());
  const changes = view?.changes || [];
  return (
    <div className="card">
      <div className="card-head">
        <Eye size={17} />
        <div className="h3">X-ray: what {atsName} extracts</div>
        <div className="spacer" />
        {loading && <Spinner />}
      </div>
      <div className="row wrap" style={{ gap: 6, marginBottom: 12 }}>
        {changes.length === 0 && !loading && <span className="chip sm good"><Check size={12} /> Parses cleanly, nothing lost</span>}
        {[...new Set(changes.map(c => c.type))].map(t => {
          const n = changes.filter(c => c.type === t).length;
          const label = { columns: 'Columns interleaved', dropped: 'Lines dropped', icon: 'Icons stripped', header: 'Headings unrecognised' }[t] || t;
          return <span key={t} className={`chip sm ${t === 'icon' ? 'warn' : 'bad'}`}>{label}{n > 1 ? ` ×${n}` : ''}</span>;
        })}
      </div>
      <div className="xray-head"><span>Your resume (reading order)</span><span>{atsName} parser output</span></div>
      <div className="xray">
        <div>{original.slice(0, 220).map((l, i) => <div key={i} className="l">{l}</div>)}</div>
        <div>
          {(view?.lines || []).map((l, i) => (
            <div key={i} className={`l ${l.status}`}>{l.status === 'unrecognized' ? `[UNRECOGNISED SECTION] ${l.text}` : l.text}</div>
          ))}
        </div>
      </div>
      <div className="tiny faint" style={{ marginTop: 10 }}>
        Simulation based on documented and commonly observed parser behaviour. No vendor's actual parser was used.
      </div>
    </div>
  );
}

export default function ScanView({ analysis, onAnalyzed, onReset, goJobs, notify, health, roles, setRoles }) {
  const [atsId, setAtsId] = useState('workday');
  if (!analysis) return <div className="container page"><Upload onAnalyzed={onAnalyzed} notify={notify} health={health} /></div>;

  const { profile, audit, ats_scores: scores, readability } = analysis;
  const issues = [...audit.issues].sort((a, b) => SEV_ORDER[a.severity] - SEV_ORDER[b.severity]);
  const selected = scores.find(s => s.id === atsId) || scores[0];
  const best = scores[scores.length - 1];
  const worst = scores[0];
  const first = (profile.name || '').split(' ')[0];

  return (
    <div className="container page">
      <div className="row wrap" style={{ alignItems: 'flex-end', marginBottom: 26, gap: 16 }}>
        <div>
          <div className="eyebrow">Step 01 · Resume X-ray</div>
          <h2 className="h2" style={{ marginTop: 8 }}>
            {first ? `${first}, here's` : "Here's"} what the <span className="serif grad-text">machine</span> sees.
          </h2>
        </div>
        <div className="spacer" />
        <button className="btn" onClick={onReset}><RotateCcw size={15} /> Scan another</button>
        <button className="btn primary" onClick={goJobs}>Find jobs in India <ArrowRight size={16} /></button>
      </div>

      <div className="grid-main">
        <div className="stack">
          <ProfileCard profile={profile} audit={audit} />
          <div className="card">
            <div className="card-head">
              <Sparkles size={16} />
              <div className="h3">Roles to search</div>
            </div>
            <p className="tiny faint" style={{ marginBottom: 10 }}>Inferred from your resume. Edit these to steer the job search.</p>
            <div className="row wrap" style={{ gap: 6 }}>
              {roles.map(r => <Chip key={r} onRemove={() => setRoles(roles.filter(x => x !== r))}>{r}</Chip>)}
              <AddInput placeholder="+ Add a role" onAdd={r => !roles.includes(r) && setRoles([...roles, r])} />
            </div>
          </div>
          <SkillsCard skills={profile.skills || []} />
        </div>

        <div className="stack">
          <div className="card glow">
            <div className="row wrap" style={{ gap: 26, alignItems: 'center' }}>
              <Ring value={readability} size={150} label="READABILITY" />
              <div style={{ flex: 1, minWidth: 220 }}>
                <div className="h3">ATS readability</div>
                <p className="muted small" style={{ marginTop: 6 }}>
                  How much of your resume survives parsing, averaged across 15 ATS. It ranges from
                  <b style={{ color: scoreColor(worst.score) }}> {worst.score}</b> on {worst.name} to
                  <b style={{ color: scoreColor(best.score) }}> {best.score}</b> on {best.name}.
                </p>
                <div className="row wrap" style={{ gap: 6, marginTop: 12 }}>
                  <span className="chip sm">{audit.file_type?.toUpperCase()}</span>
                  {audit.pages && <span className="chip sm">{audit.pages} page{audit.pages > 1 ? 's' : ''}</span>}
                  <span className="chip sm">{audit.words} words</span>
                  <span className={`chip sm ${audit.columns ? 'bad' : 'good'}`}>{audit.columns ? 'Multi-column' : 'Single column'}</span>
                  {audit.tables > 0 && <span className="chip sm warn">{audit.tables} tables</span>}
                </div>
              </div>
            </div>
            <div className="divider" />
            <div className="eyebrow" style={{ marginBottom: 8 }}>Parse survival by ATS · click one to X-ray it</div>
            <div className="stack" style={{ gap: 2 }}>
              {scores.map(s => (
                <button key={s.id} className={`ats-row ${s.id === selected.id ? 'on' : ''}`} onClick={() => setAtsId(s.id)}>
                  <span className="small" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {s.name}{s.region === 'India' && <span className="faint tiny"> · IN</span>}
                  </span>
                  <Bar value={s.score} />
                  <span className="mono small" style={{ color: scoreColor(s.score), textAlign: 'right' }}>{s.score}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="card">
            <div className="card-head">
              <AlertTriangle size={17} />
              <div className="h3">What to fix</div>
              <div className="spacer" />
              <span className="badge badge-neutral">{issues.length} found</span>
            </div>
            {issues.length === 0 && <div className="row small" style={{ color: 'var(--lime)' }}><Check size={16} /> No structural problems found. Your resume is ATS-safe.</div>}
            {issues.map((i, idx) => (
              <div className="issue" key={idx}>
                <span className={`sev ${i.severity}`} />
                <div>
                  <div className="row wrap" style={{ gap: 8 }}>
                    <b style={{ fontWeight: 600 }}>{i.title}</b>
                    <span className="tiny faint mono">{i.severity.toUpperCase()}</span>
                  </div>
                  <div className="small muted" style={{ marginTop: 3 }}>{i.detail}</div>
                  <div className="small" style={{ marginTop: 6 }}><span style={{ color: 'var(--lime)' }}>Fix →</span> {i.fix}</div>
                </div>
              </div>
            ))}
          </div>

          <XRay analysis={analysis} atsId={selected.id} atsName={selected.name} />
        </div>
      </div>
    </div>
  );
}
