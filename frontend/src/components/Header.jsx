import React, { useState } from 'react';
import { Eye, Scale, Sparkles, Key } from 'lucide-react';

export default function Header({ activeTab, setActiveTab, onLoadSample, groqApiKey, setGroqApiKey }) {
  const [showKeyModal, setShowKeyModal] = useState(false);
  const [tempKey, setTempKey] = useState(groqApiKey);

  const handleSaveKey = () => {
    setGroqApiKey(tempKey.trim());
    setShowKeyModal(false);
  };

  return (
    <header style={{
      borderBottom: '1px solid var(--border-color)',
      backgroundColor: 'var(--bg-primary)',
      position: 'sticky',
      top: 0,
      zIndex: 50,
      padding: '14px 24px'
    }}>
      <div style={{
        maxWidth: '1280px',
        margin: '0 auto',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexWrap: 'wrap',
        gap: '16px'
      }}>
        {/* Brand */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <div style={{
            width: '36px',
            height: '36px',
            borderRadius: '8px',
            background: '#1f2937',
            border: '1px solid var(--border-color)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center'
          }}>
            <Eye size={20} color="#f9fafb" />
          </div>
          <div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <h1 style={{ fontSize: '1.25rem', fontWeight: 800, color: '#f9fafb', letterSpacing: '-0.02em' }}>
                GlassBox
              </h1>
              <span className="badge badge-neutral">ATS & Bias Auditor</span>
            </div>
            <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
              Transparent ATS Parsing Simulation & Explainable Hiring Bias Auditor
            </p>
          </div>
        </div>

        {/* Persistent Horizontal Pipeline Stepper (Discover -> Reality-Check -> Audit) */}
        <div style={{
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
          background: 'rgba(15, 23, 42, 0.6)',
          padding: '4px 6px',
          borderRadius: '8px',
          border: '1px solid var(--border-color)'
        }}>
          <button
            onClick={() => setActiveTab('job_discovery')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '7px 14px',
              borderRadius: '6px',
              border: activeTab === 'job_discovery' ? '1px solid var(--cyan-accent)' : '1px solid transparent',
              fontWeight: 600,
              fontSize: '0.82rem',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              background: activeTab === 'job_discovery' ? 'rgba(34, 211, 238, 0.12)' : 'transparent',
              color: activeTab === 'job_discovery' ? 'var(--cyan-accent)' : 'var(--text-secondary)'
            }}
          >
            <Sparkles size={14} color={activeTab === 'job_discovery' ? 'var(--cyan-accent)' : 'var(--text-muted)'} />
            <span>1. Discover</span>
          </button>

          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>→</span>

          <button
            onClick={() => setActiveTab('ats_checker')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '7px 14px',
              borderRadius: '6px',
              border: (activeTab === 'ats_checker' || activeTab === 'ats') ? '1px solid var(--cyan-accent)' : '1px solid transparent',
              fontWeight: 600,
              fontSize: '0.82rem',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              background: (activeTab === 'ats_checker' || activeTab === 'ats') ? 'rgba(34, 211, 238, 0.12)' : 'transparent',
              color: (activeTab === 'ats_checker' || activeTab === 'ats') ? 'var(--cyan-accent)' : 'var(--text-secondary)'
            }}
          >
            <Eye size={14} color={(activeTab === 'ats_checker' || activeTab === 'ats') ? 'var(--cyan-accent)' : 'var(--text-muted)'} />
            <span>2. Reality-Check</span>
          </button>

          <span style={{ color: 'var(--text-muted)', fontSize: '0.75rem' }}>→</span>

          <button
            onClick={() => setActiveTab('bias_auditor')}
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              padding: '7px 14px',
              borderRadius: '6px',
              border: (activeTab === 'bias_auditor' || activeTab === 'bias') ? '1px solid var(--cyan-accent)' : '1px solid transparent',
              fontWeight: 600,
              fontSize: '0.82rem',
              cursor: 'pointer',
              transition: 'all 0.2s ease',
              background: (activeTab === 'bias_auditor' || activeTab === 'bias') ? 'rgba(34, 211, 238, 0.12)' : 'transparent',
              color: (activeTab === 'bias_auditor' || activeTab === 'bias') ? 'var(--cyan-accent)' : 'var(--text-secondary)'
            }}
          >
            <Scale size={14} color={(activeTab === 'bias_auditor' || activeTab === 'bias') ? 'var(--cyan-accent)' : 'var(--text-muted)'} />
            <span>3. Audit</span>
          </button>
        </div>

        {/* Actions */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button className="btn-secondary" onClick={() => setShowKeyModal(true)}>
            <Key size={14} color={groqApiKey ? 'var(--signal-green)' : 'var(--signal-amber)'} />
            {groqApiKey ? 'Groq Key Active' : 'Groq Key'}
          </button>

          <button className="btn-secondary" onClick={onLoadSample}>
            <Sparkles size={14} color="#9ca3af" /> Load Kaggle Resume
          </button>
        </div>
      </div>

      {/* Groq API Key Modal */}
      {showKeyModal && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100vw',
          height: '100vh',
          background: 'rgba(0,0,0,0.8)',
          backdropFilter: 'blur(4px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 100
        }}>
          <div className="glass-panel" style={{ width: '90%', maxWidth: '440px', padding: '24px' }}>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, marginBottom: '8px', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Key size={18} /> Groq API Key Configuration
            </h3>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '16px' }}>
              Used for structured requirement extraction with `llama-3.3-70b-versatile`.
            </p>
            <input
              type="password"
              className="input-field"
              placeholder="gsk_..."
              value={tempKey}
              onChange={(e) => setTempKey(e.target.value)}
              style={{ marginBottom: '16px' }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button className="btn-secondary" onClick={() => setShowKeyModal(false)}>Cancel</button>
              <button className="btn-primary" onClick={handleSaveKey}>Save Key</button>
            </div>
          </div>
        </div>
      )}
    </header>
  );
}
