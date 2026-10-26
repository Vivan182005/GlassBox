# GlassBox

**See your resume the way the ATS does.** GlassBox is built for job seekers in India:

1. **Resume X-ray**: upload a PDF/DOCX and see what 15 applicant tracking systems (Workday, Greenhouse, Lever, iCIMS, Taleo, SuccessFactors, and Indian platforms such as Darwinbox, Keka and Zoho Recruit) actually extract. Columns, tables, icons, header/footer contact details, creative headings, scanned PDFs and broken font encodings are measured from the file itself, not guessed.
2. **Jobs in India**: live openings read straight from the career boards of 119 companies hiring in India (Greenhouse, Lever, Ashby, SmartRecruiters and Workday public APIs). Because each job comes from the company's own ATS, the ATS behind every posting is known for certain. Jobs are ranked by role-family match, skill overlap with the full job description, and seniority fit.
3. **ATS pass check**: for any job, GlassBox pulls the recruiter's keywords out of the JD, matches them alias-aware against your resume, checks knockouts (years, degree), simulates parse survival on that company's ATS, and gives a pass estimate with prioritised fixes. Optionally, it rewrites your headline, summary and bullets for the job using only facts already on your resume.
4. **ATS Lookup**: name any company to find which ATS it uses. GlassBox checks the verified registry, probes ATS vendors live (Greenhouse, Lever, Ashby, SmartRecruiters, Darwinbox, Keka, Zoho Recruit, Freshteam, iCIMS), fingerprints careers pages, and only then falls back to a clearly labelled AI estimate. When no ATS turns up, it searches the wider network (LinkedIn, Naukri, Indeed, Instahyre and others).
5. **Fairness Lab**: a deliberately biased screening model audited with SHAP, LIME, ICE plots and fairness metrics, to show how proxies like college tier or a career gap can sway automated decisions.

> GlassBox simulates documented and commonly observed ATS behaviour. It does not access any vendor's or employer's private systems, and its scores are estimates.

## Architecture

```
frontend/   React + Vite. Scan → Jobs → Pass check flow (Vercel)
gateway/    Node/Express streaming proxy; keeps API keys server-side (Render)
ml-service/ FastAPI (Render)
  core/       LLM layer (Groq → Gemini fallback), optional Supabase
  parsing/    resume_reader (layout audit, column-aware text, ATS views), profile_extractor
  ats/        ATS profiles + company → ATS detector with an evidence trail
  jobs/       live board connectors, India discovery + ranking, network search
  matching/   skills lexicon (aliases), per-job ATS pass check + tailoring
  bias_model/, explainability/   Fairness Lab
  data/company_registry.json     the 119 verified company boards
```

## Running locally

```bash
# ML service (Python 3.11+)
cd ml-service && python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
uvicorn main:app --port 8000 --reload

# Gateway
cd gateway && npm install && ML_SERVICE_URL=http://127.0.0.1:8000 npm start   # port 5001

# Frontend (proxies /api to the gateway on :5001)
cd frontend && npm install && npm run dev                                     # http://localhost:3000
```

Tests: `cd ml-service && python -m unittest tests.test_glassbox_core`

## Environment (ml-service/.env)

| Variable | Required | Purpose |
|---|---|---|
| `GROQ_API_KEY` | recommended | Profile extraction, JD keyword extraction, tailoring (default model `openai/gpt-oss-120b`, override with `GROQ_MODEL`) |
| `GEMINI_API_KEY` | optional | Fallback LLM (default `gemini-2.5-flash`, override with `GEMINI_MODEL`) |
| `RAPIDAPI_KEY` | optional | Adds JSearch results (LinkedIn, Naukri, Indeed aggregation) to job search |
| `SUPABASE_URL` / `SUPABASE_ANON_KEY` | optional | Not required; the service runs entirely without it |
| `ALLOWED_ORIGINS` | optional | CORS allow-list |

Without any LLM key everything still works on rule-based fallbacks, with less precise role and keyword extraction.

## Refreshing the company registry

`ml-service/data/company_registry.json` lists boards that were verified to have live India postings. To add a company, add its ATS board slug (for Workday also the `wd` shard, site name and India facet) and confirm `GET /api/jobs/search` returns its jobs.
