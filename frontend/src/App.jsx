import React, { useState, useEffect } from 'react';
import axios from 'axios';
import Header from './components/Header';
import JobDiscovery from './components/Dashboard1/JobDiscovery';
import ATSChecker from './components/Dashboard1/ATSChecker';
import BiasAuditor from './components/Dashboard2/BiasAuditor';

axios.defaults.baseURL = import.meta.env.VITE_API_BASE_URL || '';

const DEFAULT_SAMPLE_JD = `Role: Senior Software Engineer
Location: San Francisco, CA (Hybrid)

Responsibilities:
- Design, build, and maintain production web applications and distributed backend microservices.
- Optimize database queries (PostgreSQL/SQL) and deploy cloud containers via Docker and AWS.
- Collaborate with product managers and UX designers to deliver polished feature updates.

Requirements:
- 4+ years of professional full stack software engineering experience.
- Strong proficiency in Python, React, Node.js, and SQL databases.
- Experience with containerization (Docker) and cloud infrastructure.
- Bachelor's degree in Computer Science or equivalent field.`;

export default function App() {
  const [activeTab, setActiveTab] = useState('job_discovery');
  const [resumeText, setResumeText] = useState('');
  const [jdText, setJdText] = useState(DEFAULT_SAMPLE_JD);
  const [companyName, setCompanyName] = useState('Stripe');
  const [careersUrl, setCareersUrl] = useState('');
  const [detectedAts, setDetectedAts] = useState(null);
  const [parsedData, setParsedData] = useState(null);
  const [matchData, setMatchData] = useState(null);
  const [groqApiKey, setGroqApiKey] = useState('');
  const [autoFillSource, setAutoFillSource] = useState(null); // 'kaggle_sample' | 'your_resume' | null

  // Dashboard 3 candidate feature state
  const [candidateFeatures, setCandidateFeatures] = useState({
    years_experience: 4.5,
    skill_count: 7,
    college_tier: 'Tier 1',
    employment_gap_months: 6,
    has_internship: true,
    gpa: 3.8,
    project_count: 4,
    graduation_year: 2023,
    has_referral: false,
    demographic_proxy: 'Group A'
  });

  // Load real Kaggle sample candidate & initial company lookup on mount
  useEffect(() => {
    handleLoadSample();
    axios.post('/api/ats/detect-company', { company_name: companyName })
      .then(res => setDetectedAts(res.data))
      .catch(err => console.error("Initial ATS detect error", err));
  }, []);

  // Fetch real Kaggle sample candidate from dataset
  const handleLoadSample = async () => {
    try {
      const res = await axios.get('/api/resumes/sample');
      if (res.data && res.data.length > 0) {
        const sample = res.data[Math.floor(Math.random() * res.data.length)];
        setResumeText(sample.raw_resume_text);
        setCandidateFeatures({
          years_experience: sample.years_experience,
          skill_count: sample.skill_count,
          college_tier: sample.college_tier,
          employment_gap_months: sample.employment_gap_months,
          has_internship: sample.has_internship,
          gpa: sample.gpa,
          project_count: sample.project_count,
          graduation_year: sample.graduation_year,
          has_referral: sample.has_referral,
          demographic_proxy: sample.demographic_proxy
        });
        setAutoFillSource('kaggle_sample');
      }
    } catch (err) {
      console.error("Failed to load sample Kaggle candidate", err);
    }
  };

  // Switch to ATS Checker from Job Discovery card
  const handleSelectJobForATS = (job) => {
    if (job) {
      if (job.description) setJdText(job.description);
      if (job.companyName) setCompanyName(job.companyName);
      if (job.company) setCompanyName(job.company);
    }
    setActiveTab('ats_checker');
  };

  // Seamless Handoff from ATS Checker to Bias Auditor with Auto-Fill
  const handleHandoffToAudit = (extractedFeatures) => {
    if (extractedFeatures) {
      setCandidateFeatures(prev => ({
        ...prev,
        years_experience: extractedFeatures.years_experience ?? prev.years_experience,
        skill_count: extractedFeatures.skill_count ?? prev.skill_count,
        college_tier: extractedFeatures.college_tier ?? prev.college_tier,
        employment_gap_months: extractedFeatures.employment_gap_months ?? prev.employment_gap_months,
        has_internship: extractedFeatures.has_internship ?? prev.has_internship,
        gpa: extractedFeatures.gpa ?? prev.gpa,
        project_count: extractedFeatures.project_count ?? prev.project_count,
        graduation_year: extractedFeatures.graduation_year ?? prev.graduation_year,
        has_referral: extractedFeatures.has_referral ?? prev.has_referral
      }));
      setAutoFillSource('your_resume');
    }
    setActiveTab('bias_auditor');
  };

  return (
    <div style={{ minHeight: '100vh', display: 'flex', flexDirection: 'column' }}>
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        onLoadSample={handleLoadSample}
        groqApiKey={groqApiKey}
        setGroqApiKey={setGroqApiKey}
      />

      <main style={{ flex: 1, maxWidth: '1280px', width: '100%', margin: '0 auto', padding: '24px' }}>
        {activeTab === 'job_discovery' ? (
          <JobDiscovery
            onSelectJobForATS={handleSelectJobForATS}
            onHandoffToAudit={handleHandoffToAudit}
            groqApiKey={groqApiKey}
          />
        ) : activeTab === 'ats_checker' || activeTab === 'ats' ? (
          <ATSChecker
            resumeText={resumeText}
            setResumeText={setResumeText}
            jdText={jdText}
            setJdText={setJdText}
            careersUrl={careersUrl}
            setCareersUrl={setCareersUrl}
            companyName={companyName}
            setCompanyName={setCompanyName}
            detectedAts={detectedAts}
            setDetectedAts={setDetectedAts}
            parsedData={parsedData}
            setParsedData={setParsedData}
            matchData={matchData}
            setMatchData={setMatchData}
            groqApiKey={groqApiKey}
            onHandoffToAudit={handleHandoffToAudit}
          />
        ) : (
          <BiasAuditor
            candidateFeatures={candidateFeatures}
            setCandidateFeatures={setCandidateFeatures}
            autoFillSource={autoFillSource}
            groqApiKey={groqApiKey}
          />
        )}
      </main>

      <footer style={{
        borderTop: '1px solid var(--border-color)',
        padding: '20px 24px',
        textAlign: 'center',
        fontSize: '0.78rem',
        color: 'var(--text-muted)',
        marginTop: '40px'
      }}>
        GlassBox ATS Reality-Checker & Real Kaggle Resume Bias Auditor — Powered by Two-Tier Company ATS Detection, Plain-Language Groq Summaries, SHAP, LIME, RandomForest, and Groq LLM API.
      </footer>
    </div>
  );
}
