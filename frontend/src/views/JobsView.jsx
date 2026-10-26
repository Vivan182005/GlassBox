import React, { useEffect, useMemo, useRef, useState } from 'react';
import { Search, MapPin, Clock, ExternalLink, ScanLine, Radar, ArrowUpRight, ClipboardPaste, AlertCircle } from 'lucide-react';
import { api, errorMessage } from '../api';
import { AtsBadge, CompanyLogo, Chip, AddInput, Seg, Spinner } from '../components/ui/primitives';
import { scoreColor, postedLabel, atsColor } from '../lib/format';

const MAIN_CITIES = ['Bengaluru', 'Hyderabad', 'Pune', 'Mumbai', 'Delhi NCR', 'Chennai', 'Remote'];
const MORE_CITIES = ['Kolkata', 'Ahmedabad', 'Jaipur', 'Kochi', 'Coimbatore', 'Chandigarh', 'Indore', 'Mysuru'];
const CITY_ALIASES = { bangalore: 'Bengaluru', bengaluru: 'Bengaluru', gurgaon: 'Delhi NCR', gurugram: 'Delhi NCR', noida: 'Delhi NCR', delhi: 'Delhi NCR', 'new delhi': 'Delhi NCR', bombay: 'Mumbai' };

export function cityFromLocation(loc) {
  const l = (loc || '').toLowerCase();
  for (const [k, v] of Object.entries(CITY_ALIASES)) if (l.includes(k)) return v;
  return [...MAIN_CITIES, ...MORE_CITIES].find(c => l.includes(c.toLowerCase())) || null;
}

function Scanning({ companies }) {
  const [i, setI] = useState(0);
  const [pct, setPct] = useState(4);
  useEffect(() => {
    const t1 = setInterval(() => setI(x => x + 1), 700);
    const t2 = setInterval(() => setPct(p => Math.min(94, p + (100 - p) * 0.06)), 400);
    return () => { clearInterval(t1); clearInterval(t2); };
  }, []);
  const c = companies.length ? companies[i % companies.length] : null;
  return (
    <div className="card glow" style={{ textAlign: 'center', padding: '44px 22px' }}>
      <Radar size={30} className="spin" style={{ animationDuration: '2.4s', color: 'var(--cyan)' }} />
      <div className="h3" style={{ marginTop: 14 }}>Scanning {companies.length || 119} company career sites live…</div>
      <div className="ticker small muted" style={{ marginTop: 8 }}>
        {c && <span key={i}>{c.name} <span className="faint">· {c.ats_name}</span></span>}
      </div>
      <div className="bar" style={{ maxWidth: 380, margin: '18px auto 0' }}><i style={{ width: `${pct}%`, background: 'var(--grad)' }} /></div>
      <p className="tiny faint" style={{ marginTop: 12 }}>The first search reads every board (~20s). Searches after that are cached and near-instant.</p>
    </div>
  );
}

function JobCard({ job, onCheck, delay }) {
  const posted = postedLabel(job.posted_days);
  return (
    <div className="job" style={{ animationDelay: `${delay}ms` }}>
      <CompanyLogo domain={job.domain} name={job.company} />
      <div style={{ minWidth: 0 }}>
        <div className="title">{job.title}</div>
        <div className="meta">
          <span style={{ color: 'var(--text)' }}>{job.company}</span>
          <span className="row" style={{ gap: 4 }}><MapPin size={13} />{job.location}</span>
          {posted && <span className="row" style={{ gap: 4 }}><Clock size={13} />{posted}</span>}
          {job.source === 'network' && <span className="faint">via {job.via}</span>}
        </div>
        <div className="row wrap" style={{ gap: 6, marginTop: 10 }}>
          {job.ats_name ? <AtsBadge id={job.ats_id} name={job.ats_name} small /> : <span className="badge badge-neutral">ATS unknown</span>}
          {job.matched_skills.slice(0, 6).map(s => <span key={s} className="chip sm good">{s}</span>)}
          {job.missing_skills.slice(0, 3).map(s => <span key={s} className="chip sm" title="In the JD, not on your resume">{s}</span>)}
        </div>
        {job.seniority_note && <div className="tiny" style={{ color: 'var(--amber)', marginTop: 8 }}>{job.seniority_note}</div>}
      </div>
      <div className="side">
        <div className="fit" style={{ color: scoreColor(job.fit) }}>{job.fit}<small>fit</small></div>
        <div className="row" style={{ gap: 6 }}>
          {job.url && <a className="btn sm ghost" href={job.url} target="_blank" rel="noreferrer" aria-label="Open posting"><ExternalLink size={14} /></a>}
          <button className="btn sm primary" onClick={() => onCheck(job)}><ScanLine size={14} /> Pass check</button>
        </div>
      </div>
    </div>
  );
}

export default function JobsView({ analysis, roles, setRoles, results, setResults, filters, setFilters, meta, openCheck, notify, goScan }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [atsFilter, setAtsFilter] = useState(null);
  const [sort, setSort] = useState('fit');
  const [shown, setShown] = useState(30);
  const [showMoreCities, setShowMoreCities] = useState(false);
  const [manualSkills, setManualSkills] = useState([]);
  const autoRan = useRef(false);

  const skills = useMemo(
    () => (analysis?.profile?.skills || []).filter(s => s.category !== 'Soft Skills').map(s => s.name).concat(manualSkills),
    [analysis, manualSkills]
  );

  const search = async () => {
    if (!roles.length) {
      notify('Add at least one role to search for.', 'error');
      return;
    }
    setLoading(true);
    setError(null);
    setShown(30);
    setAtsFilter(null);
    try {
      const res = await api.searchJobs({
        roles, skills,
        years_experience: analysis?.profile?.years_experience || 0,
        cities: filters.cities,
        max_age_days: filters.maxAge || null,
      });
      setResults({ ...res, key: JSON.stringify([roles, filters]) });
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (!autoRan.current && roles.length && !results && !loading) {
      autoRan.current = true;
      search();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const toggleCity = (c) => setFilters(f => ({ ...f, cities: f.cities.includes(c) ? f.cities.filter(x => x !== c) : [...f.cities, c] }));
  const stale = results && results.key !== JSON.stringify([roles, filters]);

  const jobs = useMemo(() => {
    let list = results?.jobs || [];
    if (atsFilter) list = list.filter(j => j.ats_name === atsFilter);
    if (sort === 'new') list = [...list].sort((a, b) => (a.posted_days ?? 999) - (b.posted_days ?? 999));
    return list;
  }, [results, atsFilter, sort]);

  return (
    <div className="container page">
      <div className="row wrap" style={{ alignItems: 'flex-end', marginBottom: 22, gap: 16 }}>
        <div>
          <div className="eyebrow">Step 02 · Who's hiring in India</div>
          <h2 className="h2" style={{ marginTop: 8 }}>Live openings that match your <span className="serif grad-text">keywords</span>.</h2>
          <p className="muted small" style={{ marginTop: 6, maxWidth: 640 }}>
            Read straight from each company's own ATS, so you know exactly which system will parse your application.
          </p>
        </div>
        <div className="spacer" />
        <button className="btn" onClick={() => openCheck({ custom: true })}><ClipboardPaste size={15} /> Check a job from elsewhere</button>
      </div>

      {!analysis && (
        <div className="card tight row wrap" style={{ marginBottom: 16, gap: 12, borderColor: 'rgba(255,184,77,0.35)' }}>
          <AlertCircle size={18} color="var(--amber)" />
          <span className="small" style={{ flex: 1 }}>No resume scanned yet. Add roles and skills by hand, or scan your resume for better matching and pass checks.</span>
          <button className="btn sm primary" onClick={goScan}>Scan resume</button>
        </div>
      )}

      <div className="card filters" style={{ marginBottom: 18 }}>
        <div className="filter-row">
          <span className="label eyebrow">Roles</span>
          {roles.map(r => <Chip key={r} onRemove={() => setRoles(roles.filter(x => x !== r))}>{r}</Chip>)}
          <AddInput placeholder="+ Add role" onAdd={r => !roles.includes(r) && setRoles([...roles, r])} />
        </div>
        {!analysis && (
          <div className="filter-row">
            <span className="label eyebrow">Skills</span>
            {manualSkills.map(s => <Chip key={s} onRemove={() => setManualSkills(manualSkills.filter(x => x !== s))}>{s}</Chip>)}
            <AddInput placeholder="+ Add skill" onAdd={s => !manualSkills.includes(s) && setManualSkills([...manualSkills, s])} />
          </div>
        )}
        <div className="filter-row">
          <span className="label eyebrow">Cities</span>
          {[...MAIN_CITIES, ...(showMoreCities ? MORE_CITIES : [])].map(c => (
            <button key={c} className={`chip ${filters.cities.includes(c) ? 'on' : ''}`} onClick={() => toggleCity(c)}>{c}</button>
          ))}
          <button className="btn sm ghost" onClick={() => setShowMoreCities(v => !v)}>{showMoreCities ? 'Fewer' : '+ More cities'}</button>
          {filters.cities.length === 0 && <span className="tiny faint">All of India</span>}
        </div>
        <div className="filter-row">
          <span className="label eyebrow">Posted</span>
          <Seg
            value={filters.maxAge || 0}
            onChange={v => setFilters(f => ({ ...f, maxAge: v }))}
            options={[{ value: 0, label: 'Any time' }, { value: 7, label: '7 days' }, { value: 30, label: '30 days' }, { value: 90, label: '90 days' }]}
          />
          <div className="spacer" />
          <button className="btn primary" onClick={search} disabled={loading || !roles.length}>
            {loading ? <Spinner /> : <Search size={15} />} {results && !stale ? 'Search again' : 'Search jobs'}
          </button>
        </div>
      </div>

      {loading && <Scanning companies={meta?.companies || []} />}

      {error && !loading && (
        <div className="card" style={{ borderColor: 'rgba(255,95,109,0.4)' }}>
          <b>Search failed.</b> <span className="muted small">{error}</span>
        </div>
      )}

      {results && !loading && (
        <>
          <div className="row wrap" style={{ gap: 26, margin: '6px 4px 16px' }}>
            {[
              [results.stats?.postings_scanned, 'India postings scanned'],
              [results.stats?.companies_hiring, 'companies hiring for you'],
              [results.total_matches, 'matching roles'],
              [`${results.stats?.elapsed_seconds}s`, 'search time'],
            ].map(([v, l]) => (
              <div className="stat" key={l}><b style={{ fontSize: 22 }}>{v ?? '—'}</b><span>{l}</span></div>
            ))}
            <div className="spacer" />
            <Seg value={sort} onChange={setSort} options={[{ value: 'fit', label: 'Best fit' }, { value: 'new', label: 'Newest' }]} />
          </div>

          {stale && <div className="tiny" style={{ color: 'var(--amber)', margin: '0 4px 12px' }}>Filters changed. Hit "Search jobs" to refresh the results.</div>}

          {Object.keys(results.stats?.by_ats || {}).length > 0 && (
            <div className="row wrap" style={{ gap: 6, marginBottom: 16 }}>
              <span className="tiny faint" style={{ marginRight: 4 }}>Filter by ATS</span>
              <button className={`chip sm ${!atsFilter ? 'on' : ''}`} onClick={() => setAtsFilter(null)}>All</button>
              {Object.entries(results.stats.by_ats).sort((a, b) => b[1] - a[1]).map(([name, n]) => {
                const id = (results.jobs.find(j => j.ats_name === name) || {}).ats_id;
                return (
                  <button key={name} className={`chip sm ${atsFilter === name ? 'on' : ''}`} onClick={() => setAtsFilter(atsFilter === name ? null : name)}>
                    <span style={{ width: 7, height: 7, borderRadius: 4, background: atsColor(id) }} />{name} <span className="faint mono">{n}</span>
                  </button>
                );
              })}
            </div>
          )}

          {jobs.length === 0 ? (
            <div className="card empty">
              <Search size={28} />
              <div className="h3" style={{ marginTop: 10 }}>No matches in the company network</div>
              <p className="small" style={{ marginTop: 6 }}>{results.message || 'Try another city, a broader role, or the job sites below.'}</p>
            </div>
          ) : (
            <div className="stack" style={{ gap: 12 }}>
              {jobs.slice(0, shown).map((j, i) => <JobCard key={j.id} job={j} onCheck={openCheck} delay={Math.min(i, 10) * 35} />)}
              {jobs.length > shown && (
                <button className="btn" style={{ alignSelf: 'center', marginTop: 8 }} onClick={() => setShown(s => s + 30)}>
                  Show more ({jobs.length - shown} left)
                </button>
              )}
            </div>
          )}

          <div className="card" style={{ marginTop: 22 }}>
            <div className="card-head">
              <Radar size={17} />
              <div className="h3">Keep searching across the network</div>
            </div>
            <p className="small muted" style={{ marginBottom: 12 }}>
              Plenty of Indian companies hire through LinkedIn, Naukri or their own sites rather than a public ATS board.
              Open the same search there, then paste any JD into <b>Check a job from elsewhere</b> to get its pass odds.
            </p>
            <div className="row wrap" style={{ gap: 8 }}>
              {(results.search_links || []).map(l => (
                <a key={l.label} className="btn sm" href={l.url} target="_blank" rel="noreferrer">{l.label} <ArrowUpRight size={13} /></a>
              ))}
            </div>
          </div>
        </>
      )}

      {!results && !loading && !error && (
        <div className="card empty">
          <Search size={28} />
          <div className="h3" style={{ marginTop: 10 }}>Pick your roles and cities, then search</div>
        </div>
      )}
    </div>
  );
}
