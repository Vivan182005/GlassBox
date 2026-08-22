import React, { useState, useEffect } from 'react';
import { Building2, AlertTriangle, CheckCircle, ArrowRight, Layers, Cpu, Sparkles, RefreshCw, ChevronDown, ChevronUp, FileText, Upload, X, Link } from 'lucide-react';
import axios from 'axios';

export default function ATSChecker({
  resumeText,
  setResumeText,
  jdText,
  setJdText,
  careersUrl,
  setCareersUrl,
  companyName,
  setCompanyName,
  detectedAts,
  setDetectedAts,
  parsedData,
  setParsedData,
  matchData,
  setMatchData,
  groqApiKey,
  onHandoffToAudit,
  autoRunAtsCheck,
  setAutoRunAtsCheck
}) {
  const [loadingParse, setLoadingParse] = useState(false);
  const [loadingMatch, setLoadingMatch] = useState(false);
  const [loadingCompany, setLoadingCompany] = useState(false);
  const [batchData, setBatchData] = useState(null);
  const [loadingBatch, setLoadingBatch] = useState(false);
  const [fileObject, setFileObject] = useState(null);

  // UI state
  const [showUrlOverride, setShowUrlOverride] = useState(false);
  const [showRawDiff, setShowRawDiff] = useState(false);
  const [showBatchMatrix, setShowBatchMatrix] = useState(false);

  useEffect(() => {
    if (autoRunAtsCheck) {
      handleSimulateAndMatch();
      if (setAutoRunAtsCheck) setAutoRunAtsCheck(false);
    }
  }, [autoRunAtsCheck]);

  // Handle Company Name lookup
  const handleCompanyLookup = async (name) => {
    setCompanyName(name);
    if (!name.trim()) {
      setDetectedAts(null);
      return;
    }
    setLoadingCompany(true);
    try {
      const res = await axios.post('/api/ats/detect-company', {
        company_name: name,
        groq_api_key: groqApiKey
      });
      setDetectedAts(res.data);
    } catch (err) {
      console.error("Company ATS lookup failed", err);
    } finally {
      setLoadingCompany(false);
    }
  };

  // Handle URL lookup
  const handleUrlChange = async (url) => {
    setCareersUrl(url);
    if (!url.trim()) return;
    try {
      const res = await axios.post('/api/ats/detect', { url });
      setDetectedAts(res.data);
    } catch (err) {
      console.error("ATS detection failed", err);
    }
  };

  // Run ATS Parsing Simulation & Auto-match
  const handleSimulateAndMatch = async () => {
    if (!resumeText.trim() && !fileObject) {
      alert("Please upload a resume file or click 'Load Kaggle Resume'.");
      return;
    }
    setLoadingParse(true);
    try {
      const formData = new FormData();
      if (fileObject) formData.append('file', fileObject);
      if (resumeText) formData.append('raw_text', resumeText);
      if (careersUrl) formData.append('careers_url', careersUrl);
      if (companyName) formData.append('company_name', companyName);

      const res = await axios.post('/api/parse/simulate', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setParsedData(res.data);
      if (res.data.ats_detection) setDetectedAts(res.data.ats_detection);

      // Auto-trigger JD match if JD is present
      const textToMatch = res.data.parsed_text || resumeText;
      if (jdText && textToMatch) {
        setLoadingMatch(true);
        const matchRes = await axios.post('/api/match/score', {
          resume_text: textToMatch,
          jd_text: jdText,
          groq_api_key: groqApiKey
        });
        setMatchData(matchRes.data);
      }
    } catch (err) {
      alert("Analysis failed. " + (err.response?.data?.detail || err.message));
    } finally {
      setLoadingParse(false);
      setLoadingMatch(false);
    }
  };

  // Run Batch ATS Comparison
  const handleBatchComparison = async () => {
    if (!resumeText && !fileObject) return;
    setLoadingBatch(true);
    try {
      const formData = new FormData();
      if (fileObject) formData.append('file', fileObject);
      if (resumeText) formData.append('raw_text', resumeText);

      const res = await axios.post('/api/batch/parse', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });
      setBatchData(res.data);
      setShowBatchMatrix(true);
    } catch (err) {
      console.error("Batch comparison failed", err);
    } finally {
      setLoadingBatch(false);
    }
  };

  const atsProfile = detectedAts?.profile || { name: 'Generic ATS', parsing_behavior: {} };
  const isTier1 = detectedAts?.source_tier === 'tier1';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '20px', maxWidth: '1200px', margin: '0 auto' }}>
      
      {/* Streamlined Primary Input Box */}
      <div className="glass-panel" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '18px', flexWrap: 'wrap', gap: '12px' }}>
          <h2 style={{ fontSize: '1.05rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Building2 size={18} /> Company ATS & Resume Input
          </h2>

          {detectedAts?.detected ? (
            <span className={`badge ${isTier1 ? 'badge-green' : 'badge-amber'}`}>
              {isTier1 ? <CheckCircle size={12} /> : <AlertTriangle size={12} />}
              {detectedAts.badge_label || (isTier1 ? `Verified Live: ${detectedAts.profile.name}` : `AI Best Guess: ${detectedAts.profile.name}`)}
            </span>
          ) : (
            <span className="badge badge-neutral">
              Generic ATS Profile
            </span>
          )}
        </div>

        {/* 3 Streamlined Inputs */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px' }}>
          
          {/* Input 1: Company Name */}
          <div>
            <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>
              Target Company Name:
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type="text"
                className="input-field"
                placeholder="e.g. Stripe, IBM, Meta, Netflix, Deloitte"
                value={companyName}
                onChange={(e) => handleCompanyLookup(e.target.value)}
              />
              {loadingCompany && (
                <RefreshCw size={14} className="animate-spin" style={{ position: 'absolute', right: '12px', top: '12px', color: 'var(--text-muted)' }} />
              )}
            </div>

            <div style={{ marginTop: '6px', display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '8px' }}>
              <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>
                {detectedAts?.message || 'AI Tier 1 search & Tier 2 Groq fallback enabled'}
              </span>
              <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                <select
                  value={detectedAts?.profile?.id || 'generic'}
                  onChange={async (e) => {
                    const newId = e.target.value;
                    if (companyName.trim()) {
                      try {
                        const res = await axios.post('/api/ats/correct', { company_name: companyName, ats_id: newId });
                        setDetectedAts(res.data);
                      } catch (err) {
                        console.error("Failed to correct ATS", err);
                      }
                    }
                  }}
                  className="input-field"
                  style={{ width: 'auto', padding: '2px 6px', fontSize: '0.72rem', background: 'rgba(0,0,0,0.4)' }}
                >
                  <option value="workday">Workday</option>
                  <option value="greenhouse">Greenhouse</option>
                  <option value="lever">Lever</option>
                  <option value="icims">iCIMS</option>
                  <option value="taleo">Taleo (Oracle)</option>
                  <option value="smartrecruiters">SmartRecruiters</option>
                  <option value="successfactors">SAP SuccessFactors</option>
                  <option value="generic">Generic ATS</option>
                </select>

                <button
                  style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', fontSize: '0.75rem', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
                  onClick={() => setShowUrlOverride(!showUrlOverride)}
                >
                  <Link size={12} /> {showUrlOverride ? 'Hide URL Override' : 'URL Override'}
                </button>
              </div>
            </div>

            {showUrlOverride && (
              <input
                type="text"
                className="input-field"
                placeholder="https://myworkdayjobs.com/careers"
                value={careersUrl}
                onChange={(e) => handleUrlChange(e.target.value)}
                style={{ marginTop: '8px', fontSize: '0.82rem' }}
              />
            )}
          </div>

          {/* Input 2: Compact Resume File Upload */}
          <div>
            <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)', display: 'block', marginBottom: '6px' }}>
              Resume Document Upload (PDF/DOCX):
            </label>

            {fileObject ? (
              <div style={{
                background: 'rgba(0,0,0,0.4)',
                border: '1px solid var(--border-color)',
                padding: '8px 14px',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '0.85rem'
              }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-primary)' }}>
                  📄 <strong>{fileObject.name}</strong> ({Math.round(fileObject.size / 1024)} KB)
                </span>
                <button
                  onClick={() => { setFileObject(null); setResumeText(''); }}
                  style={{ background: 'none', border: 'none', color: 'var(--signal-red)', cursor: 'pointer' }}
                >
                  <X size={16} />
                </button>
              </div>
            ) : resumeText ? (
              <div style={{
                background: 'rgba(0,0,0,0.4)',
                border: '1px solid var(--border-color)',
                padding: '8px 14px',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '0.85rem'
              }}>
                <span style={{ display: 'flex', alignItems: 'center', gap: '8px', color: 'var(--text-primary)' }}>
                  📄 <strong>Loaded Real Kaggle Candidate Resume</strong>
                </span>
                <button
                  onClick={() => setResumeText('')}
                  style={{ background: 'none', border: 'none', color: 'var(--signal-red)', cursor: 'pointer' }}
                >
                  <X size={16} />
                </button>
              </div>
            ) : (
              <div style={{
                border: '1px dashed var(--border-color)',
                borderRadius: '8px',
                padding: '12px',
                textAlign: 'center',
                background: 'rgba(0,0,0,0.2)'
              }}>
                <input
                  type="file"
                  id="resume-file-input"
                  accept=".pdf,.docx,.txt"
                  onChange={(e) => {
                    if (e.target.files?.[0]) setFileObject(e.target.files[0]);
                  }}
                  style={{ display: 'none' }}
                />
                <label htmlFor="resume-file-input" style={{ cursor: 'pointer', fontSize: '0.82rem', color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  <Upload size={14} /> Choose Resume File or Drop Here
                </label>
              </div>
            )}
          </div>

        </div>

        {/* Input 3: Target Job Description */}
        <div style={{ marginTop: '16px' }}>
          <label style={{ fontSize: '0.82rem', fontWeight: 600, color: 'var(--text-secondary)', marginBottom: '6px', display: 'block' }}>
            Target Job Description (JD):
          </label>
          <textarea
            className="input-field mono-editor"
            rows={5}
            placeholder="Paste target job requirements and description..."
            value={jdText}
            onChange={(e) => setJdText(e.target.value)}
          />
        </div>

        {/* Primary Action Button */}
        <div style={{ marginTop: '16px', display: 'flex', gap: '10px' }}>
          <button className="btn-primary" onClick={handleSimulateAndMatch} disabled={loadingParse || loadingMatch}>
            {loadingParse || loadingMatch ? <RefreshCw className="animate-spin" size={15} /> : <Cpu size={15} />}
            Analyze ATS Parsing & Requirement Match
          </button>
        </div>
      </div>

      {/* Step 2: Headline Cards */}
      {(parsedData || matchData) && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '16px' }}>
          
          {/* Structure Integrity Score Card */}
          {parsedData && (
            <div className="metric-card">
              <span className="metric-label">Structure Integrity Score</span>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
                <span className="metric-number" style={{
                  color: parsedData.parsing_score >= 75 ? 'var(--signal-green)' : parsedData.parsing_score >= 50 ? 'var(--signal-amber)' : 'var(--signal-red)'
                }}>
                  {parsedData.parsing_score}/100
                </span>
                <span className={`badge ${parsedData.parsing_score >= 75 ? 'badge-green' : parsedData.parsing_score >= 50 ? 'badge-amber' : 'badge-red'}`}>
                  {parsedData.ats_profile?.name || 'ATS'}
                </span>
              </div>
              <p className="metric-explanation">
                How much of your original resume formatting and section content survived this ATS's layout parser without mangling.
              </p>
            </div>
          )}

          {/* JD Requirement Match Score Card */}
          {matchData && (
            <div className="metric-card">
              <span className="metric-label">JD Requirement Match Score</span>
              <div style={{ display: 'flex', alignItems: 'baseline', gap: '10px' }}>
                <span className="metric-number" style={{
                  color: matchData.match_score >= 70 ? 'var(--signal-green)' : matchData.match_score >= 45 ? 'var(--signal-amber)' : 'var(--signal-red)'
                }}>
                  {matchData.match_score}%
                </span>
                {matchData.groq_used && (
                  <span className="badge badge-green">Groq LLM Evaluated</span>
                )}
              </div>
              <p className="metric-explanation">
                How well your resume's actual content covers what this job description is asking for.
              </p>
            </div>
          )}

        </div>
      )}

      {/* Step 3: Key Requirement Findings */}
      {matchData && (
        <div className="glass-panel" style={{ padding: '20px 24px' }}>
          <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '14px', color: 'var(--text-primary)' }}>
            Requirement Fit Analysis
          </h3>
          <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', marginBottom: '16px' }}>
            {matchData.summary}
          </p>

          {/* Missing Requirements List */}
          {matchData.missing_requirements?.length > 0 && (
            <div style={{ marginBottom: '16px' }}>
              <h4 style={{ fontSize: '0.82rem', color: 'var(--signal-red)', marginBottom: '8px', fontWeight: 600 }}>
                Critical Missing Requirements ({matchData.missing_requirements.length}):
              </h4>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {matchData.missing_requirements.map((item, idx) => (
                  <div key={idx} style={{
                    background: 'rgba(239, 68, 68, 0.1)',
                    border: '1px solid rgba(239, 68, 68, 0.3)',
                    padding: '6px 12px',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                    color: '#fca5a5'
                  }}>
                    ❌ <strong>{item.requirement}:</strong> {item.rationale}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Matched Requirements List */}
          {matchData.matched_requirements?.length > 0 && (
            <div>
              <h4 style={{ fontSize: '0.82rem', color: 'var(--signal-green)', marginBottom: '8px', fontWeight: 600 }}>
                Matched Requirements ({matchData.matched_requirements.length}):
              </h4>
              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
                {matchData.matched_requirements.map((item, idx) => (
                  <div key={idx} style={{
                    background: 'rgba(16, 185, 129, 0.1)',
                    border: '1px solid rgba(16, 185, 129, 0.3)',
                    padding: '6px 12px',
                    borderRadius: '6px',
                    fontSize: '0.8rem',
                    color: '#6ee7b7'
                  }}>
                    ✅ <strong>{item.requirement}:</strong> {item.rationale}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Step 4: Expandable Detailed Technical Breakdown */}
      {parsedData && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
          
          <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
            <button
              className="btn-secondary"
              onClick={() => setShowRawDiff(!showRawDiff)}
            >
              <FileText size={15} />
              {showRawDiff ? 'Hide Raw Extracted Text Diff' : 'View Raw Extracted Text Diff'}
            </button>

            <button
              className="btn-secondary"
              onClick={handleBatchComparison}
              disabled={loadingBatch}
            >
              {loadingBatch ? <RefreshCw className="animate-spin" size={15} /> : <Layers size={15} />}
              {showBatchMatrix ? 'Hide Cross-ATS Matrix' : 'Compare Across All ATS Profiles'}
            </button>
          </div>

          {/* Collapsible Raw Diff View (Scan Reveal Animation) */}
          {showRawDiff && (
            <div className="glass-panel animate-scan-reveal" style={{ padding: '20px 24px', borderLeft: '4px solid var(--cyan-accent)' }}>
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
                <h3 style={{ fontSize: '0.9rem', fontWeight: 700, color: 'var(--cyan-accent)', display: 'flex', alignItems: 'center', gap: '8px' }}>
                  <span>⚡ Scan Reveal Diff — What You Wrote vs What Survived</span>
                </h3>
                <span className="badge badge-neutral mono-val" style={{ fontSize: '0.72rem' }}>
                  Mangled Spans: {parsedData.mangled_spans?.length || 0}
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '14px' }}>
                <div style={{ background: 'rgba(0,0,0,0.4)', padding: '14px', borderRadius: '8px', border: '1px solid var(--border-color)' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '6px' }}>
                    ORIGINAL INPUT RESUME TEXT
                  </span>
                  <div className="mono-editor" style={{ maxHeight: '280px', overflowY: 'auto' }}>
                    {parsedData.original_text}
                  </div>
                </div>

                <div style={{ background: 'rgba(0,0,0,0.6)', padding: '14px', borderRadius: '8px', border: '1px solid var(--cyan-accent)' }}>
                  <span style={{ fontSize: '0.75rem', color: 'var(--cyan-accent)', display: 'block', marginBottom: '6px', fontWeight: 700 }}>
                    MACHINE EXTRACTED TEXT ({parsedData.ats_profile?.name || 'ATS'})
                  </span>
                  <div className="mono-editor" style={{ maxHeight: '280px', overflowY: 'auto' }}>
                    {parsedData.parsed_text}
                  </div>
                </div>
              </div>

              {/* Mangled Spans Micro-Label Callouts */}
              {parsedData.mangled_spans?.length > 0 && (
                <div style={{ marginTop: '14px', paddingTop: '12px', borderTop: '1px solid var(--border-color)' }}>
                  <span style={{ fontSize: '0.78rem', fontWeight: 600, color: 'var(--signal-amber)', display: 'block', marginBottom: '8px' }}>
                    ⚠️ Spans Mangled or Dropped by Parser ({parsedData.mangled_spans.length}):
                  </span>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                    {parsedData.mangled_spans.map((span, idx) => (
                      <span
                        key={idx}
                        title="⨯ dropped by parser"
                        style={{
                          fontSize: '0.72rem',
                          background: 'rgba(239, 68, 68, 0.15)',
                          border: '1px solid rgba(239, 68, 68, 0.4)',
                          color: '#fca5a5',
                          padding: '2px 8px',
                          borderRadius: '4px',
                          textDecoration: 'line-through',
                          opacity: 0.85,
                          cursor: 'help'
                        }}
                      >
                        ⨯ {span.reason || 'dropped by parser'}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Collapsible Batch ATS Comparison Matrix */}
          {showBatchMatrix && batchData && (
            <div className="glass-panel" style={{ padding: '20px 24px' }}>
              <h3 style={{ fontSize: '0.9rem', fontWeight: 700, marginBottom: '14px', color: 'var(--text-primary)' }}>
                Cross-ATS Compatibility Matrix
              </h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.82rem' }}>
                  <thead>
                    <tr style={{ borderBottom: '1px solid var(--border-color)', textAlign: 'left', color: 'var(--text-secondary)' }}>
                      <th style={{ padding: '8px' }}>ATS Engine</th>
                      <th style={{ padding: '8px' }}>Retained Structure Score</th>
                      <th style={{ padding: '8px' }}>Layout Issues</th>
                      <th style={{ padding: '8px' }}>Profile Quirks</th>
                    </tr>
                  </thead>
                  <tbody>
                    {batchData.comparison.map((item) => (
                      <tr key={item.ats_id} style={{ borderBottom: '1px solid rgba(255,255,255,0.05)' }}>
                        <td style={{ padding: '10px 8px', fontWeight: 600 }}>{item.ats_name}</td>
                        <td style={{ padding: '10px 8px' }}>
                          <span className={`badge ${item.parsing_score >= 75 ? 'badge-green' : item.parsing_score >= 50 ? 'badge-amber' : 'badge-red'}`}>
                            {item.parsing_score}%
                          </span>
                        </td>
                        <td style={{ padding: '10px 8px', color: item.mangled_count > 0 ? 'var(--signal-red)' : 'var(--signal-green)' }}>
                          {item.mangled_count} issues
                        </td>
                        <td style={{ padding: '10px 8px', color: 'var(--text-muted)', fontSize: '0.78rem' }}>
                          {item.description}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

        </div>
      )}

      {/* Connective Handoff to Dashboard 2 */}
      {parsedData && (
        <div style={{
          background: 'rgba(255,255,255,0.03)',
          border: '1px solid var(--border-color)',
          borderRadius: '12px',
          padding: '18px 24px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: '12px'
        }}>
          <div>
            <h4 style={{ fontSize: '0.95rem', fontWeight: 700, color: '#fff' }}>
              Proceed to Dashboard 2: Candidate Bias Audit
            </h4>
            <p style={{ fontSize: '0.8rem', color: 'var(--text-secondary)' }}>
              Inspect how automated screening models score this candidate using SHAP & LIME.
            </p>
          </div>
          <button className="btn-primary" onClick={() => onHandoffToAudit(matchData?.extracted_features)}>
            Audit Candidate in Dashboard 2 <ArrowRight size={15} />
          </button>
        </div>
      )}

    </div>
  );
}
