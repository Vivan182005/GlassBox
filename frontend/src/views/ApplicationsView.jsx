import React from 'react';
import { ExternalLink, Trash2, Briefcase, Star } from 'lucide-react';
import { AtsBadge, CompanyLogo } from '../components/ui/primitives';
import { ratingColor, scoreColor } from '../lib/format';

const STAGES = ['applied', 'interview', 'offer', 'rejected', 'no reply'];

export default function ApplicationsView({ applications, setApplications, goJobs }) {
  const update = (id, patch) => setApplications(list => list.map(a => (a.id === id ? { ...a, ...patch } : a)));
  const remove = (id) => setApplications(list => list.filter(a => a.id !== id));
  const counts = STAGES.map(s => [s, applications.filter(a => a.status === s).length]);

  return (
    <div className="container page">
      <div style={{ marginBottom: 22 }}>
        <div className="eyebrow">Step 03 · Your pipeline</div>
        <h2 className="h2" style={{ marginTop: 8 }}>Applications</h2>
        <p className="muted small" style={{ marginTop: 6, maxWidth: 640 }}>
          Every job you approved, with the rating and ATS score it went out with. Kept in this browser only.
        </p>
      </div>

      {applications.length === 0 ? (
        <div className="card empty">
          <Briefcase size={28} />
          <div className="h3" style={{ marginTop: 10 }}>Nothing sent yet</div>
          <p className="small" style={{ marginTop: 6 }}>Rate jobs in Jobs in India, then press Apply on the ones at 4.0 and above.</p>
          <button className="btn primary" style={{ marginTop: 14 }} onClick={goJobs}>Find jobs</button>
        </div>
      ) : (
        <>
          <div className="row wrap" style={{ gap: 26, margin: '0 4px 16px' }}>
            {counts.map(([s, n]) => <div className="stat" key={s}><b style={{ fontSize: 22 }}>{n}</b><span>{s}</span></div>)}
          </div>
          <div className="stack" style={{ gap: 10 }}>
            {applications.map(a => (
              <div key={a.id} className="job">
                <CompanyLogo name={a.company} />
                <div style={{ minWidth: 0 }}>
                  <div className="title">{a.title}</div>
                  <div className="meta">
                    <span style={{ color: 'var(--text)' }}>{a.company}</span>
                    <span>Applied {a.date}</span>
                    {a.ats_name && <AtsBadge id={a.ats_id} name={a.ats_name} small />}
                  </div>
                  <div className="row wrap small" style={{ gap: 16, marginTop: 8 }}>
                    <span className="row" style={{ gap: 4, color: ratingColor(a.rating) }}><Star size={13} fill="currentColor" />{a.rating?.toFixed(1)} rating</span>
                    {a.ats_after != null && (
                      <span>ATS <b style={{ color: scoreColor(a.ats_before) }}>{a.ats_before}</b> → <b style={{ color: scoreColor(a.ats_after) }}>{a.ats_after}</b></span>
                    )}
                  </div>
                </div>
                <div className="side">
                  <select className="input" value={a.status} onChange={e => update(a.id, { status: e.target.value })} style={{ height: 32, width: 130 }}>
                    {STAGES.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                  <div className="row" style={{ gap: 6 }}>
                    {a.url && <a className="btn sm ghost" href={a.url} target="_blank" rel="noreferrer" aria-label="Open posting"><ExternalLink size={14} /></a>}
                    <button className="btn sm ghost" onClick={() => remove(a.id)} aria-label="Remove"><Trash2 size={14} /></button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
