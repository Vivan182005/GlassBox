export const ATS_COLORS = {
  workday: '#f5a524',
  greenhouse: '#3ecf8e',
  lever: '#8f9cff',
  ashby: '#c58cff',
  smartrecruiters: '#38bdf8',
  icims: '#f472b6',
  taleo: '#fb7185',
  oracle: '#f87171',
  successfactors: '#60a5fa',
  darwinbox: '#2dd4bf',
  keka: '#a3e635',
  zoho_recruit: '#facc15',
  freshteam: '#34d399',
  eightfold: '#818cf8',
  phenom: '#fb923c',
  generic: '#94a3b8',
};

export const atsColor = (id) => ATS_COLORS[id] || ATS_COLORS.generic;

export const scoreColor = (s) => (s >= 75 ? 'var(--lime)' : s >= 55 ? 'var(--amber)' : 'var(--red)');

export const verdictLabel = {
  pass: 'Likely to get through',
  borderline: 'Borderline: could go either way',
  fail: 'Likely to be filtered out',
};

export const postedLabel = (days) => {
  if (days === null || days === undefined) return null;
  if (days <= 0) return 'Today';
  if (days === 1) return 'Yesterday';
  if (days < 30) return `${days}d ago`;
  if (days < 365) return `${Math.round(days / 30)}mo ago`;
  return '1y+ ago';
};

export const initials = (name = '') =>
  name.split(/\s+/).filter(Boolean).slice(0, 2).map(w => w[0]?.toUpperCase()).join('') || '?';

export const storage = {
  get(key, fallback = null) {
    try {
      const raw = window.localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      if (value === null || value === undefined) window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      /* storage unavailable (private mode / quota); state just won't persist */
    }
  },
};
