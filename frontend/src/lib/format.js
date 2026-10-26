// Muted heritage tones that read on the paper background.
export const ATS_COLORS = {
  workday: '#b3802f',
  greenhouse: '#3f5d45',
  lever: '#3d4f6b',
  ashby: '#6b4a6b',
  smartrecruiters: '#2f5f6b',
  icims: '#8a4a5a',
  taleo: '#a8442f',
  oracle: '#8f3a2a',
  successfactors: '#41587a',
  darwinbox: '#2f6b60',
  keka: '#5f6b2f',
  zoho_recruit: '#9a6b1f',
  freshteam: '#4a6b4f',
  eightfold: '#55507a',
  phenom: '#a65f2f',
  generic: '#7d6b56',
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

// 1-5 job rating (apply at 4.0+), coloured like the pass scores.
export const ratingColor = (r) => (r >= 4 ? 'var(--lime)' : r >= 3.5 ? 'var(--amber)' : 'var(--red)');

export const APPLY_THRESHOLD = 4.0;

export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}
