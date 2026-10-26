import axios from 'axios';

// Production talks to the ML service directly. The old Node gateway was a pure
// pass-through on a second free Render instance, and Render answers 429
// ("hibernate-rate-limited") while a sleeping instance wakes, so it doubled
// the cold-start pain for nothing. VITE_ML_URL overrides; dev uses Vite's proxy.
const BASE = import.meta.env.DEV ? '' : (import.meta.env.VITE_ML_URL || 'https://glassbox-ml-service.onrender.com');

const http = axios.create({ baseURL: BASE, timeout: 180000 });

// Free Render instances sleep after ~15 minutes idle. While one wakes it
// returns 429/502/503/504 or drops the connection, so retry with backoff.
const RETRYABLE = new Set([429, 502, 503, 504]);
const DELAYS = [2000, 4000, 8000, 12000, 15000, 15000];
http.interceptors.response.use(undefined, async (err) => {
  const cfg = err.config;
  const status = err.response?.status;
  const retryable = cfg && (RETRYABLE.has(status) || (!err.response && err.code !== 'ECONNABORTED'));
  if (!retryable) throw err;
  cfg.__try = (cfg.__try || 0) + 1;
  if (cfg.__try > DELAYS.length) throw err;
  await new Promise(r => setTimeout(r, DELAYS[cfg.__try - 1]));
  return http(cfg);
});

export const errorMessage = (err) =>
  err?.response?.data?.detail ||
  (err?.code === 'ECONNABORTED' ? 'The request timed out. The service may be waking up, so try again.' : null) ||
  ([429, 502, 503, 504].includes(err?.response?.status) ? 'The analysis service is still waking up (free hosting sleeps when idle). Give it a minute and try again.' : null) ||
  (err?.response ? `Request failed (${err.response.status})` : 'Could not reach the GlassBox service. It may be waking up, so try again in a minute.');

export const api = {
  health: () => http.get('/api/health').then(r => r.data),
  meta: () => http.get('/api/meta').then(r => r.data),
  analyze: ({ file, text }) => {
    const form = new FormData();
    if (file) form.append('file', file);
    else form.append('raw_text', text);
    return http.post('/api/resume/analyze', form).then(r => r.data);
  },
  atsView: (analysis, atsId) =>
    http.post('/api/resume/ats-view', {
      resume_text: analysis.resume_text,
      naive_text: analysis.naive_text,
      audit: analysis.audit,
      ats_id: atsId,
    }).then(r => r.data),
  searchJobs: (body) => http.post('/api/jobs/search', body).then(r => r.data),
  check: (body) => http.post('/api/check', body).then(r => r.data),
  tailor: (body) => http.post('/api/check/tailor', body).then(r => r.data),
  lookupCompany: (body) => http.post('/api/company/lookup', body).then(r => r.data),
  confirmCompany: (body) => http.post('/api/company/confirm', body).then(r => r.data),
  rateJobs: (body) => http.post('/api/apply/rate', body).then(r => r.data),
  prepareApplication: (body) => http.post('/api/apply/prepare', body).then(r => r.data),
  resumeFile: (ext, body) => http.post(`/api/apply/resume.${ext}`, body, { responseType: 'blob' }).then(r => r.data),
  resumeFileWithHeaders: (ext, body) => http.post(`/api/apply/resume.${ext}`, body, { responseType: 'blob' })
    .then(r => ({ blob: r.data, headers: r.headers })),
  resumeTex: (body) => http.post('/api/apply/resume.tex', body).then(r => r.data),
};

export default http;
