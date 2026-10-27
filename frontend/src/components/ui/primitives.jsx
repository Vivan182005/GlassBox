import React, { useEffect, useState } from 'react';
import { Loader2, X } from 'lucide-react';
import { atsColor, scoreColor, initials } from '../../lib/format';

export function Ring({ value = 0, size = 132, stroke = 5, label, color, sub }) {
  const r = (size - stroke) / 2;
  const c = 2 * Math.PI * r;
  const [shown, setShown] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setShown(value), 60);
    return () => clearTimeout(t);
  }, [value]);
  const col = color || scoreColor(value);
  return (
    <div className="ring" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="#e6dcc8" strokeWidth={stroke} />
        <circle
          cx={size / 2} cy={size / 2} r={r} fill="none" stroke={col} strokeWidth={stroke} strokeLinecap="butt"
          strokeDasharray={c} strokeDashoffset={c * (1 - Math.max(0, Math.min(100, shown)) / 100)}
        />
      </svg>
      <div className="val">
        <b style={{ fontSize: size * 0.27 }}>{Math.round(value)}</b>
        {label && <span className="tiny faint mono">{label}</span>}
        {sub}
      </div>
    </div>
  );
}

export function Bar({ value = 0, color }) {
  const [w, setW] = useState(0);
  useEffect(() => {
    const t = setTimeout(() => setW(value), 60);
    return () => clearTimeout(t);
  }, [value]);
  return (
    <div className="bar">
      <i style={{ width: `${Math.max(2, Math.min(100, w))}%`, background: color || scoreColor(value) }} />
    </div>
  );
}

export function AtsBadge({ id, name, small }) {
  if (!name) return null;
  const col = atsColor(id);
  return (
    <span className="badge" style={{ color: col, borderColor: `${col}44`, background: `${col}12`, height: small ? 22 : 24 }}>
      <span className="dot" style={{ background: col }} />
      {name}
    </span>
  );
}

export function CompanyLogo({ domain, name, size = 46 }) {
  const [failed, setFailed] = useState(!domain);
  if (failed) {
    return <div className="logo fallback" style={{ width: size, height: size }}>{initials(name)}</div>;
  }
  return (
    <div className="logo" style={{ width: size, height: size }}>
      <img
        src={`https://www.google.com/s2/favicons?domain=${domain}&sz=128`}
        alt=""
        onError={() => setFailed(true)}
        style={{ width: size * 0.62, height: size * 0.62 }}
      />
    </div>
  );
}

export function Spinner({ size = 16 }) {
  return <Loader2 size={size} className="spin" />;
}

export function Chip({ children, onRemove, className = '', ...rest }) {
  return (
    <span className={`chip ${className}`} {...rest}>
      {children}
      {onRemove && <X size={13} className="x" onClick={onRemove} aria-label="Remove" />}
    </span>
  );
}

export function Seg({ options, value, onChange }) {
  return (
    <div className="seg" role="tablist">
      {options.map(o => (
        <button key={o.value} className={value === o.value ? 'on' : ''} onClick={() => onChange(o.value)} type="button">
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function Toast({ message, kind, onClose }) {
  useEffect(() => {
    if (!message) return;
    const t = setTimeout(onClose, 6000);
    return () => clearTimeout(t);
  }, [message, onClose]);
  if (!message) return null;
  return <div className={`toast ${kind || ''}`} role="status">{message}</div>;
}

export function AddInput({ placeholder, onAdd, options = [], exclude = [] }) {
  const [v, setV] = useState('');
  const [open, setOpen] = useState(false);
  const [hi, setHi] = useState(0);
  const q = v.trim().toLowerCase();
  const taken = new Set(exclude.map(x => x.toLowerCase()));
  // Prefix matches first, then matches anywhere in the name.
  const matches = options
    .filter(o => !taken.has(o.toLowerCase()) && (!q || o.toLowerCase().includes(q)))
    .sort((a, b) => (b.toLowerCase().startsWith(q) - a.toLowerCase().startsWith(q)))
    .slice(0, 8);
  const add = (val) => {
    if (!val.trim()) return;
    onAdd(val.trim());
    setV('');
    setHi(0);
  };
  return (
    <div className="combo">
      <input
        className="input"
        style={{ height: 30, width: 190, fontSize: 14 }}
        placeholder={placeholder}
        value={v}
        role="combobox"
        aria-expanded={open && matches.length > 0}
        aria-autocomplete="list"
        onFocus={() => setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 120)}
        onChange={e => { setV(e.target.value); setHi(0); setOpen(true); }}
        onKeyDown={e => {
          if (e.key === 'ArrowDown') { e.preventDefault(); setHi(h => Math.min(h + 1, matches.length - 1)); }
          else if (e.key === 'ArrowUp') { e.preventDefault(); setHi(h => Math.max(h - 1, 0)); }
          else if (e.key === 'Escape') setOpen(false);
          else if (e.key === 'Enter') {
            e.preventDefault();
            add(open && q && matches[hi] && matches[hi].toLowerCase().startsWith(q) ? matches[hi] : v);
          }
        }}
      />
      {open && matches.length > 0 && (
        <ul className="combo-list" role="listbox">
          {matches.map((o, i) => (
            <li key={o} role="option" aria-selected={i === hi} className={i === hi ? 'on' : ''}
              onMouseDown={e => { e.preventDefault(); add(o); }} onMouseEnter={() => setHi(i)}>
              {o}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
