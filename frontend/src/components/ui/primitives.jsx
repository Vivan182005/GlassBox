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

export function AddInput({ placeholder, onAdd }) {
  const [v, setV] = useState('');
  return (
    <input
      className="input"
      style={{ height: 30, width: 170, fontSize: 14 }}
      placeholder={placeholder}
      value={v}
      onChange={e => setV(e.target.value)}
      onKeyDown={e => {
        if (e.key === 'Enter' && v.trim()) {
          onAdd(v.trim());
          setV('');
        }
      }}
    />
  );
}
