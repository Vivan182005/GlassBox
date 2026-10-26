import React from 'react';
import { ScanLine, Briefcase, Radar, Scale } from 'lucide-react';

const TABS = [
  { id: 'scan', label: 'Resume X-ray', step: '01', icon: ScanLine },
  { id: 'jobs', label: 'Jobs in India', step: '02', icon: Briefcase },
  { id: 'company', label: 'ATS Lookup', icon: Radar },
  { id: 'fairness', label: 'Fairness Lab', icon: Scale },
];

export default function Nav({ view, setView, health }) {
  const llmOn = health?.llm?.available;
  return (
    <header className="nav">
      <div className="container nav-inner">
        <button className="brand" onClick={() => setView('scan')} aria-label="GlassBox home">
          <span className="brand-mark" />
          GlassBox
        </button>
        <nav className="tabs" aria-label="Sections">
          {TABS.map(t => (
            <button key={t.id} className={`tab ${view === t.id ? 'on' : ''}`} onClick={() => setView(t.id)}>
              <t.icon size={15} />
              {t.label}
              {t.step && <span className="step">{t.step}</span>}
            </button>
          ))}
        </nav>
        <div className="spacer" />
        {health && (
          <span className="status-pill" title={llmOn ? `AI: ${health.llm.groq.model}` : 'AI keys not configured; using rule-based fallbacks'}>
            <span className={`pulse ${llmOn ? '' : 'off'}`} />
            {health.network?.companies || 0} live boards · AI {llmOn ? 'on' : 'off'}
          </span>
        )}
      </div>
    </header>
  );
}
