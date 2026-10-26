import React from 'react';
import BiasAuditor from '../components/BiasAuditor';

export default function FairnessView({ features, setFeatures, fromResume }) {
  return (
    <div className="container page">
      <div style={{ marginBottom: 22 }}>
        <div className="eyebrow">Fairness Lab</div>
        <h2 className="h2" style={{ marginTop: 8 }}>What if the screener is <span className="serif grad-text">biased</span>?</h2>
        <p className="muted small" style={{ marginTop: 6, maxWidth: 720 }}>
          A deliberately biased screening model, trained on public resume data, audited with SHAP, LIME and fairness metrics.
          It shows how proxies like college tier or a career gap can sway an automated decision, and what a mitigation pass changes.
          It's a demonstration of the auditing technique, not a model of any real employer.
        </p>
      </div>
      <BiasAuditor candidateFeatures={features} setCandidateFeatures={setFeatures} autoFillSource={fromResume ? 'your_resume' : 'kaggle_sample'} />
    </div>
  );
}
