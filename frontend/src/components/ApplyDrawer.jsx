import React, { useEffect, useMemo, useState } from 'react';
import {
  X, ExternalLink, Check, ShieldAlert, FileText, Download, Copy, Star, ClipboardList, PenLine, BadgeCheck, Lock, AlertTriangle, ScanLine, ArrowRight,
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

// The page where the form lives, per ATS.
function applyUrl(job) {
  if (!job?.url) return null;
  if (job.ats_id === 'lever') return job.url.replace(/\/?$/, '/apply');
  if (job.ats_id === 'ashby') return job.url.replace(/\/?$/, '/application');
  return job.url;
}

export function RatingBadge({ rating, size = 'md' }) {
  if (!rating) return null;
  return (
    <span className={`rating ${size}`} style={{ color: ratingColor(rating.score), borderColor: ratingColor(rating.score) }} title={rating.label}>
      <Star size={size === 'sm' ? 12 : 14} fill="currentColor" />{rating.score.toFixed(1)}
    </span>
  );
}

function Rating({ rating }) {
  const low = rating.score < APPLY_THRESHOLD;
  return (
    <div className="card glow">
      <div className="row wrap" style={{ gap: 18, alignItems: 'flex-start' }}>
        <div style={{ textAlign: 'center', minWidth: 110 }}>
          <div className="rating-big" style={{ color: ratingColor(rating.score) }}>{rating.score.toFixed(1)}<small>/5</small></div>
          <div className="eyebrow" style={{ marginTop: 4 }}>{rating.label}</div>
        </div>
        <div style={{ flex: 1, minWidth: 220 }}>
          <p className="small" style={{ marginBottom: 12 }}>{rating.advice}</p>
          <div className="stack" style={{ gap: 8 }}>
            {rating.dimensions.map(d => (
              <div key={d.key} style={{ display: 'grid', gridTemplateColumns: '92px 1fr 30px', gap: 10, alignItems: 'center' }} title={d.detail}>
                <span className="small muted">{d.label}</span>
                <Bar value={d.score * 20} color={ratingColor(d.score)} />
                <span className="mono small" style={{ textAlign: 'right' }}>{d.score.toFixed(1)}</span>
              </div>
            ))}
          </div>
          {rating.red_flags.length > 0 && (
            <div className="stack" style={{ gap: 6, marginTop: 12 }}>
              {rating.red_flags.map(f => (
                <div key={f} className="row small" style={{ alignItems: 'flex-start', gap: 8 }}>
                  <AlertTriangle size={14} color="var(--amber)" style={{ flexShrink: 0, marginTop: 3 }} />{f}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
      {low && (
        <div className="tiny" style={{ marginTop: 14, color: 'var(--amber)' }}>
          GlassBox recommends applying only at {APPLY_THRESHOLD.toFixed(1)}+. You can still continue; your call.
        </div>
      )}
    </div>
  );
}

function TailoredResume({ tailored, onDownload, busy }) {
  const [open, setOpen] = useState(false);
  if (!tailored) {
    return (
      <div className="card">
        <div className="row"><ShieldAlert size={17} color="var(--amber)" /><b>The tailored resume couldn't be written right now.</b></div>
        <p className="small muted" style={{ marginTop: 6 }}>The AI service is busy. Close this and press Apply again in a minute; your original resume still works for the form.</p>
      </div>
    );
  }
  const { before, after } = tailored;
  return (
    <div className="card">
      <div className="card-head"><FileText size={17} /><div className="h3">1 · Your resume, tailored for this job</div></div>
      <div className="row wrap" style={{ gap: 22, marginBottom: 14 }}>
        <div className="stat"><b style={{ color: scoreColor(before.score) }}>{before.score}</b><span>ATS score now</span></div>
        <ArrowRight size={18} className="faint" />
        <div className="stat"><b style={{ color: scoreColor(after.score) }}>{after.score}</b><span>tailored ({after.verdict === 'pass' ? 'passes' : after.verdict})</span></div>
        <div className="stat"><b>{after.coverage.must_matched}/{after.coverage.must_total}</b><span>required keywords</span></div>
        <div className="spacer" />
        <div className="row" style={{ gap: 8 }}>
          <button className="btn sm" onClick={() => onDownload('pdf')} disabled={busy}><Download size={13} /> PDF</button>
          <button className="btn sm" onClick={() => onDownload('docx')} disabled={busy}><Download size={13} /> Word</button>
        </div>
      </div>
      <p className="tiny faint" style={{ marginBottom: 10 }}>
        Single column, standard headings, full links: the same scanner that X-rayed your resume re-scored this version.
        Only facts from your resume are used; anything the AI couldn't back up is listed below.
      </p>
      {tailored.do_not_claim.length > 0 && (
        <div style={{ marginBottom: 12 }}>
          <div className="eyebrow">The job asks for these, but your resume doesn't show them</div>
          <div className="row wrap" style={{ gap: 6, marginTop: 6 }}>{tailored.do_not_claim.map(t => <span key={t} className="chip sm bad">{t}</span>)}</div>
        </div>
      )}
      {tailored.fact_notes.length > 0 && (
        <div className="stack" style={{ gap: 4, marginBottom: 12 }}>
          {tailored.fact_notes.map(n => <div key={n} className="tiny row" style={{ gap: 6 }}><Lock size={12} />{n}</div>)}
        </div>
      )}
      <button className="btn sm ghost" onClick={() => setOpen(o => !o)}>{open ? 'Hide' : 'Read'} the tailored resume</button>
      {open && <pre className="paper">{tailored.text}</pre>}
    </div>
  );
}

function AnswerInput({ row, value, onChange }) {
  if (row.type === 'file') {
    return <div className="small row" style={{ gap: 6 }}><FileText size={14} />{row.value === 'cover_letter' ? 'Cover letter (below)' : 'Tailored resume PDF'}</div>;
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

function Answers({ rows, values, setValue, form }) {
  const copy = (t) => navigator.clipboard?.writeText(Array.isArray(t) ? t.join(', ') : String(t || ''));
  return (
    <div className="card">
      <div className="card-head"><ClipboardList size={17} /><div className="h3">2 · Every question on the form</div></div>
      <p className="tiny faint" style={{ marginBottom: 12 }}>
        {form.source === 'standard'
          ? (form.note || 'This ATS shows its questions after you sign in, so the usual ones are prepared.')
          : `Read from the live ${form.source[0].toUpperCase() + form.source.slice(1)} form.`}
        {' '}Answers you type are saved and reused on the next application.
      </p>
      <div className="stack" style={{ gap: 14 }}>
        {rows.map(r => {
          const v = values[r.id];
          const answered = v !== undefined && v !== null && v !== '' && !(Array.isArray(v) && !v.length);
          const st = ['needs_you', 'sensitive'].includes(r.status) && answered ? { label: 'Your answer', cls: 'good' } : (STATUS[r.status] || STATUS.needs_you);
          const missing = r.required && r.type !== 'file' && (v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length));
          return (
            <div key={r.id} className={`answer ${missing ? 'missing' : ''}`}>
              <div className="row" style={{ gap: 8, marginBottom: 6, alignItems: 'flex-start' }}>
                <b className="small" style={{ flex: 1 }}>{r.label}{r.required && <span style={{ color: 'var(--red)' }}> *</span>}</b>
                <span className={`chip sm ${st.cls}`}>{r.status === 'sensitive' && <Lock size={11} />}{st.label}</span>
                {r.type !== 'file' && v && <button className="btn sm ghost" onClick={() => copy(v)} aria-label="Copy answer"><Copy size={12} /></button>}
              </div>
              <AnswerInput row={r} value={v} onChange={val => setValue(r, val)} />
              {r.basis && r.status !== 'from_resume' && r.status !== 'file' && <div className="tiny faint" style={{ marginTop: 5 }}>{r.basis}</div>}
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function ApplyDrawer({ job, analysis, cities, savedAnswers, setSavedAnswers, onApplied, onClose, notify, goScan }) {
  const [data, setData] = useState(null);
  const [error, setError] = useState(null);
  const [values, setValues] = useState({});
  const [cover, setCover] = useState('');
  const [reviewed, setReviewed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

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

  const setValue = (row, val) => {
    setValues(v => ({ ...v, [row.id]: val }));
    // Things only the user knows are remembered for the next form.
    if (['needs_you', 'sensitive', 'saved'].includes(row.status)) setSavedAnswers(s => ({ ...s, [row.key]: val }));
  };

  const blocking = useMemo(() => (data?.answers || []).filter(r => r.required && r.type !== 'file' && (() => {
    const v = values[r.id];
    return v === undefined || v === null || v === '' || (Array.isArray(v) && !v.length);
  })()), [data, values]);

  const fileName = `${(analysis?.profile?.name || 'Resume').replace(/\s+/g, '_')}_${(job?.company || 'job').replace(/\W+/g, '_')}`;
  const download = async (ext) => {
    if (!data?.tailored) return;
    setBusy(true);
    try {
      const blob = await api.resumeFile(ext, { resume: data.tailored.resume, header: data.tailored.header, filename: fileName });
      downloadBlob(blob, `${fileName}.${ext}`);
    } catch (err) {
      notify(errorMessage(err), 'error');
    } finally {
      setBusy(false);
    }
  };

  const answersText = () => (data?.answers || [])
    .filter(r => r.type !== 'file')
    .map(r => `${r.label}\n${Array.isArray(values[r.id]) ? values[r.id].join(', ') : values[r.id] || ''}`)
    .join('\n\n') + (cover ? `\n\nCover letter\n${cover}` : '');

  const approve = async () => {
    // Open the form first: browsers only allow pop-ups straight from the click.
    const url = applyUrl(job);
    if (url) window.open(url, '_blank', 'noopener');
    navigator.clipboard?.writeText(answersText()).catch(() => {});
    if (data?.tailored) await download('pdf');
    onApplied({
      id: job.id, company: job.company, title: job.title, url: job.url, ats_id: job.ats_id, ats_name: job.ats_name,
      rating: data.rating.score, ats_before: data.tailored?.before.score ?? data.check.score, ats_after: data.tailored?.after.score ?? null,
      status: 'applied', date: new Date().toISOString().slice(0, 10),
    });
    setDone(true);
  };

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
        </div>

        <div className="drawer-body">
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
              <div className="small">Rating the job, tailoring your resume to it, reading {job?.company}'s application form and filling in what your resume already answers…</div>
            </div>
          )}

          {error && (
            <div className="card">
              <div className="row"><ShieldAlert size={18} color="var(--red)" /><b>Couldn't prepare this application</b></div>
              <p className="small muted" style={{ marginTop: 6 }}>{error}</p>
            </div>
          )}

          {data && !done && (
            <>
              <Rating rating={data.rating} />
              <TailoredResume tailored={data.tailored} onDownload={download} busy={busy} />
              <Answers rows={data.answers} values={values} setValue={setValue} form={data.form} />

              <div className="card">
                <div className="card-head"><PenLine size={17} /><div className="h3">3 · Cover letter</div></div>
                <p className="tiny faint" style={{ marginBottom: 8 }}>Written from your resume for this role. Edit freely; it's copied along with your answers.</p>
                <textarea className="input" value={cover} onChange={e => setCover(e.target.value)} style={{ minHeight: 190 }} />
              </div>

              <div className="card glow">
                <div className="card-head"><BadgeCheck size={17} /><div className="h3">4 · Approve and apply</div></div>
                {blocking.length > 0 && (
                  <div className="small" style={{ color: 'var(--red)', marginBottom: 10 }}>
                    Answer {blocking.length} required question{blocking.length > 1 ? 's' : ''} first: {blocking.map(b => b.label).join(' · ')}
                  </div>
                )}
                <label className="row small" style={{ gap: 10, alignItems: 'flex-start', cursor: 'pointer' }}>
                  <input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} style={{ marginTop: 4 }} />
                  <span>I've read the tailored resume, the answers and the cover letter, and everything in them is true.</span>
                </label>
                <button className="btn primary lg" style={{ marginTop: 14, width: '100%', justifyContent: 'center' }}
                  disabled={!reviewed || blocking.length > 0 || busy} onClick={approve}>
                  <Check size={16} /> Approve &amp; apply
                </button>
                <p className="tiny faint" style={{ marginTop: 10 }}>
                  One click opens {job?.company}'s application, downloads your tailored resume and copies every answer, ready to paste.
                  You press Submit on their page: company forms need you signed in and block automated submissions, and you stay in control of what's sent.
                </p>
              </div>
            </>
          )}

          {done && (
            <div className="card glow" style={{ textAlign: 'center', padding: '36px 22px' }}>
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
