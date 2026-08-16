import React, { useState } from 'react';
import { Sparkles, Upload, Search, Briefcase, MapPin, Clock, DollarSign, Plus, X, ArrowRight, CheckCircle2, AlertCircle, FileText, ChevronRight, Sliders, ExternalLink, ShieldAlert } from 'lucide-react';
import axios from 'axios';

export default function JobDiscovery({
  onSelectJobForATS,
  onHandoffToAudit,
  groqApiKey
}) {
  // Step 1: Resume & Profile Extraction State
  const [fileObject, setFileObject] = useState(null);
  const [rawText, setRawText] = useState('');
  const [loadingExtract, setLoadingExtract] = useState(false);
  const [extractedProfile, setExtractedProfile] = useState(null);

  // Step 2: Interactive Preferences State
  const [targetRoles, setTargetRoles] = useState(['Software Engineer', 'AI/ML Engineer']);
  const [newRoleInput, setNewRoleInput] = useState('');

  const [preferredLocations, setPreferredLocations] = useState(['Bangalore', 'Remote']);
  const [newLocInput, setNewLocInput] = useState('');

  const [employmentType, setEmploymentType] = useState('Both'); // Internship | Full-time | Both
  const [workMode, setWorkMode] = useState('Any'); // Remote | Hybrid | On-site | Any
  const [experienceLevel, setExperienceLevel] = useState('0-1 years');
  const [yearsExperienceNum, setYearsExperienceNum] = useState(1.0);

  const [skillsList, setSkillsList] = useState(['Python', 'React', 'SQL', 'Machine Learning']);
  const [newSkillInput, setNewSkillInput] = useState('');

  const [minSalary, setMinSalary] = useState('');
  const [postingAge, setPostingAge] = useState('7'); // days
  const [companyPref, setCompanyPref] = useState('Any'); // Any | Startup | Mid-size | Enterprise
  const [industryFilter, setIndustryFilter] = useState('Any');

  // Decision Factor Weights (Multiple Options Control Panel)
  const [decisionFactors, setDecisionFactors] = useState({
    title_match: 0.25,
    skill_match: 0.30,
    location_match: 0.15,
    work_mode: 0.10,
    experience: 0.10,
    freshness: 0.05,
    salary: 0.05
  });

  // Step 3: Search Results State
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [searchStatusMsg, setSearchStatusMsg] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [selectedJobDetails, setSelectedJobDetails] = useState(null);

  // Handle Resume File / Text Upload & Extraction
  const handleExtractProfile = async (fileToUpload = fileObject, textToUpload = rawText) => {
    if (!fileToUpload && !textToUpload.trim()) {
      alert("Please upload a resume file (PDF/DOCX) or paste resume text.");
      return;
    }
    setLoadingExtract(true);
    try {
      const formData = new FormData();
      if (fileToUpload) formData.append('file', fileToUpload);
      if (textToUpload) formData.append('raw_text', textToUpload);

      const res = await axios.post('/api/resume/extract-profile', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setExtractedProfile(res.data);
      const explicit = res.data.explicit_fields || {};
      const inferred = res.data.inferred_fields || {};

      if (inferred.primary_role) {
        const roles = [inferred.primary_role, ...(inferred.suggested_alternative_roles || [])].slice(0, 3);
        setTargetRoles(roles);
      }
      if (explicit.skill_list?.length) setSkillsList(explicit.skill_list);
      if (explicit.location) setPreferredLocations([explicit.location]);
      if (explicit.years_experience !== undefined) {
        setYearsExperienceNum(explicit.years_experience);
        if (explicit.years_experience <= 1) setExperienceLevel('0-1 years');
        else if (explicit.years_experience <= 3) setExperienceLevel('1-3 years');
        else setExperienceLevel('3-5 years');
      }
      if (explicit.has_internship !== undefined) {
        setEmploymentType(explicit.has_internship ? 'Both' : 'Full-time');
      }
    } catch (err) {
      alert("Profile extraction failed. " + (err.response?.data?.detail || err.message));
    } finally {
      setLoadingExtract(false);
    }
  };

  // Handle Live Job Search
  const handleSearchJobs = async () => {
    setLoadingSearch(true);
    setSearchStatusMsg('Connecting to LinkedIn Live API...');
    try {
      const payload = {
        preferences: {
          target_roles: targetRoles,
          preferred_locations: preferredLocations,
          employment_type: employmentType,
          work_mode: workMode,
          experience_level: experienceLevel,
          years_experience: yearsExperienceNum,
          skills: skillsList,
          min_salary: minSalary ? parseFloat(minSalary) : 0.0,
          max_posting_days: parseInt(postingAge),
          company_preference: companyPref,
          industry: industryFilter
        },
        decision_factors: decisionFactors
      };

      const res = await axios.post('/api/jobs/search', payload);
      setSearchResults(res.data);
    } catch (err) {
      setSearchResults({
        status: 'error',
        provider: 'LinkedIn',
        message: 'Failed to connect to job search backend: ' + (err.response?.data?.error || err.message),
        jobs: []
      });
    } finally {
      setLoadingSearch(false);
      setSearchStatusMsg('');
    }
  };

  // Add/Remove Helpers
  const addRole = () => {
    if (newRoleInput.trim() && !targetRoles.includes(newRoleInput.trim())) {
      setTargetRoles([...targetRoles, newRoleInput.trim()]);
      setNewRoleInput('');
    }
  };
  const removeRole = (r) => setTargetRoles(targetRoles.filter(role => role !== r));

  const addLocation = () => {
    if (newLocInput.trim() && !preferredLocations.includes(newLocInput.trim())) {
      setPreferredLocations([...preferredLocations, newLocInput.trim()]);
      setNewLocInput('');
    }
  };
  const removeLocation = (l) => setPreferredLocations(preferredLocations.filter(loc => loc !== l));

  const addSkill = () => {
    if (newSkillInput.trim() && !skillsList.includes(newSkillInput.trim())) {
      setSkillsList([...skillsList, newSkillInput.trim()]);
      setNewSkillInput('');
    }
  };
  const removeSkill = (s) => setSkillsList(skillsList.filter(sk => sk !== s));

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      
      {/* Header Banner */}
      <div className="glass-panel" style={{ padding: '24px', background: 'linear-gradient(135deg, rgba(16,185,129,0.08) 0%, rgba(17,24,39,0.6) 100%)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <Sparkles size={22} color="var(--signal-green)" />
          <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#f9fafb' }}>
            AI Job Discovery & Intelligent Preference Matcher
          </h2>
          <span className="badge badge-green">Live Provider Architecture</span>
        </div>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', maxWidth: '850px', lineHeight: '1.5' }}>
          Upload your resume to extract candidate job preferences, edit your target search parameters & decision factors, and discover matching opportunities.
        </p>
      </div>

      {/* Step 1: Resume Upload & Extraction Box */}
      <div className="glass-panel" style={{ padding: '20px 24px' }}>
        <h3 style={{ fontSize: '0.95rem', fontWeight: 700, marginBottom: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
          <Upload size={16} /> 1. Upload Resume Document (PDF / DOCX)
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '16px', alignItems: 'center' }}>
          <div>
            {fileObject ? (
              <div style={{
                background: 'rgba(0,0,0,0.4)',
                border: '1px solid var(--border-color)',
                padding: '10px 14px',
                borderRadius: '8px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                fontSize: '0.85rem'
              }}>
                <span>📄 <strong>{fileObject.name}</strong> ({Math.round(fileObject.size / 1024)} KB)</span>
                <button onClick={() => { setFileObject(null); setRawText(''); }} style={{ background: 'none', border: 'none', color: 'var(--signal-red)', cursor: 'pointer' }}>
                  <X size={16} />
                </button>
              </div>
            ) : (
              <div style={{ border: '1px dashed var(--border-color)', borderRadius: '8px', padding: '16px', textAlign: 'center', background: 'rgba(0,0,0,0.2)' }}>
                <input
                  type="file"
                  id="job-discovery-resume-file"
                  accept=".pdf,.docx,.txt"
                  onChange={(e) => {
                    if (e.target.files?.[0]) {
                      setFileObject(e.target.files[0]);
                      handleExtractProfile(e.target.files[0], '');
                    }
                  }}
                  style={{ display: 'none' }}
                />
                <label htmlFor="job-discovery-resume-file" style={{ cursor: 'pointer', fontSize: '0.85rem', color: 'var(--text-secondary)', display: 'inline-flex', alignItems: 'center', gap: '8px' }}>
                  <Upload size={16} /> Select PDF/DOCX Resume File
                </label>
              </div>
            )}
          </div>

          <div style={{ display: 'flex', gap: '10px' }}>
            <button className="btn-primary" onClick={() => handleExtractProfile()} disabled={loadingExtract}>
              {loadingExtract ? 'Analyzing Profile with Gemini AI...' : 'Analyze Resume Profile'}
            </button>
          </div>
        </div>
      </div>

      {/* Step 2: Interactive Search Preferences Editor */}
      <div className="glass-panel" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', flexWrap: 'wrap', gap: '12px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px', color: '#f9fafb' }}>
            <Sliders size={18} color="var(--signal-green)" /> 2. Your Job Search Preferences
          </h3>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Editable candidate criteria used for live job provider querying & deterministic ranking
          </span>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(320px, 1fr))', gap: '20px' }}>
          
          {/* Target Roles */}
          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '14px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
            <label style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-secondary)', display: 'block', marginBottom: '8px' }}>
              Target Roles:
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
              {targetRoles.map((role) => (
                <span key={role} style={{ background: 'rgba(16,185,129,0.15)', border: '1px solid rgba(16,185,129,0.3)', color: '#6ee7b7', padding: '4px 10px', borderRadius: '16px', fontSize: '0.8rem', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  {role}
                  <X size={12} style={{ cursor: 'pointer' }} onClick={() => removeRole(role)} />
                </span>
              ))}
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              <input
                type="text"
                className="input-field"
                placeholder="Add target role (e.g. Backend Developer)..."
                value={newRoleInput}
                onChange={(e) => setNewRoleInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addRole()}
                style={{ fontSize: '0.8rem' }}
              />
              <button className="btn-secondary" onClick={addRole} style={{ padding: '4px 10px' }}><Plus size={14} /></button>
            </div>
          </div>

          {/* Preferred Locations */}
          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '14px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
            <label style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-secondary)', display: 'block', marginBottom: '8px' }}>
              Preferred Locations:
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px' }}>
              {preferredLocations.map((loc) => (
                <span key={loc} style={{ background: 'rgba(59,130,246,0.15)', border: '1px solid rgba(59,130,246,0.3)', color: '#93c5fd', padding: '4px 10px', borderRadius: '16px', fontSize: '0.8rem', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  {loc}
                  <X size={12} style={{ cursor: 'pointer' }} onClick={() => removeLocation(loc)} />
                </span>
              ))}
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              <input
                type="text"
                className="input-field"
                placeholder="Add location (e.g. Hyderabad)..."
                value={newLocInput}
                onChange={(e) => setNewLocInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addLocation()}
                style={{ fontSize: '0.8rem' }}
              />
              <button className="btn-secondary" onClick={addLocation} style={{ padding: '4px 10px' }}><Plus size={14} /></button>
            </div>
          </div>

          {/* Employment Type & Work Mode */}
          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '14px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
            <label style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-secondary)', display: 'block', marginBottom: '8px' }}>
              Employment Type & Work Mode:
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Type:</span>
                <select className="input-field" value={employmentType} onChange={(e) => setEmploymentType(e.target.value)} style={{ fontSize: '0.8rem' }}>
                  <option value="Internship">Internship</option>
                  <option value="Full-time">Full-time</option>
                  <option value="Both">Both</option>
                </select>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Mode:</span>
                <select className="input-field" value={workMode} onChange={(e) => setWorkMode(e.target.value)} style={{ fontSize: '0.8rem' }}>
                  <option value="Any">Any</option>
                  <option value="Remote">Remote</option>
                  <option value="Hybrid">Hybrid</option>
                  <option value="On-site">On-site</option>
                </select>
              </div>
            </div>
          </div>

          {/* Skills Chips */}
          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '14px', borderRadius: '10px', border: '1px solid var(--border-color)', gridColumn: 'span 1' }}>
            <label style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-secondary)', display: 'block', marginBottom: '8px' }}>
              Extracted Technical Skills:
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '8px', maxHeight: '100px', overflowY: 'auto' }}>
              {skillsList.map((skill) => (
                <span key={skill} style={{ background: 'rgba(255,255,255,0.08)', border: '1px solid var(--border-color)', color: 'var(--text-primary)', padding: '4px 10px', borderRadius: '16px', fontSize: '0.8rem', display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                  {skill}
                  <X size={12} style={{ cursor: 'pointer' }} onClick={() => removeSkill(skill)} />
                </span>
              ))}
            </div>
            <div style={{ display: 'flex', gap: '6px' }}>
              <input
                type="text"
                className="input-field"
                placeholder="Add skill (e.g. PyTorch)..."
                value={newSkillInput}
                onChange={(e) => setNewSkillInput(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && addSkill()}
                style={{ fontSize: '0.8rem' }}
              />
              <button className="btn-secondary" onClick={addSkill} style={{ padding: '4px 10px' }}><Plus size={14} /></button>
            </div>
          </div>

          {/* Experience, Salary & Posting Age Filters */}
          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '14px', borderRadius: '10px', border: '1px solid var(--border-color)' }}>
            <label style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--text-secondary)', display: 'block', marginBottom: '8px' }}>
              Experience & Posting Freshness:
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Max Posting Age:</span>
                <select className="input-field" value={postingAge} onChange={(e) => setPostingAge(e.target.value)} style={{ fontSize: '0.8rem' }}>
                  <option value="1">24 hours</option>
                  <option value="3">3 days</option>
                  <option value="7">7 days (Default)</option>
                  <option value="14">14 days</option>
                  <option value="30">30 days</option>
                </select>
              </div>
              <div>
                <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'block', marginBottom: '4px' }}>Company Size:</span>
                <select className="input-field" value={companyPref} onChange={(e) => setCompanyPref(e.target.value)} style={{ fontSize: '0.8rem' }}>
                  <option value="Any">Any</option>
                  <option value="Startup">Startup</option>
                  <option value="Mid-size">Mid-size</option>
                  <option value="Enterprise">Enterprise</option>
                </select>
              </div>
            </div>
          </div>

          {/* Decision Factors Control Panel (Multiple Options) */}
          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '14px', borderRadius: '10px', border: '1px solid var(--border-color)', gridColumn: 'span 1' }}>
            <label style={{ fontSize: '0.82rem', fontWeight: 700, color: 'var(--signal-green)', display: 'block', marginBottom: '8px' }}>
              Match Decision Factor Weights:
            </label>
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', fontSize: '0.78rem' }}>
              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-secondary)' }}>
                  <span>Skill Overlap Weight:</span>
                  <strong>{Math.round(decisionFactors.skill_match * 100)}%</strong>
                </div>
                <input
                  type="range"
                  min="0.10"
                  max="0.60"
                  step="0.05"
                  value={decisionFactors.skill_match}
                  onChange={(e) => setDecisionFactors({ ...decisionFactors, skill_match: parseFloat(e.target.value) })}
                  style={{ width: '100%' }}
                />
              </div>

              <div>
                <div style={{ display: 'flex', justifyContent: 'space-between', color: 'var(--text-secondary)' }}>
                  <span>Role Title Match Weight:</span>
                  <strong>{Math.round(decisionFactors.title_match * 100)}%</strong>
                </div>
                <input
                  type="range"
                  min="0.10"
                  max="0.50"
                  step="0.05"
                  value={decisionFactors.title_match}
                  onChange={(e) => setDecisionFactors({ ...decisionFactors, title_match: parseFloat(e.target.value) })}
                  style={{ width: '100%' }}
                />
              </div>
            </div>
          </div>

        </div>

        {/* Search Action Button */}
        <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn-primary" onClick={handleSearchJobs} disabled={loadingSearch} style={{ padding: '10px 24px', fontSize: '0.95rem' }}>
            <Search size={16} /> {loadingSearch ? 'Searching Live Provider...' : 'Find Matching Jobs'}
          </button>
        </div>
      </div>

      {/* Step 3: Search Results Feed & Honest Provider Banner */}
      {searchResults && (
        <div className="glass-panel" style={{ padding: '24px' }}>
          
          {searchResults.status !== 'success' ? (
            <div style={{
              background: 'rgba(239,68,68,0.1)',
              border: '1px solid rgba(239,68,68,0.3)',
              borderRadius: '10px',
              padding: '20px',
              color: '#fca5a5'
            }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '8px' }}>
                <ShieldAlert size={20} color="var(--signal-red)" />
                <h4 style={{ fontSize: '1rem', fontWeight: 700 }}>
                  Unable to Fetch Live Jobs ({searchResults.provider || 'Provider'})
                </h4>
              </div>
              <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', lineHeight: '1.5' }}>
                {searchResults.message}
              </p>
              <div style={{ marginTop: '14px', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                <strong>Required Configuration on Render:</strong> Add <code>LINKEDIN_CLIENT_ID</code> and <code>LINKEDIN_ACCESS_TOKEN</code> to your Render environment variables to enable live LinkedIn API queries.
              </div>
            </div>
          ) : (
            <div>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
                <h3 style={{ fontSize: '1.05rem', fontWeight: 700, color: '#f9fafb' }}>
                  Live Matching Jobs ({searchResults.total_found})
                </h3>
                <span className="badge badge-green">Official {searchResults.provider} API</span>
              </div>

              <div style={{ display: 'flex', flexDirection: 'column', gap: '16px' }}>
                {searchResults.jobs.map((job) => (
                  <div key={job.providerJobId || job.id} className="glass-panel" style={{ padding: '18px 20px', background: 'rgba(0,0,0,0.4)', borderRadius: '12px' }}>
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: '12px' }}>
                      <div>
                        <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontWeight: 600 }}>{job.companyName}</div>
                        <h4 style={{ fontSize: '1.1rem', fontWeight: 700, color: '#fff', margin: '2px 0 6px 0' }}>{job.title}</h4>
                        <div style={{ display: 'flex', gap: '12px', fontSize: '0.8rem', color: 'var(--text-secondary)', flexWrap: 'wrap' }}>
                          {job.location && <span>📍 {job.location}</span>}
                          {job.workMode && <span>💻 {job.workMode}</span>}
                          {job.employmentType && <span>💼 {job.employmentType}</span>}
                          {job.postedAt && <span>📅 Posted {job.postedAt}</span>}
                        </div>
                      </div>

                      <div style={{ textAlign: 'right' }}>
                        <div style={{ fontSize: '1.4rem', fontWeight: 800, color: job.match_percentage >= 75 ? 'var(--signal-green)' : 'var(--signal-amber)' }}>
                          {job.match_percentage}%
                        </div>
                        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Match Score</span>
                      </div>
                    </div>

                    <p style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', margin: '12px 0', lineHeight: '1.4' }}>
                      {job.why_matched}
                    </p>

                    {/* Skill Tags */}
                    {job.skills?.length > 0 && (
                      <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px', marginBottom: '14px' }}>
                        {job.skills.map(s => (
                          <span key={s} style={{ background: 'rgba(255,255,255,0.06)', padding: '3px 8px', borderRadius: '4px', fontSize: '0.75rem', color: 'var(--text-secondary)' }}>
                            {s}
                          </span>
                        ))}
                      </div>
                    )}

                    {/* Card Buttons */}
                    <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
                      <button className="btn-secondary" onClick={() => setSelectedJobDetails(job)} style={{ fontSize: '0.8rem' }}>
                        More Details
                      </button>

                      <button className="btn-primary" onClick={() => onSelectJobForATS(job)} style={{ fontSize: '0.8rem' }}>
                        ATS Check <ArrowRight size={13} />
                      </button>

                      {job.applicationUrl && (
                        <a href={job.applicationUrl} target="_blank" rel="noopener noreferrer" className="btn-secondary" style={{ fontSize: '0.8rem', display: 'inline-flex', alignItems: 'center', gap: '4px', textDecoration: 'none' }}>
                          Apply <ExternalLink size={13} />
                        </a>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

        </div>
      )}

      {/* Step 4: Job Details Modal */}
      {selectedJobDetails && (
        <div style={{
          position: 'fixed',
          top: 0,
          left: 0,
          width: '100vw',
          height: '100vh',
          background: 'rgba(0,0,0,0.85)',
          backdropFilter: 'blur(5px)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          zIndex: 100,
          padding: '20px'
        }}>
          <div className="glass-panel" style={{ width: '100%', maxWidth: '680px', maxHeight: '85vh', overflowY: 'auto', padding: '24px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '16px' }}>
              <div>
                <span className="badge badge-green">{selectedJobDetails.provider}</span>
                <h3 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#fff', marginTop: '6px' }}>{selectedJobDetails.title}</h3>
                <div style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>{selectedJobDetails.companyName} · {selectedJobDetails.location}</div>
              </div>
              <button onClick={() => setSelectedJobDetails(null)} style={{ background: 'none', border: 'none', color: '#9ca3af', cursor: 'pointer' }}>
                <X size={20} />
              </button>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px', fontSize: '0.8rem', color: 'var(--text-secondary)', marginBottom: '16px', background: 'rgba(0,0,0,0.3)', padding: '12px', borderRadius: '8px' }}>
              <div>Work Mode: <strong>{selectedJobDetails.workMode}</strong></div>
              <div>Employment: <strong>{selectedJobDetails.employmentType}</strong></div>
              <div>Experience: <strong>{selectedJobDetails.experience || 'Not specified'}</strong></div>
              <div>Salary: <strong>{selectedJobDetails.salary || 'Not disclosed'}</strong></div>
            </div>

            <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--signal-green)', marginBottom: '6px' }}>Why This Job Matches</h4>
            <p style={{ fontSize: '0.82rem', color: 'var(--text-primary)', marginBottom: '16px', lineHeight: '1.5' }}>
              {selectedJobDetails.why_matched}
            </p>

            <h4 style={{ fontSize: '0.85rem', fontWeight: 700, color: 'var(--text-secondary)', marginBottom: '6px' }}>Job Description</h4>
            <div style={{ fontSize: '0.82rem', color: 'var(--text-secondary)', lineHeight: '1.6', whiteSpace: 'pre-line', maxHeight: '200px', overflowY: 'auto', background: 'rgba(0,0,0,0.2)', padding: '12px', borderRadius: '8px' }}>
              {selectedJobDetails.description || 'No full description text provided by provider.'}
            </div>

            <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
              <button className="btn-secondary" onClick={() => setSelectedJobDetails(null)}>Close</button>
              <button className="btn-primary" onClick={() => { const job = selectedJobDetails; setSelectedJobDetails(null); onSelectJobForATS(job); }}>
                Run ATS Check
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
