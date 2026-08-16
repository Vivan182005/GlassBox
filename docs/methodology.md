# GlassBox Methodology & Ethics Disclosure

## 1. ATS Parsing Simulation Methodology

GlassBox Dashboard 1 simulates documented parsing failure modes of Applicant Tracking Systems (ATS).

### Important Disclaimer
> **Notice:** GlassBox does not access, reverse-engineer, or claim access to any proprietary employer ATS software or private scoring model. All parsing rules are synthesized from publicly documented HR-tech research, industry candidate survey findings, and published parser behaviors (e.g. standard PDF text extraction ordering and structure retention heuristics).

### Documented Parsing Weaknesses Implemented

1. **Multi-Column Concatenation**
   - **Mechanism:** Standard text extractors process text left-to-right, top-to-bottom across the entire page geometry. Multi-column layouts (e.g., left sidebar for skills, right column for experience) often get interleaved line-by-line or merged out of chronological order.
   - **Simulation:** Merges horizontal text bounding boxes across column boundaries when column separation width is below standard margin thresholds.

2. **Table Structural Loss**
   - **Mechanism:** Cells in complex HTML or PDF tables are flattened into unstructured continuous text without column/row context.
   - **Simulation:** Strips matrix boundaries and concatenates table cells row-major without delimiter padding.

3. **Header/Footer & Visual Icon Content Loss**
   - **Mechanism:** Key contact info (email, phone, LinkedIn) placed in page headers/footers or preceded by icon graphics rather than explicit text labels (e.g., `Phone:`) are frequently dropped by OCR and standard text parsers.
   - **Simulation:** Drops text blocks located in top/bottom 5% margin bounds and strips symbol/unicode icon prefixes.

4. **Non-Standard Section Headings**
   - **Mechanism:** Parsers look for standardized section headers (`Work Experience`, `Education`, `Skills`, `Projects`). Creative headers like `"What I've Built"` or `"My Journey"` get misclassified or ignored.
   - **Simulation:** Re-attaches unrecognized sections to adjacent generic blocks or drops the section classification entirely.

---

## 2. Explainable AI (XAI) & Algorithmic Fairness Methodology

GlassBox Dashboard 2 audits automated candidate screening decisions using explainability techniques and algorithmic fairness metrics.

### 1. Feature Extraction via LLM
Raw unstructured resume text is converted into tabular features using structured JSON extraction (or deterministic NLP fallback):
- `years_experience`: Continuous (years)
- `college_tier`: Categorical (Tier 1 vs Tier 2/3)
- `skill_count`: Continuous (count of matched domain skills)
- `employment_gap_months`: Continuous (total gap length in months)
- `demographic_proxy`: Categorical (name/language-derived proxy for bias auditing)

### 2. Audited Screening Model
A baseline classifier (XGBoost / Logistic Regression) is trained with controlled, ground-truth injected bias (e.g., artificial boost for Tier 1 colleges, artificial penalty for employment gaps or demographic proxy signals).

### 3. Explainability Techniques

- **SHAP (SHapley Additive exPlanations):** Computes exact Shapley values based on game theory to quantify the positive or negative contribution of each feature to a specific candidate's score.
- **LIME (Local Interpretable Model-agnostic Explanations):** Builds a local linear surrogate model around a candidate's feature vector to explain the local decision boundary.
- **ICE (Individual Conditional Expectation) Plots:** Isolates a single feature (e.g., `employment_gap_months`) and plots the model prediction trajectory across all possible values of that feature while holding all other candidate features fixed.

### 4. Algorithmic Fairness Metrics

- **Demographic Parity Difference:**
  $$\text{DPD} = |P(\hat{Y}=1 | A=0) - P(\hat{Y}=1 | A=1)|$$
  Measures the absolute difference in acceptance rates between privileged and unprivileged demographic proxy groups.

- **Disparate Impact Ratio (80% Rule):**
  $$\text{DI} = \frac{P(\hat{Y}=1 | A=\text{unprivileged})}{P(\hat{Y}=1 | A=\text{privileged})}$$
  A ratio below $0.80$ indicates potential adverse impact under standard employment guidelines.
