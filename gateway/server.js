const express = require('express');
const cors = require('cors');
const http = require('http');
const https = require('https');
require('dotenv').config();

const app = express();
const PORT = process.env.PORT || 5001;
const ML_SERVICE_URL = (process.env.ML_SERVICE_URL || 'https://glassbox-ml-service.onrender.com').replace(/\/$/, '');
const target = new URL(ML_SERVICE_URL);
const transport = target.protocol === 'https:' ? https : http;

const allowedOrigins = process.env.ALLOWED_ORIGINS
  ? process.env.ALLOWED_ORIGINS.split(',').map(o => o.trim())
  : '*';

app.use(cors({ origin: allowedOrigins, credentials: true }));

// Gateway-level health: reports whether the ML service is reachable.
app.get('/api/gateway/health', (req, res) => {
  const probe = transport.get(`${ML_SERVICE_URL}/api/health`, { timeout: 10000 }, upstream => {
    let body = '';
    upstream.on('data', chunk => { body += chunk; });
    upstream.on('end', () => {
      try {
        res.json({ status: 'ok', gateway: 'GlassBox gateway', ml_service: JSON.parse(body) });
      } catch {
        res.json({ status: 'degraded', gateway: 'GlassBox gateway', ml_service_error: 'Unexpected response from ML service' });
      }
    });
  });
  probe.on('timeout', () => probe.destroy(new Error('timeout')));
  probe.on('error', () => {
    res.json({ status: 'degraded', gateway: 'GlassBox gateway', ml_service_error: 'ML service is starting up or unreachable' });
  });
});

// Every other /api request is streamed to the ML service unchanged (JSON and
// multipart uploads alike), so new endpoints need no gateway changes and the
// API keys stay server-side in the ML service's environment.
app.use('/api', (req, res) => {
  const upstream = transport.request(
    {
      protocol: target.protocol,
      hostname: target.hostname,
      port: target.port || (target.protocol === 'https:' ? 443 : 80),
      path: `/api${req.url}`,
      method: req.method,
      headers: { ...req.headers, host: target.host },
      timeout: 120000,
    },
    upstreamRes => {
      res.status(upstreamRes.statusCode || 502);
      for (const [key, value] of Object.entries(upstreamRes.headers)) {
        if (!['access-control-allow-origin', 'access-control-allow-credentials'].includes(key)) {
          res.setHeader(key, value);
        }
      }
      upstreamRes.pipe(res);
    }
  );
  upstream.on('timeout', () => upstream.destroy(new Error('ML service timed out')));
  upstream.on('error', err => {
    console.error(`Gateway proxy error: ${err.message}`);
    if (!res.headersSent) {
      res.status(502).json({ detail: 'The analysis service is waking up or unreachable. Try again in a few seconds.' });
    }
  });
  req.pipe(upstream);
});

app.listen(PORT, () => {
  console.log(`GlassBox gateway on port ${PORT} -> ${ML_SERVICE_URL}`);
});
