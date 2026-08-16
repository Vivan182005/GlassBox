import React, { useState } from 'react';
import { Sparkles, Upload, Search, Briefcase, MapPin, Clock, DollarSign, X, ArrowRight, CheckCircle2, AlertCircle, FileText, ChevronRight, Sliders, ExternalLink, ShieldAlert, Code, Building2 } from 'lucide-react';
import axios from 'axios';
import SearchableMultiSelect from './SearchableMultiSelect';

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

  // Step 2: Interactive Search Taxonomy Preferences State (backed by Supabase)
  const [maxTargetRoles, setMaxTargetRoles] = useState(5);
  const [targetRoles, setTargetRoles] = useState([
    { id: 1, name: 'Software Engineer', category: 'Software Engineering', is_ai_extracted: false },
    { id: 2, name: 'Machine Learning Engineer', category: 'AI / Data Science', is_ai_extracted: false }
  ]);

  const [preferredLocations, setPreferredLocations] = useState([
    { id: 201, name: 'Bengaluru, Karnataka, India', city: 'Bengaluru', country: 'India', is_ai_extracted: false },
    { id: 214, name: 'Remote (Worldwide)', city: 'Remote', country: 'Worldwide', is_ai_extracted: false }
  ]);

  const [skillsList, setSkillsList] = useState([
    { id: 101, name: 'Python', category: 'Programming Languages', is_ai_extracted: false },
    { id: 104, name: 'React.js', category: 'Frontend Frameworks', is_ai_extracted: false },
    { id: 106, name: 'SQL', category: 'Databases', is_ai_extracted: false },
    { id: 108, name: 'Machine Learning', category: 'AI / Data Science', is_ai_extracted: false }
  ]);

  const [employmentType, setEmploymentType] = useState('Full-time');
  const [workMode, setWorkMode] = useState('Any');
  const [experienceLevel, setExperienceLevel] = useState('0-1 years');
  const [yearsExperienceNum, setYearsExperienceNum] = useState(1.0);
  const [minSalary, setMinSalary] = useState('');
  const [postingAge, setPostingAge] = useState('7 days');
  const [companyPref, setCompanyPref] = useState('Any');

  // Decision Factor Weights
  const [decisionFactors, setDecisionFactors] = useState({
    title_match: 0.30,
    skill_match: 0.40,
    location_match: 0.15,
    work_mode: 0.10,
    experience: 0.05
  });

  // Step 3: Search Results State
  const [loadingSearch, setLoadingSearch] = useState(false);
  const [searchStatusMsg, setSearchStatusMsg] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [selectedJobDetails, setSelectedJobDetails] = useState(null);

  // Handle Resume File / Text Upload & AI Profile Extraction
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
      formData.append('max_roles', maxTargetRoles);

      const res = await axios.post('/api/resume/extract-profile', formData, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setExtractedProfile(res.data);
      const explicit = res.data.explicit_fields || {};

      // Map normalized Supabase taxonomy records returned from AI extraction
      if (res.data.taxonomy_roles?.length) {
        setTargetRoles(res.data.taxonomy_roles);
      }
      if (res.data.taxonomy_skills?.length) {
        setSkillsList(res.data.taxonomy_skills);
      }
      if (res.data.taxonomy_locations?.length) {
        setPreferredLocations(res.data.taxonomy_locations);
      }

      if (explicit.years_experience !== undefined) {
        setYearsExperienceNum(explicit.years_experience);
        if (explicit.years_experience <= 1) setExperienceLevel('0-1 years');
        else if (explicit.years_experience <= 3) setExperienceLevel('1-3 years');
        else setExperienceLevel('3-5 years');
      }
      if (explicit.has_internship !== undefined) {
        setEmploymentType(explicit.has_internship ? 'Internship' : 'Full-time');
      }
    } catch (err) {
      alert("Profile extraction failed. " + (err.response?.data?.detail || err.message));
    } finally {
      setLoadingExtract(false);
    }
  };

  // Handle Live Job Search
  const handleSearchJobs = async () => {
    if (targetRoles.length === 0) {
      alert("Please select at least one Target Role from the database.");
      return;
    }
    setLoadingSearch(true);
    setSearchStatusMsg('Connecting to LinkedIn Live API...');
    try {
      const payload = {
        preferences: {
          target_roles: targetRoles.map((r) => r.name),
          preferred_locations: preferredLocations.map((l) => l.name),
          employment_type: employmentType,
          work_mode: workMode,
          experience_level: experienceLevel,
          years_experience: yearsExperienceNum,
          skills: skillsList.map((s) => s.name),
          min_salary: minSalary ? parseFloat(minSalary) : 0.0,
          max_posting_age: postingAge,
          company_preference: companyPref
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

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '24px', maxWidth: '1200px', margin: '0 auto' }}>
      
      {/* Header Banner */}
      <div className="glass-panel" style={{ padding: '24px', background: 'linear-gradient(135deg, rgba(16,185,129,0.08) 0%, rgba(17,24,39,0.6) 100%)' }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', marginBottom: '8px' }}>
          <Sparkles size={22} color="var(--signal-green)" />
          <h2 style={{ fontSize: '1.2rem', fontWeight: 800, color: '#f9fafb' }}>
            AI Job Search & Database Taxonomy Preferences
          </h2>
          <span className="badge badge-green">Supabase Backed Taxonomy</span>
        </div>
        <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)', maxWidth: '850px', lineHeight: '1.5' }}>
          Upload your resume to automatically extract candidate preferences normalized against our Supabase taxonomy, or search & select valid roles, skills, and locations.
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
              {loadingExtract ? 'Extracting & Mapping Taxonomy...' : 'Analyze & Map Resume'}
            </button>
          </div>
        </div>
      </div>

      {/* Step 2: Interactive Search Preferences Editor */}
      <div className="glass-panel" style={{ padding: '24px' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '18px', flexWrap: 'wrap', gap: '12px' }}>
          <h3 style={{ fontSize: '1.05rem', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px', color: '#f9fafb' }}>
            <Sliders size={18} color="var(--signal-green)" /> 2. Searchable Taxonomy Preferences (Supabase DB)
          </h3>
          <span style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
            Searchable dropdowns querying database taxonomy records
          </span>
        </div>

        {/* Target Roles & Max Cap Selector */}
        <div style={{ background: 'rgba(0,0,0,0.3)', padding: '16px', borderRadius: '12px', border: '1px solid var(--border-color)', marginBottom: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: '12px', paddingBottom: '12px', borderBottom: '1px solid var(--border-color)' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Briefcase size={16} color="var(--signal-green)" />
              <h4 style={{ fontSize: '0.9rem', fontWeight: 600, color: 'var(--text-primary)' }}>Target Roles Configuration</h4>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <label style={{ fontSize: '0.8rem', color: 'var(--text-secondary)', fontWeight: 500 }}>Number of Target Roles:</label>
              <select
                value={maxTargetRoles}
                onChange={(e) => {
                  const val = parseInt(e.target.value);
                  setMaxTargetRoles(val);
                  if (targetRoles.length > val) {
                    setTargetRoles(targetRoles.slice(0, val));
                  }
                }}
                className="input-field"
                style={{ width: 'auto', padding: '4px 10px', fontSize: '0.8rem' }}
              >
                <option value={1}>1 Role</option>
                <option value={2}>2 Roles</option>
                <option value={3}>3 Roles</option>
                <option value={4}>4 Roles</option>
                <option value={5}>5 Roles (Max)</option>
              </select>
            </div>
          </div>

          <SearchableMultiSelect
            label="Target Job Roles"
            placeholder="Search database roles (e.g. Software Engineer, Machine Learning Engineer)..."
            apiUrl="/api/job-roles"
            selectedItems={targetRoles}
            onItemsChange={setTargetRoles}
            maxSelections={maxTargetRoles}
            icon={Briefcase}
            helpText="Select up to your specified role maximum from Supabase job_roles taxonomy."
          />
        </div>

        {/* Skills & Locations Section */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '16px', marginBottom: '20px' }}>
          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '16px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <SearchableMultiSelect
              label="Technical Skills"
              placeholder="Search skills (e.g. Python, React, SQL, Docker)..."
              apiUrl="/api/skills"
              selectedItems={skillsList}
              onItemsChange={setSkillsList}
              icon={Code}
              helpText="Search and select valid skill entries from Supabase skills taxonomy."
            />
          </div>

          <div style={{ background: 'rgba(0,0,0,0.3)', padding: '16px', borderRadius: '12px', border: '1px solid var(--border-color)' }}>
            <SearchableMultiSelect
              label="Preferred Locations"
              placeholder="Search location (e.g. Bengaluru, San Francisco, Remote)..."
              apiUrl="/api/locations"
              selectedItems={preferredLocations}
              onItemsChange={setPreferredLocations}
              icon={MapPin}
              helpText="Search cities, countries, or remote locations from Supabase locations taxonomy."
            />
          </div>
        </div>

        {/* Controlled Filter Dropdowns Grid */}
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '16px', padding: '16px', background: 'rgba(0,0,0,0.2)', borderRadius: '12px', border: '1px solid var(--border-color)', marginBottom: '20px' }}>
          {/* Employment Type */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Employment Type</label>
            <select
              value={employmentType}
              onChange={(e) => setEmploymentType(e.target.value)}
              className="input-field"
              style={{ padding: '6px 10px', fontSize: '0.82rem' }}
            >
              <option value="Full-time">Full-time</option>
              <option value="Internship">Internship</option>
              <option value="Part-time">Part-time</option>
              <option value="Contract">Contract</option>
              <option value="Temporary">Temporary</option>
              <option value="Apprenticeship">Apprenticeship</option>
              <option value="Any">Any</option>
            </select>
          </div>

          {/* Work Mode */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Work Mode</label>
            <select
              value={workMode}
              onChange={(e) => setWorkMode(e.target.value)}
              className="input-field"
              style={{ padding: '6px 10px', fontSize: '0.82rem' }}
            >
              <option value="Any">Any</option>
              <option value="Remote">Remote</option>
              <option value="Hybrid">Hybrid</option>
              <option value="On-site">On-site</option>
            </select>
          </div>

          {/* Posting Freshness */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Maximum Posting Age</label>
            <select
              value={postingAge}
              onChange={(e) => setPostingAge(e.target.value)}
              className="input-field"
              style={{ padding: '6px 10px', fontSize: '0.82rem' }}
            >
              <option value="24 hours">24 hours</option>
              <option value="3 days">3 days</option>
              <option value="7 days">7 days</option>
              <option value="14 days">14 days</option>
              <option value="30 days">30 days</option>
              <option value="Any">Any</option>
            </select>
          </div>

          {/* Company Size */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
            <label style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--text-secondary)' }}>Company Size</label>
            <select
              value={companyPref}
              onChange={(e) => setCompanyPref(e.target.value)}
              className="input-field"
              style={{ padding: '6px 10px', fontSize: '0.82rem' }}
            >
              <option value="Any">Any</option>
              <option value="Startup">Startup</option>
              <option value="Small">Small</option>
              <option value="Medium">Medium</option>
              <option value="Large">Large</option>
              <option value="Enterprise">Enterprise</option>
            </select>
          </div>
        </div>

        {/* Search Action Button */}
        <div style={{ marginTop: '20px', display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn-primary" onClick={handleSearchJobs} disabled={loadingSearch} style={{ padding: '10px 24px', fontSize: '0.95rem' }}>
            <Search size={16} /> {loadingSearch ? 'Querying Provider...' : 'Find Matching Jobs'}
          </button>
        </div>
      </div>

      {/* Step 3: Search Results Feed & Provider Status */}
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
