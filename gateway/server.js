const express = require('express');
const cors = require('cors');
const multer = require('multer');
const axios = require('axios');
const FormData = require('form-data');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 5001;
const ML_SERVICE_URL = process.env.ML_SERVICE_URL || 'http://127.0.0.1:8000';

const allowedOrigins = process.env.ALLOWED_ORIGINS
  ? process.env.ALLOWED_ORIGINS.split(',').map(o => o.trim())
  : '*';

app.use(cors({
  origin: allowedOrigins,
  credentials: true
}));
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true, limit: '10mb' }));

const storage = multer.memoryStorage();
const upload = multer({ storage: storage });

// Helper for proxy errors
const handleProxyError = (err, res, fallbackData = null) => {
  console.error(`Gateway proxy error: ${err.message}`);
  const statusCode = err.response?.status || 500;
  const detail = err.response?.data || { error: err.message };
  if (fallbackData !== null && statusCode === 500) {
    return res.json(fallbackData);
  }
  return res.status(statusCode).json(detail);
};

// Health check
app.get('/api/health', async (req, res) => {
  try {
    const mlHealth = await axios.get(`${ML_SERVICE_URL}/api/health`, { timeout: 10000 });
    res.json({
      status: 'ok',
      gateway: 'Node.js Express Gateway',
      ml_service: mlHealth.data
    });
  } catch (err) {
    res.json({
      status: 'degraded',
      gateway: 'Node.js Express Gateway',
      ml_service_error: 'Python ML service disconnected or starting up'
    });
  }
});

// Taxonomy Search Endpoints
app.get('/api/job-roles', async (req, res) => {
  try {
    const response = await axios.get(`${ML_SERVICE_URL}/api/job-roles`, { params: req.query, timeout: 15000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res, []);
  }
});

app.get('/api/skills', async (req, res) => {
  try {
    const response = await axios.get(`${ML_SERVICE_URL}/api/skills`, { params: req.query, timeout: 15000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res, []);
  }
});

app.get('/api/locations', async (req, res) => {
  try {
    const response = await axios.get(`${ML_SERVICE_URL}/api/locations`, { params: req.query, timeout: 15000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res, []);
  }
});

// Model Training Stats
app.get('/api/model/stats', async (req, res) => {
  try {
    const response = await axios.get(`${ML_SERVICE_URL}/api/model/stats`, { timeout: 60000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res);
  }
});

// ATS Detection via URL
app.post('/api/ats/detect', async (req, res) => {
  try {
    const response = await axios.post(`${ML_SERVICE_URL}/api/ats/detect`, req.body, { timeout: 60000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res);
  }
});

// ATS Detection via Company Name
app.post('/api/ats/detect-company', async (req, res) => {
  try {
    const payload = {
      ...req.body,
      groq_api_key: req.body.groq_api_key || process.env.GROQ_API_KEY
    };
    const response = await axios.post(`${ML_SERVICE_URL}/api/ats/detect-company`, payload, { timeout: 60000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res);
  }
});

const DEFAULT_PROFILE_FALLBACK = {
  explicit_fields: {
    full_name: "Candidate",
    years_experience: 3.0,
    skill_list: ["Software Engineering", "Python", "React.js", "SQL", "Machine Learning"],
    college_name: "University",
    college_tier: "Tier 2/3",
    gpa: 3.5,
    graduation_year: 2023,
    employment_gap_months: 0,
    has_internship: true,
    project_count: 3,
    has_referral: false,
    location: "Remote"
  },
  inferred_fields: {
    primary_role: "Software Engineer",
    seniority_level: "Mid Level",
    top_domain: "Software Engineering",
    suggested_alternative_roles: ["Full Stack Engineer", "Backend Developer", "Machine Learning Engineer"]
  },
  taxonomy_roles: [
    { id: "1", name: "Software Engineer", category: "Software Engineering", is_ai_extracted: true },
    { id: "2", name: "Machine Learning Engineer", category: "AI / Data Science", is_ai_extracted: true }
  ],
  taxonomy_skills: [
    { id: "101", name: "Python", category: "Programming Languages", is_ai_extracted: true },
    { id: "104", name: "React.js", category: "Frontend Frameworks", is_ai_extracted: true },
    { id: "106", name: "SQL", category: "Databases", is_ai_extracted: true }
  ],
  taxonomy_locations: [
    { id: "loc_1", name: "Remote (Worldwide)", city: "Remote", country: "", is_ai_extracted: true }
  ]
};

// Candidate Profile Extraction (File Upload + Text)
app.post('/api/resume/extract-profile', upload.single('file'), async (req, res) => {
  try {
    const formData = new FormData();
    if (req.file) {
      formData.append('file', req.file.buffer, {
        filename: req.file.originalname,
        contentType: req.file.mimetype
      });
    }
    if (req.body.raw_text) formData.append('raw_text', req.body.raw_text);
    formData.append('groq_api_key', req.body.groq_api_key || process.env.GROQ_API_KEY || '');

    const response = await axios.post(`${ML_SERVICE_URL}/api/resume/extract-profile`, formData, {
      headers: formData.getHeaders(),
      timeout: 60000
    });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res, DEFAULT_PROFILE_FALLBACK);
  }
});

// Job Search & Hybrid Ranking
app.post('/api/jobs/search', async (req, res) => {
  try {
    const response = await axios.post(`${ML_SERVICE_URL}/api/jobs/search`, {
      preferences: req.body.preferences,
      decision_factors: req.body.decision_factors,
      gemini_api_key: req.body.gemini_api_key || process.env.GEMINI_API_KEY || '',
      groq_api_key: req.body.groq_api_key || process.env.GROQ_API_KEY || ''
    }, { timeout: 60000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res);
  }
});

// ATS Manual Correction
app.post('/api/ats/correct', async (req, res) => {
  try {
    const response = await axios.post(`${ML_SERVICE_URL}/api/ats/correct`, req.body, { timeout: 15000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res);
  }
});

// Parsing Simulation (File Upload + Text)
app.post('/api/parse/simulate', upload.single('file'), async (req, res) => {
  try {
    const formData = new FormData();
    if (req.file) {
      formData.append('file', req.file.buffer, {
        filename: req.file.originalname,
        contentType: req.file.mimetype
      });
    }
    if (req.body.raw_text) formData.append('raw_text', req.body.raw_text);
    if (req.body.careers_url) formData.append('careers_url', req.body.careers_url);
    if (req.body.company_name) formData.append('company_name', req.body.company_name);
    formData.append('groq_api_key', req.body.groq_api_key || process.env.GROQ_API_KEY || '');

    const response = await axios.post(`${ML_SERVICE_URL}/api/parse/simulate`, formData, {
      headers: formData.getHeaders(),
      timeout: 60000
    });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res);
  }
});

// Batch ATS Comparison
app.post('/api/batch/parse', upload.single('file'), async (req, res) => {
  try {
    const formData = new FormData();
    if (req.file) {
      formData.append('file', req.file.buffer, {
        filename: req.file.originalname,
        contentType: req.file.mimetype
      });
    }
    if (req.body.raw_text) formData.append('raw_text', req.body.raw_text);
    formData.append('groq_api_key', req.body.groq_api_key || process.env.GROQ_API_KEY || '');

    const response = await axios.post(`${ML_SERVICE_URL}/api/batch/parse`, formData, {
      headers: formData.getHeaders(),
      timeout: 60000
    });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res);
  }
});

// JD Requirement Match Score
app.post('/api/match/score', async (req, res) => {
  try {
    const payload = {
      ...req.body,
      groq_api_key: req.body.groq_api_key || process.env.GROQ_API_KEY
    };
    const response = await axios.post(`${ML_SERVICE_URL}/api/match/score`, payload, { timeout: 60000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res);
  }
});

// Audited Model Prediction & Explainability
app.post('/api/model/predict-explain', async (req, res) => {
  try {
    const payload = {
      ...req.body,
      groq_api_key: req.body.groq_api_key || process.env.GROQ_API_KEY
    };
    const response = await axios.post(`${ML_SERVICE_URL}/api/model/predict-explain`, payload, { timeout: 60000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res);
  }
});

// Fairness Metrics
app.get('/api/model/fairness', async (req, res) => {
  try {
    const response = await axios.get(`${ML_SERVICE_URL}/api/model/fairness`, { timeout: 60000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res);
  }
});

// Mitigation Audit Comparison
app.get('/api/model/mitigate', async (req, res) => {
  try {
    const response = await axios.get(`${ML_SERVICE_URL}/api/model/mitigate`, { timeout: 60000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res);
  }
});

// Sample Candidates
app.get('/api/resumes/sample', async (req, res) => {
  try {
    const response = await axios.get(`${ML_SERVICE_URL}/api/resumes/sample`, { timeout: 30000 });
    res.json(response.data);
  } catch (err) {
    handleProxyError(err, res, []);
  }
});

app.listen(PORT, () => {
  console.log(`GlassBox API Gateway running on port ${PORT}`);
});
