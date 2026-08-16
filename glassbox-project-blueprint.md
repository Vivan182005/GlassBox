# Project Blueprint: GlassBox — ATS Reality-Checker + Explainable Hiring Bias Auditor

> Working name: **GlassBox**. Rename freely — the pitch is "we make the black box of resume screening transparent."
> This document is written to be handed directly to an implementing LLM (e.g. Claude Code) as a build spec. It also doubles as your own reference / interview prep doc.

---

## 1. Elevator Pitch

Every resume a student submits disappears into an ATS (Applicant Tracking System) that parses it into structured data, then often into a scoring/ranking model, before a human ever sees it. Two things go wrong in that pipeline and almost nobody can see either of them:

1. **Parsing failure** — multi-column layouts, tables, icons, and non-standard headers get silently mangled or dropped, so the "resume" the recruiter's system sees isn't the one you wrote.
2. **Decision opacity** — even when parsing works, the scoring/ranking logic that decides who gets forwarded is a black box, and it can encode bias (college-tier proxies, gendered language, name-based ethnicity signals) that nobody audits.

GlassBox is a two-dashboard app that makes both stages visible: first it shows you **what the machine actually extracted from your resume**, then it shows you **why a screening model would rank it the way it did**, using real explainability techniques (SHAP/LIME) instead of guesswork.

**Important framing for interviews and for the README:** GlassBox does not access or reverse-engineer any real company's proprietary ATS or scoring model. Dashboard 1 replicates *publicly documented parsing behaviors* of major ATS platforms. Dashboard 2 trains and audits a *simulated* screening model on public/synthetic data, as a demonstration of the auditing technique — not a claim about any real employer's system. State this explicitly in the UI (a small "How this works" disclosure) and in your resume/interview pitch. This isn't just legal cover — it's *more* impressive to an interviewer that you understand the distinction between "simulating a technique" and "claiming access to private systems."

---

## 2. Why This Problem, Why It's Been Ignored

- Every CS student applying to placements hits this exact wall, repeatedly, and has zero visibility into it — the problem is maximally relatable to any interviewer who has ever hired.
- Companies don't expose ATS internals (no incentive to), so nobody builds tooling here — it's a gap, not a crowded market.
- The fix doesn't require new research — SHAP, LIME, embeddings, and ATS-parsing quirks are all well-documented — it just requires someone to actually assemble it into a coherent, usable pipeline. That's the "it was right in front of us" angle.

---

## 3. Two-Dashboard Architecture

```
┌─────────────────────┐        ┌──────────────────────┐
│  Dashboard 1:        │        │  Dashboard 2:         │
│  ATS Reality-Checker │──────▶│  Bias Auditor          │
│                       │ parsed │                       │
│  input: resume + JD   │ resume │  input: parsed resume  │
│  + company career URL │ (JSON) │  + JD                  │
└─────────────────────┘        └──────────────────────┘
        │                               │
        ▼                               ▼
  ATS detection +              Synthetic screening model
  parsing simulation           + SHAP/LIME explainability
  + JD match score             + fairness metrics
```

Dashboard 1's structured output (the "what the ATS actually sees" JSON) feeds directly into Dashboard 2 as its input — that's the connective tissue that makes this one project instead of two.

---

## 4. Tech Stack (confirmed)

- **Frontend:** React (your usual stack) — two-tab dashboard UI, charts via Recharts or Plotly.
- **Gateway/API:** Node.js/Express — handles auth, file upload, orchestrates calls to the Python service, serves the frontend. **Never call the LLM API directly from the frontend — the key must live only in the Python service's environment, injected server-side.** (You've hit this exact API-key-security issue before — don't repeat it.)
- **ML/NLP microservice:** Python + FastAPI — does parsing simulation, LLM-based extraction/matching, classical model training/inference, SHAP/LIME computation. Communicates with the Node gateway over REST.
- **LLM API:** Groq (`llama-3.3-70b-versatile`, since you already have this pipeline working) — used for structured extraction and JD-match reasoning, not for the audited model itself (see section 6.1). Keep the provider swappable behind a thin wrapper function so you can drop in another provider without touching the rest of the pipeline.
- **Storage:** PostgreSQL for resume/JD/session records; S3-compatible bucket (or local disk for MVP) for uploaded files.
- **Deployment:** Railway/Render for both services, same pattern as RateGuard — you already know this playbook.

---

## 5. Dashboard 1: ATS Reality-Checker

### 5.1 ATS Detection (via careers-page URL pattern matching)

Given a company's careers page URL (user pastes it), detect the ATS via known domain/path signatures:

| ATS | Signature |
|---|---|
| Workday | `myworkdayjobs.com` in URL |
| Greenhouse | `boards.greenhouse.io` or `job-boards.greenhouse.io` |
| Lever | `jobs.lever.co` |
| iCIMS | `*.icims.com` |
| Taleo | `*.taleo.net` |
| SmartRecruiters | `jobs.smartrecruiters.com` |
| SuccessFactors | `*.successfactors.com` |

Build this as a config-driven table (JSON/YAML), not hardcoded ifs — makes it trivial to extend, and it's a nice "extensible design" talking point in interviews. If detection fails (no match / unlisted ATS), fall back to a "generic ATS" parsing profile and say so explicitly in the UI rather than guessing.

### 5.2 Parsing Simulation Engine

For each ATS profile, encode its **documented parsing weaknesses** (these are publicly known from HR-tech literature and widely reported candidate experiences — cite sources in your report, don't fabricate specifics):

- Multi-column layouts → columns get concatenated out of order or merged into unreadable text
- Tables → cell contents lost or flattened without structure
- Text inside images/icons (e.g. a phone icon next to a number) → dropped entirely
- Non-standard section headers (e.g. "What I've Built" instead of "Experience") → not recognized, content misfiled or ignored
- Headers/footers → contact info placed there is frequently dropped
- Fancy date formats → parsed incorrectly or left blank, breaking chronological experience extraction

Implementation: extract the resume (PDF/DOCX) into raw text and layout metadata using `pdfplumber` / `python-docx`, then apply an ATS-profile-specific **degradation function** that mimics the above failure modes on that extracted content. Output: a side-by-side diff view — "what you wrote" vs "what this ATS profile would likely retain" — with mangled/dropped spans highlighted.

### 5.3 JD Match Scoring (Groq-powered)

Instead of an embedding-similarity score, use the LLM as a structured judge — this is more defensible to explain in an interview ("I used the LLM's reasoning, not just a vector distance") and reuses the Groq pipeline you already have working:

- **Step 1 — structured extraction:** prompt Groq to pull the parsed resume and the JD each into a fixed JSON schema (skills list, years of experience, education, key responsibilities/requirements). Force JSON-only output (you've done this pattern before) and validate/parse defensively.
- **Step 2 — match reasoning:** prompt Groq with both structured JSONs, asking for (a) a 0-100 match score, (b) a list of JD requirements with no resume support ("missing"), (c) a one-line rationale per requirement. Again, force strict JSON output so the frontend can render it directly.
- **Step 3 — determinism guard:** LLM scoring is not perfectly repeatable — set `temperature: 0` and, if you want extra rigor for the report, run each score 3x and show the variance. This is a good "I understand LLM limitations" talking point rather than presenting the score as ground truth.
- Missing-requirement list is the single most "aha" moment of the dashboard — make it visually prominent.

Fallback note: if Groq is rate-limited or down, degrade gracefully to a simple keyword-overlap score rather than failing the whole dashboard — worth building this fallback path early, not as an afterthought.

### 5.4 UI

- Upload resume + paste JD + paste/select company careers URL.
- Detected ATS badge (or "generic profile used" note).
- Side-by-side "what you wrote" / "what survived parsing" view, mangled spans highlighted in red.
- Match score gauge + missing-keywords chip list.

---

## 6. Dashboard 2: Explainable Hiring Bias Auditor

### 6.1 Synthetic Screening Model (Kaggle data + Groq feature extraction)

You need a model to audit — since no real company will hand you theirs, build one deliberately, using real resumes but controlled labels:

- **Base data:** Pull a public resume dataset from Kaggle (search "resume dataset" — several exist with hundreds to thousands of real-world-style resumes across categories). This gives you realistic variation in phrasing, formatting, and content that pure synthetic generation wouldn't capture as convincingly.
- **Feature extraction via Groq:** raw resume text is messy — run each Kaggle resume through the same Groq structured-extraction prompt from section 5.3 to pull out clean fields: years of experience, college name (→ map to a tier), employment gaps, skill count, name (for the bias-proxy test only). This is a good design point to cite in interviews: **you use the LLM for understanding unstructured text, and a classical model for the auditable decision** — deliberately not asking SHAP to explain an LLM's raw output, because that's a much harder and different problem than explaining a tabular classifier.
- **Deliberately inject a realistic bias pattern** into how *labels* are generated for training (e.g. slightly favor resumes from a "tier-1 college" list, or penalize employment gaps disproportionately) — documented and disclosed. This is *the whole point*: you need a model with a known, ground-truth bias so you can prove your auditor correctly detects it. This controlled-experiment framing is what shows an interviewer you understand validation, not just building a tool and hoping it works.
- **Model:** Logistic Regression or XGBoost on the Groq-extracted features (years experience, college tier, keyword match count, employment gap length, name-derived proxy features for the bias test only) — keep the model itself simple and interpretable-adjacent; the explainability layer is the star, not the model architecture.
- **Caching note:** Kaggle resumes are static, so run the Groq extraction pass once and cache the structured output (DB or JSON file) — don't re-call the API every time you retrain the classical model. Keeps API costs/rate limits sane and makes retraining fast.

### 6.2 Explainability Layer

- **SHAP** (`shap` library): global feature importance (bar chart) + per-resume waterfall/force plot showing exactly which features pushed a decision toward accept/reject.
- **LIME**: local explanation for a single prediction, as a second lens — useful to show in interviews that you know these two methods answer different questions (global vs local, and different underlying assumptions), straight from your XAI coursework.
- **ICE plots**: for a chosen feature (e.g. "college tier" or "employment gap length"), show how the prediction changes as that one feature varies while others are held fixed — this directly surfaces bias sensitivity, and it's the exact technique from your XAI slides on ICE plots, so you can speak to it fluently.

### 6.3 Fairness Metrics

- **Demographic parity difference** and **disparate impact ratio** computed across your injected proxy groups.
- Present as a simple metrics table + a short plain-English interpretation ("this model accepts Group A at 1.4x the rate of Group B for equivalent qualifications").

### 6.4 UI

- Feed in a resume (can pull straight from Dashboard 1's parsed output) + JD.
- Model verdict (accept/reject + confidence).
- SHAP waterfall plot for this specific resume.
- Global feature importance panel.
- Fairness metrics summary panel with the injected-bias ground truth called out ("this demo model was intentionally trained with X bias — the auditor correctly surfaces it").

---

## 7. Suggested Repo Structure

```
glassbox/
├── frontend/                # React app, two-tab dashboard
├── gateway/                 # Node/Express API gateway
├── ml-service/               # Python FastAPI microservice
│   ├── parsing/               # ATS profiles + degradation engine
│   ├── matching/               # embedding + JD match scoring
│   ├── bias_model/              # training script, saved model artifact
│   ├── explainability/           # SHAP/LIME/ICE computation
│   └── main.py
├── data/                      # synthetic resume/hiring dataset + generation scripts
├── docs/                       # ATS parsing-quirk sources, methodology notes, ethics disclosure
└── docker-compose.yml
```

---

## 8. Depth / Research-Grade Additions (since you're going for portfolio-centerpiece, not MVP)

- Add a **confidence/uncertainty indicator** on the ATS-detection step (URL pattern matching is a heuristic — say so, and consider a fallback "try multiple profiles, show the range of outcomes" mode).
- Write up a short **methodology doc** in `/docs` citing where the ATS parsing-quirk claims come from — this turns "I made stuff up" into "I did the research," which matters a lot if an interviewer digs in.
- Add a **batch mode**: run the same resume against all supported ATS profiles at once, show a comparison table — nice differentiator, not much extra engineering once the single-profile path works.
- Consider a small **user study** (even n=10 classmates) comparing your parsing-degradation predictions against real application outcomes/anecdotes — gives you an actual evaluation section for your report, which most student projects skip entirely.
- Fairness metrics section could extend to **intersectional analysis** (e.g. college tier × gender-coded language combined) if you want to show off — optional, don't let it block shipping the core.

---

## 9. Open Assumptions (flag/confirm before implementation)

- **Which Kaggle resume dataset:** several exist (varying in size, category coverage, and whether they include full text vs summaries). Pick one with full resume text and decent category diversity — search Kaggle for "resume dataset" and eyeball a few before committing, since dataset quality directly determines how convincing your bias-injection demo looks.
- **Groq rate limits during dev:** structured extraction over an entire Kaggle dataset (potentially hundreds/thousands of resumes) means many API calls in a batch job — check current Groq rate limits before running the full extraction pass, and build the caching step (6.1) in from the start so you're not re-burning calls on every run.
- **Auth/multi-user:** not specified — assuming single-user local/demo mode for the portfolio version, with auth as a stretch goal if you want it deployment-ready for others to try.

---

## 10. Interview Talking Points (keep these in your back pocket)

- "I built this because I was living the problem — submitting resumes into systems I had zero visibility into."
- "Dashboard 1 and 2 aren't separate projects bolted together — the parsed output of one is literally the input schema of the other."
- "I deliberately trained the audited model with a known, injected bias so I could prove my explainability layer actually detects what it's supposed to — that's the difference between building a tool and validating one."
- "I used SHAP for global + per-instance importance and LIME for local surrogate explanations because they answer different questions — and ICE plots to show sensitivity to a single feature in isolation." (straight from your XAI coursework — you can go as deep as they want here)
- Be upfront, unprompted, about the "simulated system, not reverse-engineered real ATS" distinction — it preempts the obvious pushback and signals maturity.

---

## 11. Suggested Build Order

1. ATS detection + parsing degradation engine (Dashboard 1 core) — no ML dependencies, fastest to get demo-able.
2. JD match scoring (embeddings) — completes Dashboard 1.
3. Synthetic dataset + bias-injected model training — foundation for Dashboard 2.
4. SHAP/LIME/ICE integration — the explainability payoff.
5. Fairness metrics panel.
6. Wire Dashboard 1 → Dashboard 2 data handoff.
7. Polish UI, write methodology doc, deploy.
