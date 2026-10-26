import React, { useState } from 'react';
import { Search, Check, X, CircleDashed, ExternalLink, ArrowUpRight, ShieldCheck, HelpCircle, Sparkles, MapPin, ScanLine, Clock } from 'lucide-react';
import { api, errorMessage } from '../api';
import { AtsBadge, CompanyLogo, Spinner } from '../components/ui/primitives';
import { atsColor, scoreColor, postedLabel } from '../lib/format';

const QUICK = ['Zepto', 'Razorpay', 'Swiggy', 'Flipkart', 'Adobe', 'Paytm', 'Infosys', 'Freshworks'];
const METHOD = {
  registry: 'Verified job board',
  api_probe: 'Live ATS probe',
  web_fingerprint: 'Careers-page fingerprint',
  ai_estimate: 'AI estimate',
  user_confirmed: 'User confirmed',
  none: 'Nothing found',
};
// [parsing flag, text when true, text when false, is true the resume-friendly value?]
const TRAITS = [
  ['handles_columns', 'Reads two-column layouts correctly', 'Interleaves two-column layouts line by line', true],
  ['handles_tables', 'Keeps table content intact', 'Flattens or skips table cells', true],
  ['drops_icons', 'Drops icons and graphics', 'Keeps icon-adjacent text', false],
  ['strict_headers', 'Needs standard section headings', 'Tolerates creative section headings', false],
  ['drops_header_footer', 'Skips page header/footer text', 'Reads page header/footer text', false],
];

function StatusBadge({ status }) {
  if (status === 'verified') return <span className="badge badge-green"><ShieldCheck size={13} /> Verified</span>;
  if (status === 'estimate') return <span className="badge badge-amber"><Sparkles size={13} /> AI estimate · unverified</span>;
  return <span className="badge badge-neutral"><HelpCircle size={13} /> No ATS found</span>;
}

export default function CompanyView({ analysis, roles, openCheck, notify, meta }) {
  const [q, setQ] = useState('');
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [correction, setCorrection] = useState('');

  const lookup = async (name, refresh = false) => {
    const company = (name ?? q).trim();
    if (!company) return;
    setQ(company);
    setLoading(true);
    setResult(null);
    try {
      setResult(await api.lookupCompany({
        company, refresh, roles,
        skills: (analysis?.profile?.skills || []).map(s => s.name),
        years_experience: analysis?.profile?.years_experience || 0,
      }));
    } catch (err) {
      notify(errorMessage(err), 'error');
    } finally {
      setLoading(false);
    }
  };

  const confirm = async () => {
    if (!correction) return;
    try {
      await api.confirmCompany({ company: result.company, ats_id: correction });
      notify(`Saved: ${result.company} uses ${meta?.ats_profiles?.find(p => p.id === correction)?.name}. Thanks!`);
      lookup(result.company);
    } catch (err) {
      notify(errorMessage(err), 'error');
    }
  };

  const ats = result?.ats;
  const parse = ats && analysis?.ats_scores?.find(s => s.id === ats.id);
  const jobs = result?.india_jobs || [];

  return (
    <div className="container page">
      <section className="hero" style={{ paddingTop: 20 }}>
        <div className="eyebrow">ATS Lookup</div>
        <h2 className="h1" style={{ fontSize: 'clamp(32px, 5vw, 56px)', marginTop: 14 }}>
          Which <span className="serif grad-text">ATS</span> will read<br />your application?
        </h2>
        <p className="lede" style={{ fontSize: 16 }}>
          Name a company. GlassBox checks its verified registry, probes ATS vendors live (including Darwinbox, Keka and Zoho Recruit,
          which are common in India), and fingerprints its careers pages. Every step's evidence is shown. If no ATS turns up, it searches the wider network.
        </p>
        <form className="search-xl" onSubmit={e => { e.preventDefault(); lookup(); }}>
          <input list="company-list" placeholder="e.g. Zepto, Razorpay, Infosys…" value={q} onChange={e => setQ(e.target.value)} aria-label="Company name" />
          <datalist id="company-list">{(meta?.companies || []).map(c => <option key={c.name} value={c.name} />)}</datalist>
          <button className="btn primary lg" type="submit" disabled={loading || !q.trim()}>{loading ? <Spinner /> : <Search size={16} />} Detect</button>
        </form>
        <div className="row wrap" style={{ justifyContent: 'center', gap: 6, marginTop: 14 }}>
          {QUICK.map(c => <button key={c} className="chip sm" onClick={() => lookup(c)}>{c}</button>)}
        </div>
      </section>

      {loading && (
        <div className="card empty">
          <Spinner size={24} />
          <p className="small" style={{ marginTop: 12 }}>Checking the registry → probing 9 ATS vendors → fingerprinting careers pages…</p>
        </div>
      )}

      {result && !loading && (
        <div className="grid-2" style={{ alignItems: 'start' }}>
          <div className="stack">
            <div className="card glow">
              <div className="row" style={{ gap: 14 }}>
                <CompanyLogo domain={result.domain} name={result.company} size={52} />
                <div style={{ flex: 1 }}>
                  <div className="h3" style={{ fontSize: 20 }}>{result.company}</div>
                  <div className="row" style={{ marginTop: 4 }}><StatusBadge status={result.status} />{result.cached && <span className="tiny faint">cached</span>}</div>
                </div>
              </div>
              <div className="divider" />
              {ats ? (
                <div className="row wrap" style={{ gap: 18 }}>
                  <div style={{ flex: 1 }}>
                    <div className="eyebrow">Applicant tracking system</div>
                    <div className="h2" style={{ color: atsColor(ats.id), marginTop: 6 }}>{ats.name}</div>
                    <div className="small muted" style={{ marginTop: 2 }}>{METHOD[result.method]} · {Math.round(result.confidence * 100)}% confidence</div>
                  </div>
                  {parse && (
                    <div style={{ textAlign: 'right' }}>
                      <div className="eyebrow">Your parse survival</div>
                      <div className="fit" style={{ fontSize: 34, color: scoreColor(parse.score), marginTop: 6 }}>{parse.score}</div>
                    </div>
                  )}
                </div>
              ) : (
                <div className="small muted">
                  No public ATS fingerprint was found. The company may run its own portal, hire through job sites,
                  or use an ATS that hides behind its own domain. See where it's hiring below.
                </div>
              )}
              {result.careers_url && (
                <a className="btn sm" style={{ marginTop: 16 }} href={result.careers_url} target="_blank" rel="noreferrer">Careers site <ExternalLink size={13} /></a>
              )}
            </div>

            <div className="card">
              <div className="card-head"><div className="h3">How we know</div></div>
              <div className="timeline">
                {result.evidence.map((e, i) => (
                  <div key={i} className={`tl ${e.outcome}`}>
                    <span className="dot">{e.outcome === 'hit' ? <Check size={14} /> : e.outcome === 'estimate' ? <Sparkles size={13} /> : <X size={13} />}</span>
                    <div>
                      <div className="small"><b style={{ fontWeight: 600 }}>{e.step}</b></div>
                      <div className="small muted">{e.detail}</div>
                      {e.url && <a className="tiny link" href={e.url} target="_blank" rel="noreferrer">{e.url.replace(/^https?:\/\//, '').slice(0, 70)}</a>}
                    </div>
                  </div>
                ))}
              </div>
              <div className="divider" />
              <div className="row wrap" style={{ gap: 8 }}>
                <span className="small muted">Know better?</span>
                <select className="input" style={{ width: 'auto', height: 34, fontSize: 13 }} value={correction} onChange={e => setCorrection(e.target.value)}>
                  <option value="">Set the correct ATS…</option>
                  {(meta?.ats_profiles || []).map(p => <option key={p.id} value={p.id}>{p.name}</option>)}
                </select>
                <button className="btn sm" disabled={!correction} onClick={confirm}>Save</button>
                <button className="btn sm ghost" onClick={() => lookup(result.company, true)}>Re-check</button>
              </div>
            </div>
          </div>

          <div className="stack">
            {ats && (
              <div className="card">
                <div className="card-head"><div className="h3">How {ats.name} reads resumes</div></div>
                <p className="small muted" style={{ marginBottom: 12 }}>{ats.parser_note}</p>
                <div>
                  {TRAITS.map(([k, whenTrue, whenFalse, goodWhenTrue]) => {
                    const val = Boolean(ats.parsing[k]);
                    const good = val === goodWhenTrue;
                    return (
                      <div key={k} className="trait">
                        {good ? <Check size={15} color="var(--lime)" /> : <X size={15} color="var(--amber)" />}
                        <span className={good ? 'muted' : ''}>{val ? whenTrue : whenFalse}</span>
                      </div>
                    );
                  })}
                </div>
                <div className="divider" />
                <div className="small"><b>Screening: </b><span className="muted">{ats.screening}</span></div>
              </div>
            )}

            {jobs.length > 0 && (
              <div className="card">
                <div className="card-head">
                  <div className="h3">Open roles in India</div>
                  <div className="spacer" />
                  <span className="badge badge-neutral">{result.india_jobs_total}</span>
                </div>
                <div className="stack" style={{ gap: 8 }}>
                  {jobs.slice(0, 15).map(j => (
                    <div key={j.id} className="row" style={{ padding: '10px 0', borderTop: '1px solid var(--border)', alignItems: 'flex-start' }}>
                      <div style={{ flex: 1, minWidth: 0 }}>
                        <div className="small" style={{ fontWeight: 500 }}>{j.title}</div>
                        <div className="tiny faint row" style={{ gap: 10 }}>
                          <span className="row" style={{ gap: 3 }}><MapPin size={11} />{j.location}</span>
                          {postedLabel(j.posted_days) && <span className="row" style={{ gap: 3 }}><Clock size={11} />{postedLabel(j.posted_days)}</span>}
                          {j.fit !== undefined && <span style={{ color: scoreColor(j.fit) }}>{j.fit} fit</span>}
                        </div>
                      </div>
                      <button className="btn sm" onClick={() => openCheck({ ...j, domain: j.domain || result.domain })}><ScanLine size={13} /> Check</button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            {(jobs.length === 0) && (
              <div className="card">
                <div className="card-head"><div className="h3">Where {result.company} is hiring</div></div>
                {(result.network_listings || []).length > 0 ? (
                  <div className="stack" style={{ gap: 8, marginBottom: 14 }}>
                    {result.network_listings.slice(0, 8).map(l => (
                      <a key={l.url} href={l.url} target="_blank" rel="noreferrer" className="row" style={{ textDecoration: 'none', padding: '8px 0', borderTop: '1px solid var(--border)' }}>
                        <span className="badge badge-neutral">{l.source}</span>
                        <span className="small" style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.title}</span>
                        <ArrowUpRight size={14} />
                      </a>
                    ))}
                  </div>
                ) : (
                  <p className="small muted" style={{ marginBottom: 12 }}>
                    {ats ? `${ats.name} careers sites don't publish a jobs feed we can read, so search the network instead:` : 'Search the wider network:'}
                  </p>
                )}
                <div className="row wrap" style={{ gap: 8 }}>
                  {(result.search_links || []).map(l => (
                    <a key={l.label} className="btn sm" href={l.url} target="_blank" rel="noreferrer">{l.label} <ArrowUpRight size={13} /></a>
                  ))}
                </div>
                <div className="divider" />
                <button className="btn sm primary" onClick={() => openCheck({ custom: true })}><ScanLine size={14} /> Paste a {result.company} JD to check</button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
