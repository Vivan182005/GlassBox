import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  X, ExternalLink, Check, ShieldAlert, FileText, Download, Copy, Star, ClipboardList, PenLine, BadgeCheck, Lock, AlertTriangle,
  ScanLine, ArrowRight, ArrowLeft, Undo2, Upload, FileCode2, Sparkles, Gauge,
} from 'lucide-react';
import { api, errorMessage } from '../api';
import { AtsBadge, CompanyLogo, Spinner, Bar } from './ui/primitives';
import { ratingColor, scoreColor, APPLY_THRESHOLD, downloadBlob } from '../lib/format';

const STATUS = {
  from_resume: { label: 'From your resume', cls: 'good' },
  saved: { label: 'Your saved answer', cls: 'good' },
  drafted: { label: 'AI draft: read it', cls: 'warn' },
  needs_you: { label: 'Needs you', cls: 'bad' },
  sensitive: { label: 'Only you', cls: '' },
  file: { label: 'Attached', cls: 'good' },
};

const STEPS = [
  { id: 'match', label: 'Match', icon: Gauge },
  { id: 'resume', label: 'Resume', icon: FileText },
  { id: 'questions', label: 'Questions', icon: ClipboardList },
  { id: 'cover', label: 'Cover letter', icon: PenLine },
  { id: 'approve', label: 'Approve', icon: BadgeCheck },
];

// The page where the form lives, per ATS.
function applyUrl(job) {
  if (!job?.url) return null;
  if (job.ats_id === 'lever') return job.url.replace(/\/?$/, '/apply');
  if (job.ats_id === 'ashby') return job.url.replace(/\/?$/, '/application');
  return job.url;
}

const FONT_NAMES = {
  computer_modern: 'Computer Modern (classic LaTeX)', carlito: 'Carlito (Calibri style)', helvetica: 'Helvetica / Arial', times: 'Times',
  garamond: 'EB Garamond', palatino: 'Palatino', charter: 'Charter', lato: 'Lato', source_sans: 'Source Sans', roboto: 'Roboto',
  open_sans: 'Open Sans', fira_sans: 'Fira Sans', caladea: 'Caladea (Cambria style)', montserrat: 'Montserrat', raleway: 'Raleway',
};

const isEmpty = (v) => v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length);

export function RatingBadge({ rating, size = 'md' }) {
  if (!rating) return null;
  return (
    <span className={`rating ${size}`} style={{ color: ratingColor(rating.score), borderColor: ratingColor(rating.score) }} title={rating.label}>
      <Star size={size === 'sm' ? 12 : 14} fill="currentColor" />{rating.score.toFixed(1)}
    </span>
  );
}

// Words the edit inserted, highlighted; everything else is the original.
function Inserted({ original, text }) {
  const have = new Map();
  for (const w of original.toLowerCase().match(/[\w+#.]+/g) || []) have.set(w, (have.get(w) || 0) + 1);
  return text.split(/(\s+)/).map((tok, i) => {
    const key = (tok.toLowerCase().match(/[\w+#.]+/) || [''])[0];
    if (!key || /^\s+$/.test(tok)) return tok;
    if (have.get(key)) {
      have.set(key, have.get(key) - 1);
      return tok;
    }
    return <mark key={i} className="ins">{tok}</mark>;
  });
}

function MatchStep({ rating, check }) {
  const low = rating.score < APPLY_THRESHOLD;
  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card glow">
        <div className="row wrap" style={{ gap: 18, alignItems: 'flex-start' }}>
          <div style={{ textAlign: 'center', minWidth: 110 }}>
            <div className="rating-big" style={{ color: ratingColor(rating.score) }}>{rating.score.toFixed(1)}<small>/5</small></div>
            <div className="eyebrow" style={{ marginTop: 4 }}>{rating.label}</div>
          </div>
          <div style={{ flex: 1, minWidth: 220 }}>
            <p className="small" style={{ marginBottom: 12 }}>{rating.advice}</p>
            <div className="stack" style={{ gap: 9 }}>
              {rating.dimensions.map(d => (
                <div key={d.key}>
                  <div style={{ display: 'grid', gridTemplateColumns: '92px 1fr 30px', gap: 10, alignItems: 'center' }}>
                    <span className="small muted">{d.label}</span>
                    <Bar value={d.score * 20} color={ratingColor(d.score)} />
                    <span className="mono small" style={{ textAlign: 'right' }}>{d.score.toFixed(1)}</span>
                  </div>
                  <div className="tiny faint" style={{ marginLeft: 102 }}>{d.detail}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
        {rating.red_flags.length > 0 && (
          <div className="stack" style={{ gap: 6, marginTop: 14 }}>
            {rating.red_flags.map(f => (
              <div key={f} className="row small" style={{ alignItems: 'flex-start', gap: 8 }}>
                <AlertTriangle size={14} color="var(--amber)" style={{ flexShrink: 0, marginTop: 3 }} />{f}
              </div>
            ))}
          </div>
        )}
        {low && <div className="tiny" style={{ marginTop: 14, color: 'var(--amber)' }}>GlassBox suggests applying only at {APPLY_THRESHOLD.toFixed(1)}+. You can continue anyway.</div>}
      </div>
      <div className="card tight row wrap" style={{ gap: 18 }}>
        <div className="stat"><b style={{ color: scoreColor(check.score) }}>{check.score}</b><span>ATS pass score today</span></div>
        <div className="stat"><b>{check.coverage.must_matched}/{check.coverage.must_total}</b><span>required keywords</span></div>
        <div className="stat"><b>{check.ats.name}</b><span>their ATS</span></div>
      </div>
    </div>
  );
}

function ResumeStep({ tailored, decisions, setDecision, finalResume, job, analysis, notify }) {
  const [userTex, setUserTex] = useState(null);
  const [busy, setBusy] = useState(null);
  const [renderer, setRenderer] = useState(null);
  const overleaf = useRef(null);
  const [texForOverleaf, setTexForOverleaf] = useState('');

  if (!tailored) {
    return (
      <div className="card">
        <div className="row"><ShieldAlert size={17} color="var(--amber)" /><b>The tailored resume couldn't be written right now.</b></div>
        <p className="small muted" style={{ marginTop: 6 }}>The AI service is busy. Close this and press Apply again in a minute; your original resume still works for the form.</p>
      </div>
    );
  }
  const { before, after } = tailored;
  const changes = [];
  ['experience', 'projects'].forEach(sec => (tailored.resume[sec] || []).forEach((it, i) => (it.bullets || []).forEach((b, j) => {
    if (b.text !== b.original) changes.push({ id: `${sec}:${i}:${j}`, where: sec === 'experience' ? `${it.company}` : it.name, b });
  })));
  const skillChanges = (tailored.resume.skills || []).map((g, i) => ({ id: `skills:${i}`, g }))
    .filter(({ g }) => g.original && JSON.stringify(g.items) !== JSON.stringify(g.original));
  const fileName = `${(analysis?.profile?.name || 'Resume').replace(/\s+/g, '_')}_${(job?.company || 'job').replace(/\W+/g, '_')}`;
  const body = () => ({
    resume: finalResume, header: tailored.header, style: tailored.style, plan: tailored.plan,
    contact: analysis?.audit?.contact || {}, filename: fileName, user_tex: userTex,
  });

  const getTex = async () => api.resumeTex(body());
  const downloadTex = async () => {
    setBusy('tex');
    try {
      const res = await getTex();
      downloadBlob(new Blob([res.tex], { type: 'application/x-tex' }), res.filename);
      res.notes?.forEach(n => notify(n));
    } catch (err) { notify(errorMessage(err), 'error'); } finally { setBusy(null); }
  };
  const openOverleaf = async () => {
    setBusy('overleaf');
    try {
      const res = await getTex();
      setTexForOverleaf(res.tex);
      setTimeout(() => overleaf.current?.submit(), 0);
    } catch (err) { notify(errorMessage(err), 'error'); } finally { setBusy(null); }
  };
  const download = async (ext) => {
    setBusy(ext);
    try {
      const { blob, headers } = await api.resumeFileWithHeaders(ext, body());
      if (ext === 'pdf') setRenderer(headers['x-resume-renderer'] || 'basic');
      downloadBlob(blob, `${fileName}.${ext}`);
    } catch (err) { notify(errorMessage(err), 'error'); } finally { setBusy(null); }
  };
  const onTexFile = (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    f.text().then(t => {
      if (!t.includes('\\begin{document}')) return notify("That doesn't look like a LaTeX resume (.tex).", 'error');
      setUserTex(t);
      notify('Using your own .tex: only the accepted edits are swapped in.');
    });
  };
  const accepted = changes.filter(c => decisions[c.id] !== false).length + skillChanges.filter(c => decisions[c.id] !== false).length;

  return (
    <div className="stack" style={{ gap: 16 }}>
      <div className="card">
        <div className="row wrap" style={{ gap: 22 }}>
          <div className="stat"><b style={{ color: scoreColor(before.score) }}>{before.score}</b><span>ATS score now</span></div>
          <ArrowRight size={18} className="faint" />
          <div className="stat"><b style={{ color: scoreColor(after.score) }}>{after.score}</b><span>with every edit kept</span></div>
          <div className="stat"><b>{after.coverage.must_matched}/{after.coverage.must_total}</b><span>required keywords</span></div>
        </div>
        <p className="small muted" style={{ marginTop: 12 }}>
          Your resume stays yours: same sections, same order, same wording. GlassBox only inserts the job's words where a line already
          shows that work (SQL next to PostgreSQL, never a tool you didn't use). Keep or undo each edit below.
        </p>
      </div>

      {changes.length + skillChanges.length === 0 ? (
        <div className="card small muted">No edits needed: your resume already uses this job's wording wherever it truthfully can.</div>
      ) : (
        <div className="card">
          <div className="card-head"><Sparkles size={17} /><div className="h3">{accepted} of {changes.length + skillChanges.length} edits kept</div></div>
          <div className="stack" style={{ gap: 12 }}>
            {changes.map(({ id, where, b }) => {
              const on = decisions[id] !== false;
              return (
                <div key={id} className={`edit ${on ? 'on' : 'off'}`}>
                  <div className="row" style={{ gap: 8, marginBottom: 6 }}>
                    <span className="tiny faint" style={{ flex: 1 }}>{where}{b.keywords?.length ? ` · adds ${b.keywords.join(', ')}` : ''}</span>
                    <button className={`btn sm ${on ? 'ghost' : ''}`} onClick={() => setDecision(id, !on)}>
                      {on ? <><Undo2 size={13} /> Undo</> : <><Check size={13} /> Keep edit</>}
                    </button>
                  </div>
                  <div className="small">{on ? <Inserted original={b.original} text={b.text} /> : b.original}</div>
                </div>
              );
            })}
            {skillChanges.map(({ id, g }) => {
              const on = decisions[id] !== false;
              const added = g.items.filter(x => !g.original.includes(x));
              return (
                <div key={id} className={`edit ${on ? 'on' : 'off'}`}>
                  <div className="row" style={{ gap: 8, marginBottom: 6 }}>
                    <span className="tiny faint" style={{ flex: 1 }}>Skills · {g.group}{added.length ? ` · adds ${added.join(', ')}` : ' · reordered for this job'}</span>
                    <button className={`btn sm ${on ? 'ghost' : ''}`} onClick={() => setDecision(id, !on)}>
                      {on ? <><Undo2 size={13} /> Undo</> : <><Check size={13} /> Keep edit</>}
                    </button>
                  </div>
                  <div className="small">
                    <b>{g.group}:</b> {(on ? g.items : g.original).map((x, i) => (
                      <span key={x}>{i ? ', ' : ''}{on && added.includes(x) ? <mark className="ins">{x}</mark> : x}</span>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {tailored.do_not_claim.length > 0 && (
        <div className="card tight">
          <div className="eyebrow">The job asks for these; your resume doesn't show them, so they're not added</div>
          <div className="row wrap" style={{ gap: 6, marginTop: 8 }}>{tailored.do_not_claim.map(t => <span key={t} className="chip sm bad">{t}</span>)}</div>
        </div>
      )}

      <div className="card">
        <div className="card-head"><FileCode2 size={17} /><div className="h3">Get it in your own style</div></div>
        <p className="small muted" style={{ marginBottom: 12 }}>
          {userTex
            ? 'Using the .tex you uploaded: your exact template, with only the kept edits swapped in.'
            : `Typeset like your original: ${FONT_NAMES[tailored.style?.family] || 'the same font'}, ${tailored.style?.paper === 'a4' ? 'A4' : 'Letter'}, same colours, headings and bullet style. For a pixel-exact match, upload your Overleaf source.`}
        </p>
        <div className="row wrap" style={{ gap: 8 }}>
          <button className="btn primary" onClick={openOverleaf} disabled={!!busy}>{busy === 'overleaf' ? <Spinner /> : <ExternalLink size={14} />} Open in Overleaf</button>
          <button className="btn" onClick={() => download('pdf')} disabled={!!busy}>{busy === 'pdf' ? <Spinner /> : <Download size={14} />} PDF</button>
          <button className="btn" onClick={downloadTex} disabled={!!busy}>{busy === 'tex' ? <Spinner /> : <Download size={14} />} .tex</button>
          <button className="btn ghost" onClick={() => download('docx')} disabled={!!busy}><Download size={14} /> Word</button>
          <label className="btn ghost" style={{ cursor: 'pointer' }}>
            <Upload size={14} /> {userTex ? 'Replace my .tex' : 'Use my .tex'}
            <input type="file" accept=".tex,text/x-tex,text/plain" onChange={onTexFile} style={{ display: 'none' }} />
          </label>
        </div>
        {renderer === 'basic' && (
          <p className="tiny" style={{ marginTop: 10, color: 'var(--amber)' }}>
            This PDF is the plain ATS-safe version: the server has no LaTeX engine yet. "Open in Overleaf" compiles the styled one in one click.
          </p>
        )}
        <form ref={overleaf} action="https://www.overleaf.com/docs" method="post" target="_blank" style={{ display: 'none' }}>
          <input type="hidden" name="snip" value={texForOverleaf} readOnly />
          <input type="hidden" name="snip_name" value={`${fileName}.tex`} readOnly />
          <input type="hidden" name="engine" value="pdflatex" readOnly />
        </form>
      </div>
    </div>
  );
}

function AnswerInput({ row, value, onChange }) {
  if (row.type === 'file') {
    return <div className="small row" style={{ gap: 6 }}><FileText size={14} />{row.value === 'cover_letter' ? 'Cover letter (next step)' : 'Your tailored resume PDF'}</div>;
  }
  if (row.options?.length) {
    if (row.type === 'multiselect') {
      const list = Array.isArray(value) ? value : value ? [value] : [];
      return (
        <div className="row wrap" style={{ gap: 6 }}>
          {row.options.map(o => (
            <button key={o} type="button" className={`chip sm ${list.includes(o) ? 'on' : ''}`}
              onClick={() => onChange(list.includes(o) ? list.filter(x => x !== o) : [...list, o])}>{o}</button>
          ))}
        </div>
      );
    }
    if (row.options.length <= 4) {
      return (
        <div className="row wrap" style={{ gap: 6 }}>
          {row.options.map(o => (
            <button key={o} type="button" className={`chip ${value === o ? 'on' : ''}`} onClick={() => onChange(value === o ? '' : o)}>{o}</button>
          ))}
        </div>
      );
    }
    return (
      <select className="input" value={value || ''} onChange={e => onChange(e.target.value)} style={{ height: 36 }}>
        <option value="">{row.required ? 'Choose…' : 'Leave blank'}</option>
        {row.options.map(o => <option key={o} value={o}>{o}</option>)}
      </select>
    );
  }
  if (row.type === 'textarea' || (typeof value === 'string' && value.length > 90)) {
    return <textarea className="input" value={value || ''} onChange={e => onChange(e.target.value)} style={{ minHeight: 110 }} />;
  }
  return <input className="input" value={value || ''} onChange={e => onChange(e.target.value)} style={{ height: 36 }} placeholder={row.status === 'needs_you' ? 'Your answer' : ''} />;
}

function QuestionsStep({ rows, values, setValue, form }) {
  const copy = (t) => navigator.clipboard?.writeText(Array.isArray(t) ? t.join(', ') : String(t || ''));
  const todo = rows.filter(r => ['needs_you', 'sensitive', 'drafted'].includes(r.status));
  const done = rows.filter(r => !todo.includes(r));
  const Row = (r) => {
    const v = values[r.id];
    const answered = !isEmpty(v);
    const st = ['needs_you', 'sensitive'].includes(r.status) && answered ? { label: 'Your answer', cls: 'good' } : (STATUS[r.status] || STATUS.needs_you);
    const missing = r.required && r.type !== 'file' && !answered;
    return (
      <div key={r.id} className={`answer ${missing ? 'missing' : ''}`}>
        <div className="row" style={{ gap: 8, marginBottom: 6, alignItems: 'flex-start' }}>
          <b className="small" style={{ flex: 1 }}>{r.label}{r.required && <span style={{ color: 'var(--red)' }}> *</span>}</b>
          <span className={`chip sm ${st.cls}`}>{r.status === 'sensitive' && !answered && <Lock size={11} />}{st.label}</span>
          {r.type !== 'file' && answered && <button className="btn sm ghost" onClick={() => copy(v)} aria-label="Copy answer"><Copy size={12} /></button>}
        </div>
        <AnswerInput row={r} value={v} onChange={val => setValue(r, val)} />
        {r.basis && r.status !== 'from_resume' && r.status !== 'file' && <div className="tiny faint" style={{ marginTop: 5 }}>{r.basis}</div>}
      </div>
    );
  };
  return (
    <div className="stack" style={{ gap: 16 }}>
      <p className="tiny faint">
        {form.source === 'standard'
          ? (form.note || 'This ATS shows its questions after you sign in, so the usual ones are prepared.')
          : `Read from ${form.source[0].toUpperCase() + form.source.slice(1)}'s live form.`}
        {' '}What you type here is saved and pre-filled on your next application.
      </p>
      {todo.length > 0 && (
        <div className="card">
          <div className="card-head"><div className="h3">Your turn ({todo.length})</div></div>
          <div className="stack" style={{ gap: 12 }}>{todo.map(Row)}</div>
        </div>
      )}
      <details className="card" open={todo.length === 0}>
        <summary className="row"><span className="h3">Filled from your resume ({done.length})</span><div className="spacer" /><span className="tiny faint">review</span></summary>
        <div className="stack" style={{ gap: 12, marginTop: 14 }}>{done.map(Row)}</div>
      </details>
    </div>
  );
}

export default function ApplyDrawer({ job, analysis, cities, savedAnswers, setSavedAnswers, onApplied, onClose, notify, goScan }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [values, setValues] = useState({});
  const [cover, setCover] = useState('');
  const [decisions, setDecisions] = useState({});
  const [step, setStep] = useState(0);
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);
  const bodyRef = useRef(null);

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose();
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  useEffect(() => {
    if (!analysis || !job) return;
    let cancelled = false;
    setData(null);
    setError(null);
    setStep(0);
    api.prepareApplication({
      resume_text: analysis.resume_text, profile: analysis.profile, audit: analysis.audit,
      job, cities, saved_answers: savedAnswers,
    }).then(res => {
      if (cancelled) return;
      setData(res);
      setValues(Object.fromEntries(res.answers.map(a => [a.id, a.value])));
      setCover(res.tailored?.cover_letter || '');
    }).catch(err => !cancelled && setError(errorMessage(err)));
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [job?.id]);

  useEffect(() => { bodyRef.current?.closest('.drawer')?.scrollTo({ top: 0, behavior: 'smooth' }); }, [step]);

  const setValue = (row, val) => {
    setValues(v => ({ ...v, [row.id]: val }));
    // Things only the user knows are remembered for the next form.
    if (['needs_you', 'sensitive', 'saved'].includes(row.status)) setSavedAnswers(s => ({ ...s, [row.key]: val }));
  };

  // The resume with each edit kept or undone.
  const finalResume = useMemo(() => {
    const r = data?.tailored?.resume;
    if (!r) return null;
    const copy = JSON.parse(JSON.stringify(r));
    ['experience', 'projects'].forEach(sec => (copy[sec] || []).forEach((it, i) => (it.bullets || []).forEach((b, j) => {
      if (decisions[`${sec}:${i}:${j}`] === false) b.text = b.original;
    })));
    (copy.skills || []).forEach((g, i) => { if (decisions[`skills:${i}`] === false && g.original) g.items = g.original; });
    return copy;
  }, [data, decisions]);

  const blocking = useMemo(() => (data?.answers || []).filter(r => r.required && r.type !== 'file' && isEmpty(values[r.id])), [data, values]);
  const fileName = `${(analysis?.profile?.name || 'Resume').replace(/\s+/g, '_')}_${(job?.company || 'job').replace(/\W+/g, '_')}`;

  const answersText = () => (data?.answers || [])
    .filter(r => r.type !== 'file')
    .map(r => `${r.label}\n${Array.isArray(values[r.id]) ? values[r.id].join(', ') : values[r.id] || ''}`)
    .join('\n\n') + (cover ? `\n\nCover letter\n${cover}` : '');

  const approve = async () => {
    // Open the form first: browsers only allow pop-ups straight from the click.
    const url = applyUrl(job);
    if (url) window.open(url, '_blank', 'noopener');
    navigator.clipboard?.writeText(answersText()).catch(() => {});
    setBusy(true);
    try {
      if (finalResume) {
        const { blob } = await api.resumeFileWithHeaders('pdf', {
          resume: finalResume, header: data.tailored.header, style: data.tailored.style, plan: data.tailored.plan,
          contact: analysis?.audit?.contact || {}, filename: fileName,
        });
        downloadBlob(blob, `${fileName}.pdf`);
      }
    } catch (err) {
      notify(errorMessage(err), 'error');
    } finally {
      setBusy(false);
    }
    onApplied({
      id: job.id, company: job.company, title: job.title, url: job.url, ats_id: job.ats_id, ats_name: job.ats_name,
      rating: data.rating.score, ats_before: data.tailored?.before.score ?? data.check.score, ats_after: data.tailored?.after.score ?? null,
      status: 'applied', date: new Date().toISOString().slice(0, 10),
    });
    setDone(true);
  };

  // Questions only count as done once every required one is answered.
  const stepDone = (i) => (i === 2 ? !!data && blocking.length === 0 && i < step : i < step) || (i === 4 && done);
  const canNext = step < STEPS.length - 1 && !(step === 2 && blocking.length > 0);

  return (
    <>
      <div className="scrim" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-label="Apply">
        <div className="drawer-head">
          <div className="row" style={{ gap: 14 }}>
            <CompanyLogo domain={job?.domain} name={job?.company} size={42} />
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="h3" style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{job?.title}</div>
              <div className="row small muted" style={{ gap: 8 }}>
                <span>{job?.company}</span>
                {job?.ats_name && <AtsBadge id={job.ats_id} name={job.ats_name} small />}
                {data && <RatingBadge rating={data.rating} size="sm" />}
              </div>
            </div>
            {job?.url && <a className="btn sm ghost" href={job.url} target="_blank" rel="noreferrer" aria-label="Open posting"><ExternalLink size={14} /></a>}
            <button className="btn sm ghost" onClick={onClose} aria-label="Close"><X size={18} /></button>
          </div>
          {data && !done && (
            <nav className="stepper" aria-label="Application steps">
              {STEPS.map((s, i) => (
                <button key={s.id} className={`step ${i === step ? 'on' : ''} ${stepDone(i) ? 'done' : ''}`} onClick={() => setStep(i)}>
                  <span className="dot">{stepDone(i) && i !== step ? <Check size={11} /> : i === 2 && i < step && blocking.length ? '!' : i + 1}</span>
                  <span className="lbl">{s.label}</span>
                </button>
              ))}
              <div className="progress"><i style={{ width: `${(step / (STEPS.length - 1)) * 100}%` }} /></div>
            </nav>
          )}
        </div>

        <div className="drawer-body" ref={bodyRef}>
          {!analysis && (
            <div className="empty">
              <ScanLine size={30} />
              <div className="h3" style={{ marginTop: 12 }}>Scan your resume first</div>
              <button className="btn primary" style={{ marginTop: 16 }} onClick={() => { onClose(); goScan(); }}>Upload resume</button>
            </div>
          )}

          {analysis && !data && !error && (
            <div className="empty">
              <div className="scanner" aria-hidden style={{ width: 140, height: 170 }}>
                {Array.from({ length: 8 }).map((_, i) => <div key={i} className={`line ${i % 3 === 2 ? 'short' : ''}`} />)}
                <div className="beam" />
              </div>
              <div className="small">Rating the job, finding the edits your resume needs, reading {job?.company}'s application form and filling in what your resume answers…</div>
            </div>
          )}

          {error && (
            <div className="card">
              <div className="row"><ShieldAlert size={18} color="var(--red)" /><b>Couldn't prepare this application</b></div>
              <p className="small muted" style={{ marginTop: 6 }}>{error}</p>
            </div>
          )}

          {data && !done && (
            <div className="step-pane" key={step}>
              {step === 0 && <MatchStep rating={data.rating} check={data.check} />}
              {step === 1 && (
                <ResumeStep tailored={data.tailored} decisions={decisions} setDecision={(id, v) => setDecisions(d => ({ ...d, [id]: v }))}
                  finalResume={finalResume} job={job} analysis={analysis} notify={notify} />
              )}
              {step === 2 && <QuestionsStep rows={data.answers} values={values} setValue={setValue} form={data.form} />}
              {step === 3 && (
                <div className="card">
                  <div className="card-head"><PenLine size={17} /><div className="h3">Cover letter</div></div>
                  <p className="tiny faint" style={{ marginBottom: 8 }}>Written from your resume for this role. Edit freely; it's copied with your answers.</p>
                  <textarea className="input" value={cover} onChange={e => setCover(e.target.value)} style={{ minHeight: 260 }} />
                  <div className="tiny faint" style={{ marginTop: 6 }}>{(cover.match(/\S+/g) || []).length} words</div>
                </div>
              )}
              {step === 4 && (
                <div className="card glow">
                  <div className="card-head"><BadgeCheck size={17} /><div className="h3">Review and approve</div></div>
                  <ul className="checklist">
                    <li className={data.rating.score >= APPLY_THRESHOLD ? 'ok' : 'warn'}>Rated {data.rating.score.toFixed(1)}/5 ({data.rating.label})</li>
                    {data.tailored && <li className="ok">Resume tailored: ATS {data.tailored.before.score} → {data.tailored.after.score}, {Object.values(decisions).filter(v => v === false).length} edit(s) undone</li>}
                    <li className={blocking.length ? 'bad' : 'ok'}>
                      {blocking.length ? `${blocking.length} required question(s) still need you` : `All ${data.answers.length} form questions answered`}
                      {blocking.length > 0 && <button className="btn sm ghost" onClick={() => setStep(2)}>Answer them</button>}
                    </li>
                    <li className={cover ? 'ok' : 'warn'}>{cover ? 'Cover letter ready' : 'No cover letter'}</li>
                  </ul>
                  <label className="row small" style={{ gap: 10, alignItems: 'flex-start', cursor: 'pointer', marginTop: 14 }}>
                    <input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} style={{ marginTop: 4 }} />
                    <span>I've read the resume, the answers and the cover letter, and everything in them is true.</span>
                  </label>
                  <button className="btn primary lg" style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}
                    disabled={!reviewed || blocking.length > 0 || busy} onClick={approve}>
                    {busy ? <Spinner /> : <Check size={16} />} Approve &amp; apply
                  </button>
                  <p className="tiny faint" style={{ marginTop: 10 }}>
                    One click opens {job?.company}'s application, downloads your resume and copies every answer, ready to paste.
                    You press Submit on their page: company forms need you signed in and block automated submissions.
                  </p>
                </div>
              )}
              <div className="row step-nav">
                {step > 0 && <button className="btn ghost" onClick={() => setStep(s => s - 1)}><ArrowLeft size={14} /> Back</button>}
                <div className="spacer" />
                {canNext && <button className="btn primary" onClick={() => setStep(s => s + 1)}>{STEPS[step + 1].label} <ArrowRight size={14} /></button>}
                {step === 2 && blocking.length > 0 && <span className="tiny" style={{ color: 'var(--red)' }}>Answer the {blocking.length} required question(s) to continue</span>}
              </div>
            </div>
          )}

          {done && (
            <div className="card glow step-pane" style={{ textAlign: 'center', padding: '36px 22px' }}>
              <BadgeCheck size={34} color="var(--lime)" />
              <div className="h2" style={{ marginTop: 10 }}>Ready to submit</div>
              <p className="small muted" style={{ marginTop: 8, maxWidth: 460, marginInline: 'auto' }}>
                {job?.company}'s form is open in a new tab. Upload <b>{fileName}.pdf</b> from your downloads, paste the answers
                (they're on your clipboard), and press Submit. It's saved under Applications.
              </p>
              <div className="row" style={{ gap: 8, justifyContent: 'center', marginTop: 16 }}>
                <button className="btn" onClick={() => navigator.clipboard?.writeText(answersText()).then(() => notify('Answers copied'))}><Copy size={14} /> Copy answers again</button>
                {applyUrl(job) && <a className="btn primary" href={applyUrl(job)} target="_blank" rel="noreferrer">Open the form <ExternalLink size={13} /></a>}
              </div>
            </div>
          )}
        </div>
      </aside>
    </>
  );
}
