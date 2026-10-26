import axios from 'axios';

const http = axios.create({ baseURL: import.meta.env.VITE_API_BASE_URL || '', timeout: 180000 });

export const errorMessage = (err) =>
  err?.response?.data?.detail ||
  (err?.code === 'ECONNABORTED' ? 'The request timed out. The service may be waking up, so try again.' : null) ||
  (err?.response ? `Request failed (${err.response.status})` : 'Could not reach the GlassBox service. Is it running?');

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
};

export default http;
