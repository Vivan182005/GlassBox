import React, { useCallback, useEffect, useState } from 'react';
import Nav from './components/Nav';
import CheckDrawer from './components/CheckDrawer';
import ApplyDrawer from './components/ApplyDrawer';
import { Toast } from './components/ui/primitives';
import ScanView from './views/ScanView';
import JobsView, { cityFromLocation } from './views/JobsView';
import CompanyView from './views/CompanyView';
import ApplicationsView from './views/ApplicationsView';
import Footer from './components/Footer';
import Assistant from './components/Assistant';
import { useExtension } from './lib/extension';
import { api } from './api';
import { storage } from './lib/format';


const VIEWS = ['scan', 'jobs', 'applications', 'company'];
const viewFromHash = () => {
  const h = window.location.hash.replace('#', '');
  return VIEWS.includes(h) ? h : null;
};

const FOOTER_COLUMNS = [
  {
    title: 'Product',
    links: [
      { label: 'Resume X-ray', href: '#scan' },
      { label: 'Jobs in India', href: '#jobs' },
      { label: 'Applications', href: '#applications' },
      { label: 'ATS Lookup', href: '#company' },
    ],
  },
  {
    title: 'Search India',
    links: [
      { label: 'LinkedIn Jobs', href: 'https://www.linkedin.com/jobs/search/?location=India' },
      { label: 'Naukri', href: 'https://www.naukri.com/' },
      { label: 'Instahyre', href: 'https://www.instahyre.com/' },
      { label: 'Wellfound', href: 'https://wellfound.com/jobs' },
    ],
  },
  {
    title: 'Open source',
    links: [
      { label: 'GitHub', href: 'https://github.com/Vivan182005/GlassBox' },
      { label: 'Methodology', href: 'https://github.com/Vivan182005/GlassBox/blob/main/docs/methodology.md' },
      { label: 'Report an issue', href: 'https://github.com/Vivan182005/GlassBox/issues' },
    ],
  },
];

export default function App() {
  const [view, setView] = useState(() => viewFromHash() || storage.get('gb.view', 'scan'));
  const [analysis, setAnalysis] = useState(() => storage.get('gb.analysis'));
  const [roles, setRoles] = useState(() => storage.get('gb.roles', []));
  const [filters, setFilters] = useState(() => storage.get('gb.filters', { cities: [], maxAge: 0 }));
  const [jobResults, setJobResults] = useState(null);
  const [checkJob, setCheckJob] = useState(null);
  const [applyJob, setApplyJob] = useState(null);
  const [ratings, setRatings] = useState({});
  const [applications, setApplications] = useState(() => storage.get('gb.applications', []));
  const [savedAnswers, setSavedAnswers] = useState(() => storage.get('gb.answers', {}));
  const [sourcePdf, setSourcePdf] = useState(() => storage.get('gb.sourcePdf'));
  const [health, setHealth] = useState(null);
  const [meta, setMeta] = useState(null);
  const [toast, setToast] = useState(null);

  useEffect(() => {
    storage.set('gb.view', view);
    if (window.location.hash !== `#${view}`) window.history.replaceState(null, '', `#${view}`);
    window.scrollTo({ top: 0 });
  }, [view]);

  // Footer and shared links navigate by hash (#jobs, #company, …).
  useEffect(() => {
    const onHash = () => { const v = viewFromHash(); if (v) setView(v); };
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);
  useEffect(() => { storage.set('gb.analysis', analysis); }, [analysis]);
  useEffect(() => { storage.set('gb.roles', roles); }, [roles]);
  useEffect(() => { storage.set('gb.filters', filters); }, [filters]);
  useEffect(() => { storage.set('gb.applications', applications); }, [applications]);
  useEffect(() => { storage.set('gb.answers', savedAnswers); }, [savedAnswers]);
  useEffect(() => { storage.set('gb.sourcePdf', sourcePdf); }, [sourcePdf]);

  // The Autofill extension reports forms the company confirmed as submitted.
  const ext = useExtension();
  useEffect(() => {
    if (!ext.submitted.length) return;
    const sent = new Set(ext.submitted.map(x => x.id));
    setApplications(list => list.some(a => a.status === 'filling' && sent.has(a.id))
      ? list.map(a => (a.status === 'filling' && sent.has(a.id) ? { ...a, status: 'applied' } : a))
      : list);
  }, [ext.submitted]);

  useEffect(() => {
    api.health().then(setHealth).catch(() => setHealth(null));
    api.meta().then(setMeta).catch(() => {});
  }, []);

  const notify = useCallback((message, kind) => setToast({ message, kind }), []);

  const onAnalyzed = (res) => {
    setAnalysis(res);
    setRoles((res.profile?.target_roles || []).slice(0, 3));
    const city = cityFromLocation(res.profile?.location);
    setFilters(f => ({ ...f, cities: city ? [city] : f.cities }));
    setJobResults(null);
    setRatings({});
    window.scrollTo({ top: 0 });
  };

  const reset = () => {
    setAnalysis(null);
    setJobResults(null);
    setRoles([]);
    setView('scan');
  };

  return (
    <>
      <Nav view={view} setView={setView} health={health} />
      <main>
        {view === 'scan' && (
          <ScanView analysis={analysis} onAnalyzed={onAnalyzed} onSourceFile={setSourcePdf} onReset={reset} goJobs={() => setView('jobs')}
            notify={notify} health={health} roles={roles} setRoles={setRoles} />
        )}
        {view === 'jobs' && (
          <JobsView analysis={analysis} roles={roles} setRoles={setRoles} results={jobResults} setResults={setJobResults}
            filters={filters} setFilters={setFilters} meta={meta} openCheck={setCheckJob} openApply={setApplyJob}
            ratings={ratings} setRatings={setRatings} applied={applications} notify={notify} goScan={() => setView('scan')} />
        )}
        {view === 'applications' && (
          <ApplicationsView applications={applications} setApplications={setApplications} goJobs={() => setView('jobs')} />
        )}
        {view === 'company' && <CompanyView analysis={analysis} roles={roles} openCheck={setCheckJob} notify={notify} meta={meta} />}
      </main>
      <Footer columns={FOOTER_COLUMNS} />
      {applyJob && (
        <ApplyDrawer job={applyJob} analysis={analysis} sourcePdf={sourcePdf} cities={filters.cities} savedAnswers={savedAnswers} setSavedAnswers={setSavedAnswers}
          onApplied={(entry) => setApplications(list => [entry, ...list.filter(a => a.id !== entry.id)])}
          onClose={() => setApplyJob(null)} notify={notify} goScan={() => setView('scan')} />
      )}
      {checkJob && <CheckDrawer job={checkJob} analysis={analysis} onClose={() => setCheckJob(null)} notify={notify} goScan={() => setView('scan')} />}
      <Assistant view={view} analysis={analysis} roles={roles} jobResults={jobResults} ratings={ratings}
        applications={applications} focusJob={applyJob || checkJob} />
      <Toast message={toast?.message} kind={toast?.kind} onClose={() => setToast(null)} />
    </>
  );
}
