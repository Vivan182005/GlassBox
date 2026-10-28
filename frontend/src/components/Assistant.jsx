import React, { useEffect, useRef, useState } from 'react';
import { MessageCircle, Send, Trash2, X } from 'lucide-react';
import { api, errorMessage } from '../api';
import { storage } from '../lib/format';
import { Spinner } from './ui/primitives';

// What the assistant may see: only what the app already shows this user,
// trimmed so a question stays small.
function buildContext({ view, analysis, roles, jobResults, ratings, applications, focusJob }) {
  const p = analysis?.profile;
  const ctx = { current_tab: view };
  if (p) {
    ctx.profile = {
      name: p.name, headline: p.headline, location: p.location, student: p.student,
      years_experience: p.years_experience, internship_years: p.internship_years,
      target_roles: roles?.length ? roles : p.target_roles,
      skills: (p.skills || []).map(s => (typeof s === 'string' ? s : s.name)).slice(0, 40),
      education: p.education,
      links: Object.fromEntries(['linkedin', 'github'].map(k => [k, analysis.audit?.contact?.[k]]).filter(([, v]) => v)),
    };
    ctx.resume_scan = {
      readability: analysis.readability,
      issues: (analysis.audit?.issues || []).map(i => i.title),
      weakest_ats: [...(analysis.ats_scores || [])].sort((a, b) => a.score - b.score).slice(0, 3).map(s => `${s.name}: ${s.score}`),
    };
    ctx.resume_text = (analysis.resume_text || '').slice(0, 4000);
  }
  if (jobResults?.jobs?.length) {
    ctx.jobs_on_screen = jobResults.jobs.slice(0, 10).map(j => ({
      title: j.title, company: j.company, location: j.location, fit: j.fit,
      rating: ratings?.[j.id]?.score, via: j.via || 'company career page',
    }));
  }
  if (applications?.length) ctx.applications = applications.slice(0, 10).map(a => ({ title: a.title, company: a.company, status: a.status }));
  if (focusJob) ctx.open_job = { title: focusJob.title, company: focusJob.company, location: focusJob.location };
  return ctx;
}

function suggestions(analysis, jobResults) {
  if (!analysis) return ['What does GlassBox do?', 'What makes a resume ATS-friendly?', 'How do I start?'];
  const s = ['How can I improve my resume?', 'Which roles suit my profile?'];
  if (jobResults?.jobs?.length) s.push('Which job should I apply to first?');
  else s.push('How do I find internships in Bengaluru?');
  s.push('How does the Autofill extension work?');
  return s;
}

// Replies are plain text with "-" bullets and **bold**; rendered as React
// nodes, never as HTML.
function Reply({ text }) {
  const inline = (line, key) => line.split(/(\*\*[^*]+\*\*)/g).map((part, i) =>
    part.startsWith('**') && part.endsWith('**') ? <strong key={`${key}-${i}`}>{part.slice(2, -2)}</strong> : part);
  const blocks = [];
  let list = null;
  text.split('\n').forEach((raw, i) => {
    const line = raw.trimEnd();
    if (/^\s*```/.test(line)) return;
    const bullet = line.match(/^\s*(?:[-*•]|\d+\.)\s+(.*)/);
    if (bullet) {
      if (!list) { list = []; blocks.push(<ul key={`ul-${i}`}>{list}</ul>); }
      list.push(<li key={i}>{inline(bullet[1], i)}</li>);
    } else {
      list = null;
      if (line.trim()) blocks.push(<p key={i}>{inline(line.replace(/^#+\s*/, ''), i)}</p>);
    }
  });
  return <div className="assistant-reply">{blocks}</div>;
}

export default function Assistant(props) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState(() => storage.get('gb.chat', []));
  const [draft, setDraft] = useState('');
  const [busy, setBusy] = useState(false);
  const end = useRef(null);
  const input = useRef(null);

  useEffect(() => { storage.set('gb.chat', messages.slice(-30)); }, [messages]);
  useEffect(() => { end.current?.scrollIntoView({ block: 'end' }); }, [messages, busy, open]);
  useEffect(() => { if (open) input.current?.focus(); }, [open]);

  const ask = async (text) => {
    const q = (text ?? draft).trim();
    if (!q || busy) return;
    const next = [...messages, { role: 'user', content: q.slice(0, 1500) }];
    setMessages(next);
    setDraft('');
    setBusy(true);
    try {
      const { reply } = await api.ask({ messages: next.slice(-8), context: buildContext(props) });
      setMessages(m => [...m, { role: 'assistant', content: reply }]);
    } catch (err) {
      setMessages(m => [...m, { role: 'assistant', content: errorMessage(err), error: true }]);
    } finally {
      setBusy(false);
    }
  };

  if (!open) {
    return (
      <button className="assistant-fab" onClick={() => setOpen(true)} aria-label="Ask GlassBox">
        <MessageCircle size={18} /> <span>Ask GlassBox</span>
      </button>
    );
  }

  return (
    <section className="assistant" role="dialog" aria-label="Ask GlassBox">
      <header className="assistant-head">
        <MessageCircle size={16} />
        <strong>Ask GlassBox</strong>
        <div className="spacer" />
        {messages.length > 0 && (
          <button className="btn ghost sm" onClick={() => setMessages([])} aria-label="Clear conversation" title="Clear conversation"><Trash2 size={14} /></button>
        )}
        <button className="btn ghost sm" onClick={() => setOpen(false)} aria-label="Close"><X size={16} /></button>
      </header>
      <div className="assistant-body">
        {messages.length === 0 && (
          <div className="assistant-empty">
            <p className="small muted">
              {props.analysis
                ? 'Ask about your resume, your job matches or how to apply. Answers use your scan and the jobs on screen.'
                : 'Ask anything about resumes, ATS or job hunting in India. Scan your resume first for answers about you.'}
            </p>
            <div className="assistant-suggest">
              {suggestions(props.analysis, props.jobResults).map(s => (
                <button key={s} className="chip" onClick={() => ask(s)}>{s}</button>
              ))}
            </div>
          </div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`assistant-msg ${m.role}${m.error ? ' error' : ''}`}>
            {m.role === 'assistant' ? <Reply text={m.content} /> : m.content}
          </div>
        ))}
        {busy && <div className="assistant-msg assistant"><Spinner /></div>}
        <div ref={end} />
      </div>
      <form className="assistant-input" onSubmit={(e) => { e.preventDefault(); ask(); }}>
        <textarea ref={input} className="input" rows={2} maxLength={1500} value={draft} placeholder="Ask a question…"
          onChange={(e) => setDraft(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); ask(); } }} />
        <button className="btn primary" type="submit" disabled={busy || !draft.trim()} aria-label="Send"><Send size={15} /></button>
      </form>
      <p className="assistant-note tiny faint">AI answers can be wrong. Check anything important.</p>
    </section>
  );
}
