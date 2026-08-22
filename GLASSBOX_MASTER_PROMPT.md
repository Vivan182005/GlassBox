# GLASSBOX MASTER PROMPT
**Read this entire file before touching any code. Trace every change back to a numbered item here. Do not "improve" things this file doesn't mention. Do not delete working logic (ATS probing, SHAP/LIME/ICE, bias injection) to "simplify" — extend it.**

This is not a from-scratch build. GlassBox already has a working three-page app: `frontend/` (React+Vite), `gateway/` (Express proxy), `ml-service/` (FastAPI). The core ML/XAI logic is real (RandomForest + SHAP TreeExplainer + LIME + ICE, genuine two-tier ATS detection). The gaps are UI/UX, explainability rigor, and a handful of concrete bugs. Your job is to close those gaps without regressing what works.

---

## 0. Ground Truth — Confirmed Current State (do not re-derive, just verify)

- **Stack:** React/Vite frontend → Express gateway (`gateway/server.js`) → FastAPI ml-service (`ml-service/main.py`).
- **3 pages, in `Header.jsx` tabs:** `job_discovery` (Dashboard 1: AI Job Discovery), `ats_checker` (Dashboard 2: ATS Checker), `bias_auditor` (Dashboard 3: Bias Auditor). Note the header labels don't match the blueprint's dashboard numbering — fix per Section 3.
- **Groq key handling:** user pastes key in a modal (`Header.jsx`), held in React state, sent per-request as `groq_api_key` in the body/formData. Gateway falls back to `process.env.GROQ_API_KEY` if the client didn't send one. This is already wired correctly through all three components — confirm with a live test before assuming it's broken again.
- **ATS detection (`ml-service/parsing/ats_signatures.py`):** Tier 1 = live probing of real ATS subdomain patterns (`boards.greenhouse.io/{slug}`, `{slug}.myworkdayjobs.com`, etc.) via `urllib.request`, cached to `data/ats_company_cache.json`. Tier 2 = Groq LLM best-guess fallback if Tier 1 finds nothing. This is a legitimate, defensible design — don't replace it, extend it (Section 5).
- **Bias model (`ml-service/bias_model/model_trainer.py`):** RandomForest trained on Kaggle-derived features with an explicit, documented injected-bias logit formula (tier-1 college boost, gap penalty, demographic proxy boost, referral boost, age-proxy penalty via graduation year). This is real, not random.
- **Explainability (`ml-service/explainability/explainer.py`):** Real `shap.TreeExplainer`, real `lime_tabular.LimeTabularExplainer`, real ICE curves via `predict_proba` sweeps. Plain-language summary generated via Groq with a deterministic template fallback if no key is present.
- **Fairness (`ml-service/explainability/fairness.py`):** Real demographic parity difference + disparate impact ratio (80% rule) computed from actual model predictions on the dataframe, not hardcoded.
- **Design system:** `frontend/src/index.css` — dark slate glassmorphism (`#0b0f19` bg, `#1f2937` panels, blur, 3-color signal system green/red/amber). Functional, generic, reads as a stock admin-dashboard template. This is what needs the aesthetic pass.

**Because the ML/XAI backend is already real, do not build a new one. If you find yourself writing a new SHAP explainer or a new bias formula, stop — you're duplicating, not fixing.**

---

## 1. Confirmed Bugs / Gaps (fix these specifically, in this priority order)

1. **`BiasAuditor.jsx` ICE feature selector effect gap.** `useEffect` re-runs `runAudit` on `[candidateFeatures, groqApiKey]` but `selectedIceFeature` is not in the dependency array. Verify whether the ICE dropdown's `onChange` calls `runAudit` directly — if not, changing the dropdown won't refresh the ICE curve until some other state changes. Fix: either add `selectedIceFeature` to the effect deps, or explicitly call `runAudit(candidateFeatures)` in the dropdown's `onChange` handler. Pick the deps-array fix — it's the more correct React pattern and avoids double-calls.
2. **Job-title mismatch between `Header.jsx` and blueprint intent.** Header currently labels: Dashboard 1 = Job Discovery, Dashboard 2 = ATS Checker, Dashboard 3 = Bias Auditor — three dashboards, not two. Decide and lock in one of:
   - (a) Keep three pages, relabel internally as a linear pipeline (Discover → Reality-Check → Audit) rather than "Dashboard N" — Section 3 assumes this.
   - (b) Fold Job Discovery into the ATS Checker page as a "find your target JD" helper step, back to a true two-dashboard product matching the original pitch.
   State your choice explicitly in the PR description — do not silently pick one.
3. **Verify Groq-key propagation end-to-end**, don't assume either "it's broken" or "it's fine." Test: clear the key, hit each of the three POST endpoints that accept `groq_api_key` (`/api/resume/extract-profile`, `/api/match/score`, `/api/model/predict-explain`, `/api/ats/detect-company`, `/api/jobs/search`) and confirm the deterministic fallback (not a silent crash, not a stale cached response) fires cleanly. This was a real, previously-shipped bug class in this codebase — the regression test in Section 6 exists specifically to stop it recurring.
4. **`/api/parse/simulate` has no `groq_api_key` passthrough at all** (see `gateway/server.js` — the formData built for this route never appends a key). If any downstream logic in `degradation_engine.py` / `simulate_degradation` calls Groq, it will silently use only the env var. Audit `parsing/degradation_engine.py` for any Groq calls and wire the key through if so; if it's purely rule-based (no LLM), leave as-is and note that in the PR.
5. **Async / timeout hardening.** `gateway/server.js` proxies with hardcoded timeouts (10s–60s) and synchronous blocking calls through 2 hops. For the heaviest routes (`/api/resume/extract-profile`, `/api/model/predict-explain`, `/api/batch/parse`) either raise the frontend's perceived responsiveness with a loading/streaming state (cheap fix) or convert to a job-polling pattern (correct fix, more work). Minimum bar: every one of these calls must show a real loading state in the UI with elapsed-time feedback, never a frozen button.
6. **`data/ats_company_cache.json` cache has no TTL or invalidation.** A company that migrates ATS platforms will be permanently misreported. Add a `cached_at` timestamp on write and treat entries older than e.g. 90 days as stale (re-probe, don't just trust cache).
7. **No test coverage anywhere in the repo.** Zero `.test.` or `.spec.` files found. Section 6 mandates a minimum test set — this is not optional given the project's known history of shipping silent hardcoded-fallback bugs.

Do a fresh `grep -rn "TODO\|FIXME\|hardcod\|fallback" ml-service/ gateway/ frontend/src` before starting and report anything found that isn't already covered above.

---

## 2. Design Direction — Kill the Generic Admin-Dashboard Look

Current palette (`#0b0f19` / `#1f2937` / blur panels / green-red-amber signals) is a template look — it's the default "AI SaaS dashboard" aesthetic seen in hundreds of portfolio projects. The goal is a design that a recruiter remembers by name.

**Concept: "X-ray / blueprint" visual metaphor**, since the whole product's pitch is literally "seeing through the black box." Apply consistently across all 3 pages:

- **Base palette shift:** move off pure slate-gray toward a cooler, more technical navy-to-cyan family (e.g. deep ink `#0a1128` base, not `#0b0f19` — barely different but intentional, not default-Tailwind-gray). Introduce ONE accent hue used sparingly and meaningfully: a cyan/electric-blue "scan line" accent (`#22d3ee`-ish) reserved specifically for "this is the machine's view" moments (parsing diff highlights, SHAP bars) — so the accent color itself becomes a semantic signal for "machine-eye view," not just decoration.
- **Typography:** keep Inter for UI chrome, but give data/verdicts (match scores, SHAP values, ATS confidence %) a monospace treatment (`JetBrains Mono`, already in the CSS vars but under-used) — reinforces the "raw machine output" feel exactly where it matters most.
- **Signature visual motif:** a literal "scan reveal" — when parsing simulation runs, animate the transition from "what you wrote" to "what survived" as a left-to-right wipe/scan rather than a static side-by-side (small CSS/JS effort, disproportionate memorability payoff, ties directly to the product's core metaphor).
- **Drop the 3-color traffic-light system as the primary signal language.** Green/red/amber for everything (badges, borders, buttons) is what makes dashboards look interchangeable. Keep red/green/amber ONLY for true accept/reject/warning states; everything else (info panels, neutral badges, navigation) should read through typographic weight and the cyan accent, not color-coding.
- **Card elevation:** current glassmorphism (`backdrop-filter: blur(12px)`) is fine structurally — keep it, but reduce border-radius from the generic `12px` rounded-everything look toward sharper `6–8px` corners on data panels specifically (SHAP charts, tables) to reinforce "technical instrument," reserving the softer rounding for conversational/human-facing elements (the plain-language explanation card, onboarding copy).
- Do NOT reach for a from-scratch component library or a redesign so large it risks breaking the working data flow. This is a palette/motif/typography pass on the existing component structure, not a rebuild.

---

## 3. Page-by-Page Redesign Spec

### Page 1 — Job Discovery
- **Problem today:** entry point to the whole pipeline, but has no visible connection to the other two pages until a job card is clicked — the "this is one pipeline, not three tools" story isn't told visually.
- **Add a persistent horizontal pipeline stepper** at the top of all 3 pages (Discover → Reality-Check → Audit), with the current step highlighted and prior steps showing a compact status chip (e.g. "✓ Resume parsed" once Dashboard 2 has run). This single addition does more for the "coherent product, not 3 tools" narrative than any color change — build it first.
- Job cards: keep, but make the "why this match" reasoning (from Groq JD-match) visually primary, not the raw score number — recruiters/interviewers respond more to "here's what the model actually reasoned," matching the project's own thesis.
- Preserve `handleSelectJobForATS` handoff behavior exactly — this is the seam connecting Dashboard 1 → 2, don't touch its contract.

### Page 2 — ATS Checker
- **This page is the product's strongest differentiator — give it the most design budget.**
- Side-by-side diff view: implement the "scan reveal" motif from Section 2 here specifically. Mangled/dropped spans should visually feel *removed by a machine*, not just red-highlighted text (e.g. strikethrough + reduced opacity + a small "⨯ dropped by parser" micro-label on hover, not just color).
- ATS confidence badge: currently binary detected/generic. Surface the **tier** explicitly in the UI copy ("Verified via live endpoint" vs "AI best guess — unverified" vs "Generic fallback") — this transparency about the tool's own uncertainty is a stronger trust signal than hiding it, and it's already computed server-side (`source_tier`, `badge_label` in `ats_signatures.py`) — just wasn't surfaced. Wire it through.
- Missing-requirements list (from `/api/match/score`): per the original blueprint this is the single most "aha" element — it currently has no special visual treatment. Give it a dedicated, prominent card, not a buried list item.
- Preserve `onHandoffToAudit` contract exactly.

### Page 3 — Bias Auditor
- Ground-truth bias disclosure (`fairness.py`'s `ground_truth_bias_disclosure`) is currently returned by the API — confirm it's rendered prominently in the UI, not just available in the payload. This is the single fact that turns "trust me, it's unbiased" into "I can prove my auditor detects a known injected bias" — it must be unmissable, ideally pinned near the verdict, not scrollable-past.
- SHAP waterfall + LIME rules + ICE curve: keep all three, but add a **short one-line framing above each** explaining what question it answers ("SHAP: which factors drove *this* decision" / "LIME: a simplified local explanation of the same decision" / "ICE: how the decision would change if only this one factor moved") — reinforces the XAI-coursework depth the user actually has, for anyone (interviewer) reading without ML background.
- Add the **faithfulness check** described in Section 4 as a new small panel here — this is the single highest-leverage addition for "isn't just some random numbers."

---

## 4. Explainability Rigor — Making It Undeniably Real

The SHAP/LIME/ICE pipeline is already genuine — the risk isn't fabrication, it's that nothing in the UI *proves* to a skeptical viewer that it's genuine. Close that gap:

1. **SHAP–LIME agreement check.** Both methods explain the same prediction from different angles; they should broadly agree on the top 2–3 features. Compute a simple rank-correlation (e.g. Spearman) between SHAP's top features and LIME's `as_list()` output for the same candidate, server-side in `explainer.py`, and surface it as a small "Explanation consistency: 0.82" indicator. This single number is the cheapest, highest-credibility addition in this entire spec — it's the difference between "I plotted SHAP" and "I understand SHAP and validated it."
2. **Model calibration disclosure.** `model_trainer.py` already computes `roc_auc`, `precision`, `recall`, `f1_score` — these currently live only in `/api/model/stats` and may not be user-facing. Surface them plainly near the verdict ("This audit model has 82% test accuracy — verdicts are directional evidence, not certainty") — undercutting your own confidence appropriately is *more* credible to a technical interviewer, not less.
3. **One bias-mitigation pass, with before/after metrics.** Currently the auditor only detects the injected bias — add one mitigation technique (simplest: reweight training samples inversely to group frequency, or drop the demographic-proxy feature and retrain) and show the fairness-metrics delta on a toggle ("Unmitigated" vs "Reweighted"). This turns Dashboard 3 from a detector into an auditor-with-a-remedy, which is a materially stronger portfolio claim.
4. **Do not let the plain-language Groq summary ever contradict the SHAP waterfall.** Right now `generate_plain_language_explanation` derives its "primary factor" independently by re-sorting the waterfall — good — but if Groq is unavailable it falls back to a template that also references `primary['display_name']`. Confirm both paths always cite the *same* top feature as the SHAP waterfall's top feature; add an assertion/test for this (Section 6) since a mismatch here would visibly undercut the whole "explainable" claim.

---

## 5. ATS Detection — Extending the Two-Tier System

Current system (live subdomain probing + Groq guess) is a legitimate, working approach — extend it, don't replace it. Additional signal sources to layer in, roughly in order of implementation cost vs. payoff:

1. **Careers-page HTML scan (cheap, high-value).** When the user pastes a careers URL directly (`/api/ats/detect` path already exists for this), fetch the page and grep for ATS-specific script/iframe signatures beyond just the URL — e.g. Greenhouse embeds `<script src="...greenhouse.io/embed/job_board...">`, Lever embeds `lever.co/js/...`, Workday career pages load from a `wd1.myworkdayjobs.com` iframe even when the outer domain is the company's own. This catches companies that white-label their careers page under their own domain, which pure subdomain-pattern matching misses entirely.
2. **`robots.txt` / sitemap probing.** Many ATS platforms register predictable disallow rules or sitemap paths (e.g. Workday's `/wday/` path structure). Cheap to add as another Tier-1 signal before falling back to the LLM guess.
3. **Job-posting URL structure, not just the careers-page root.** If the user pastes an individual job posting URL rather than the careers homepage, the URL path structure itself is often more diagnostic than the domain (e.g. Greenhouse job URLs follow `boards.greenhouse.io/{company}/jobs/{id}`, Lever follows `jobs.lever.co/{company}/{uuid}`). Add a URL-shape regex layer specifically for posting URLs.
4. **Public BuiltWith-style lookup as an optional Tier-1.5.** Services like BuiltWith or Wappalyzer expose technology-detection APIs (some with free tiers) that can identify ATS platforms from a domain the same way they detect any other web technology. This is legitimate public information (technology fingerprinting from public HTTP responses), not reverse-engineering — keep the methodology-doc framing from `docs/methodology.md` consistent with this addition.
5. **User-submitted corrections feed the cache.** If a user manually confirms/corrects a detected ATS, write that back into `ats_company_cache.json` with a `source: "user_confirmed"` tag and treat it as higher-confidence than either Tier 1 or Tier 2 on future lookups. Cheap, and it's a nice "the tool improves with use" talking point.

None of these require touching the underlying `ATS_SIGNATURES` config structure — they're all additional *detection* signals feeding the same profile lookup, which keeps the "config-driven, extensible" design property the blueprint already called out as an interview talking point.

---

## 6. Minimum Required Test Coverage (new — currently zero tests exist)

Add these before considering any redesign "done." Keep them fast and deterministic — no live network calls in CI, mock Groq/HTTP probing.

- **Regression test for the historical bug class:** assert that when a valid `groq_api_key` is supplied to `/api/model/predict-explain` and `/api/resume/extract-profile`, the response's plain-language/explanation fields do NOT match the known deterministic-fallback template strings verbatim. This directly guards against silently reverting to hardcoded fallback text while appearing to work.
- **SHAP/LIME consistency test:** for a fixed candidate feature vector, assert the SHAP top-1 feature and LIME top-1 feature agree in direction (both push toward Accept or both toward Reject) for at least the clearly-unambiguous synthetic cases (e.g. max-everything candidate should Accept with all-positive top factors).
- **Fairness metrics sanity test:** assert `disparate_impact_ratio` and `demographic_parity_difference` are computed from actual `model.predict()` output on the dataframe (not a stored constant) by mutating the injected-bias formula's `group_a` boost coefficient in a test fixture and confirming the metric changes.
- **ATS cache staleness test:** assert an entry with `cached_at` older than the TTL is re-probed rather than returned as-is.
- **Gateway key-passthrough test:** for every route in `gateway/server.js` that accepts `groq_api_key`, assert the body forwarded to `ML_SERVICE_URL` contains the client-supplied key when present, and falls back to `process.env.GROQ_API_KEY` only when absent.

---

## 7. Explicit Non-Goals (do not do these unless separately asked)

- Do not rewrite the gateway/ml-service split into a single service.
- Do not swap RandomForest for a different model architecture — the model is intentionally simple per the blueprint's own reasoning (explainability is the star, not model complexity).
- Do not add authentication/multi-user support.
- Do not add a database (Postgres/Supabase) — current JSON-file storage is an intentional, disclosed MVP choice per the blueprint.
- Do not touch `docs/methodology.md`'s core disclaimer language ("does not access or reverse-engineer any proprietary employer ATS") — any new detection signal (Section 5) must be added to this doc using the same "publicly observable, not reverse-engineered" framing, not weakened.

---

## 8. Working Process

1. Start with Section 1 (bugs) — these are correctness issues, fix and verify each with a manual test before moving on.
2. Then Section 6 (tests) — lock in the current correct behavior before redesigning anything, so the design pass can't silently reintroduce a regression.
3. Then Section 2–3 (design) — one page at a time, in the order listed (ATS Checker gets the most attention).
4. Then Section 4 (explainability rigor) and Section 5 (ATS detection extensions) — these are additive features, do them last since they're lowest-risk to sequence after the redesign is stable.
5. After each numbered item, state explicitly which item you addressed and what you verified — do not batch silent changes across multiple items in one commit/response.
6. If any instruction in this file conflicts with what you find in the actual code, stop and flag the conflict rather than guessing which one is correct.
