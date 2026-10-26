import React from 'react';

export default function Footer({ columns }) {
  return (
    <footer className="site-footer">
      <div className="container">
        <div className="inner">
          <div className="brandcol">
            <div className="wordmark">GlassBox</div>
            <p className="small muted" style={{ marginTop: 10, maxWidth: 300 }}>
              See your resume the way the machine does, and find the companies in India worth applying to.
            </p>
          </div>
          {columns.map(col => (
            <nav key={col.title} aria-label={col.title}>
              <h4>{col.title}</h4>
              <ul>
                {col.links.map(l => (
                  <li key={l.label}>
                    <a href={l.href} {...(l.href.startsWith('http') ? { target: '_blank', rel: 'noreferrer' } : {})}>{l.label}</a>
                  </li>
                ))}
              </ul>
            </nav>
          ))}
        </div>
        <div className="legal">
          <span>© 2026 GlassBox. Simulates documented ATS behaviour; not affiliated with any ATS vendor or employer.</span>
          <span>Jobs are read live from public company career boards.</span>
        </div>
      </div>
    </footer>
  );
}
