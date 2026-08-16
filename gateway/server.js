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

// Health check
app.get('/api/health', async (req, res) => {
  try {
    const mlHealth = await axios.get(`${ML_SERVICE_URL}/api/health`, { timeout: 3000 });
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

// Model Training Stats
app.get('/api/model/stats', async (req, res) => {
  try {
    const response = await axios.get(`${ML_SERVICE_URL}/api/model/stats`);
    res.json(response.data);
  } catch (err) {
    res.status(err.response?.status || 500).json({ error: err.message });
  }
});

// ATS Detection via URL
app.post('/api/ats/detect', async (req, res) => {
  try {
    const response = await axios.post(`${ML_SERVICE_URL}/api/ats/detect`, req.body);
    res.json(response.data);
  } catch (err) {
    res.status(err.response?.status || 500).json({ error: err.message });
  }
});

// ATS Detection via Company Name
app.post('/api/ats/detect-company', async (req, res) => {
  try {
    const payload = {
      ...req.body,
      groq_api_key: req.body.groq_api_key || process.env.GROQ_API_KEY
    };
    const response = await axios.post(`${ML_SERVICE_URL}/api/ats/detect-company`, payload);
    res.json(response.data);
  } catch (err) {
    res.status(err.response?.status || 500).json({ error: err.message });
  }
});

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
      headers: formData.getHeaders()
    });
    res.json(response.data);
  } catch (err) {
    res.status(err.response?.status || 500).json({ error: err.message });
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

    const response = await axios.post(`${ML_SERVICE_URL}/api/parse/simulate`, formData, {
      headers: formData.getHeaders()
    });
    res.json(response.data);
  } catch (err) {
    res.status(err.response?.status || 500).json({ error: err.message });
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

    const response = await axios.post(`${ML_SERVICE_URL}/api/batch/parse`, formData, {
      headers: formData.getHeaders()
    });
    res.json(response.data);
  } catch (err) {
    res.status(err.response?.status || 500).json({ error: err.message });
  }
});

// JD Requirement Match Score
app.post('/api/match/score', async (req, res) => {
  try {
    const payload = {
      ...req.body,
      groq_api_key: req.body.groq_api_key || process.env.GROQ_API_KEY
    };
    const response = await axios.post(`${ML_SERVICE_URL}/api/match/score`, payload);
    res.json(response.data);
  } catch (err) {
    res.status(err.response?.status || 500).json({ error: err.message });
  }
});

// Audited Model Prediction & Explainability
app.post('/api/model/predict-explain', async (req, res) => {
  try {
    const payload = {
      ...req.body,
      groq_api_key: req.body.groq_api_key || process.env.GROQ_API_KEY
    };
    const response = await axios.post(`${ML_SERVICE_URL}/api/model/predict-explain`, payload);
    res.json(response.data);
  } catch (err) {
    res.status(err.response?.status || 500).json({ error: err.message });
  }
});

// Fairness Metrics
app.get('/api/model/fairness', async (req, res) => {
  try {
    const response = await axios.get(`${ML_SERVICE_URL}/api/model/fairness`);
    res.json(response.data);
  } catch (err) {
    res.status(err.response?.status || 500).json({ error: err.message });
  }
});

// Sample Candidates
app.get('/api/resumes/sample', async (req, res) => {
  try {
    const response = await axios.get(`${ML_SERVICE_URL}/api/resumes/sample`);
    res.json(response.data);
  } catch (err) {
    res.status(err.response?.status || 500).json({ error: err.message });
  }
});

app.listen(PORT, () => {
  console.log(`GlassBox API Gateway running on port ${PORT}`);
});
