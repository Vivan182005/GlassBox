import React, { useState, useEffect, useRef } from 'react';
import { Search, X, Sparkles, ChevronDown, Check, Loader2, AlertCircle } from 'lucide-react';
import axios from 'axios';

export default function SearchableMultiSelect({
  label,
  placeholder = "Search database taxonomy...",
  apiUrl,
  selectedItems = [],
  onItemsChange,
  maxSelections = null,
  icon: IconComponent = Search,
  helpText
}) {
  const [query, setQuery] = useState('');
  const [options, setOptions] = useState([]);
  const [loading, setLoading] = useState(false);
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef(null);

  // Debounced search against Supabase backend taxonomy API
  useEffect(() => {
    let isMounted = true;
    const timer = setTimeout(async () => {
      if (!isOpen) return;
      setLoading(true);
      try {
        const res = await axios.get(apiUrl, { params: { search: query, limit: 15 } });
        if (isMounted && Array.isArray(res.data)) {
          setOptions(res.data);
        }
      } catch (err) {
        console.error(`Taxonomy fetch error for ${apiUrl}:`, err);
      } finally {
        if (isMounted) setLoading(false);
      }
    }, 250);

    return () => {
      isMounted = false;
      clearTimeout(timer);
    };
  }, [query, apiUrl, isOpen]);

  // Handle outside click
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelectItem = (item) => {
    if (maxSelections && selectedItems.length >= maxSelections) {
      alert(`Maximum limit of ${maxSelections} selections reached.`);
      return;
    }
    // Avoid duplicate selection by ID or Name
    const exists = selectedItems.some(
      (s) => (s.id && s.id === item.id) || s.name.toLowerCase() === item.name.toLowerCase()
    );
    if (exists) return;

    const newItem = {
      id: item.id || Date.now(),
      name: item.name,
      category: item.category || item.city || null,
      is_ai_extracted: false
    };

    onItemsChange([...selectedItems, newItem]);
    setQuery('');
    setIsOpen(false);
  };

  const handleRemoveItem = (idToRemove) => {
    onItemsChange(selectedItems.filter((item) => item.id !== idToRemove));
  };

  const isMaxReached = maxSelections && selectedItems.length >= maxSelections;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '8px', width: '100%', position: 'relative' }} ref={dropdownRef}>
      {/* Label Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <label style={{ fontSize: '0.85rem', fontWeight: 600, color: 'var(--text-primary)', display: 'flex', alignItems: 'center', gap: '6px' }}>
          {IconComponent && <IconComponent size={15} style={{ color: 'var(--signal-green)' }} />}
          {label}
        </label>
        {maxSelections && (
          <span style={{
            fontSize: '0.75rem',
            fontWeight: 600,
            color: isMaxReached ? 'var(--signal-amber)' : 'var(--text-muted)',
            background: 'rgba(255,255,255,0.06)',
            padding: '2px 8px',
            borderRadius: '12px',
            border: '1px solid var(--border-color)'
          }}>
            {selectedItems.length} / {maxSelections} max
          </span>
        )}
      </div>

      {/* Selected Chips Area */}
      <div style={{
        display: 'flex',
        flexWrap: 'wrap',
        gap: '6px',
        minHeight: '44px',
        padding: '8px',
        background: 'rgba(0, 0, 0, 0.4)',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
        alignItems: 'center'
      }}>
        {selectedItems.length === 0 ? (
          <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)', fontStyle: 'italic', paddingLeft: '4px' }}>
            No items selected yet. Search below to add from database.
          </span>
        ) : (
          selectedItems.map((item) => (
            <span
              key={item.id || item.name}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '6px',
                padding: '4px 10px',
                fontSize: '0.8rem',
                fontWeight: 500,
                borderRadius: '6px',
                background: item.is_ai_extracted ? 'rgba(245, 158, 11, 0.15)' : 'rgba(255, 255, 255, 0.08)',
                border: item.is_ai_extracted ? '1px solid rgba(245, 158, 11, 0.3)' : '1px solid var(--border-color)',
                color: item.is_ai_extracted ? 'var(--signal-amber)' : 'var(--text-primary)'
              }}
            >
              {item.is_ai_extracted && (
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '2px',
                  padding: '1px 4px',
                  fontSize: '0.65rem',
                  fontWeight: 700,
                  textTransform: 'uppercase',
                  background: 'rgba(245, 158, 11, 0.3)',
                  color: '#fbbf24',
                  borderRadius: '3px'
                }}>
                  <Sparkles size={10} />
                  AI
                </span>
              )}
              <span>{item.name}</span>
              <button
                type="button"
                onClick={() => handleRemoveItem(item.id)}
                style={{
                  background: 'none',
                  border: 'none',
                  color: 'var(--text-muted)',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  padding: '2px',
                  borderRadius: '50%',
                  marginLeft: '2px'
                }}
                onMouseEnter={(e) => e.currentTarget.style.color = 'var(--signal-red)'}
                onMouseLeave={(e) => e.currentTarget.style.color = 'var(--text-muted)'}
                title="Remove selection"
              >
                <X size={13} />
              </button>
            </span>
          ))
        )}
      </div>

      {/* Dropdown Search Input */}
      <div style={{ position: 'relative', width: '100%' }}>
        <div
          onClick={() => !isMaxReached && setIsOpen(true)}
          style={{
            display: 'flex',
            alignItems: 'center',
            background: isMaxReached ? 'rgba(255, 255, 255, 0.03)' : 'rgba(0, 0, 0, 0.5)',
            border: isOpen ? '1px solid var(--border-focus)' : '1px solid var(--border-color)',
            borderRadius: '8px',
            padding: '8px 12px',
            cursor: isMaxReached ? 'not-allowed' : 'pointer',
            opacity: isMaxReached ? 0.6 : 1,
            boxShadow: isOpen ? '0 0 0 2px rgba(255, 255, 255, 0.1)' : 'none',
            transition: 'all 0.2s ease'
          }}
        >
          <Search size={15} style={{ color: 'var(--text-secondary)', marginRight: '8px', flexShrink: 0 }} />
          <input
            type="text"
            value={query}
            disabled={isMaxReached}
            onChange={(e) => {
              setQuery(e.target.value);
              setIsOpen(true);
            }}
            onFocus={() => setIsOpen(true)}
            placeholder={isMaxReached ? `Limit of ${maxSelections} reached` : placeholder}
            style={{
              width: '100%',
              background: 'transparent',
              border: 'none',
              outline: 'none',
              fontSize: '0.85rem',
              color: 'var(--text-primary)',
              fontFamily: 'var(--font-sans)'
            }}
          />
          {loading ? (
            <Loader2 size={15} style={{ color: 'var(--signal-green)', marginLeft: '8px', animation: 'spin 1s linear infinite', flexShrink: 0 }} />
          ) : (
            <ChevronDown size={15} style={{
              color: 'var(--text-secondary)',
              marginLeft: '8px',
              transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)',
              transition: 'transform 0.2s ease',
              flexShrink: 0
            }} />
          )}
        </div>

        {/* Dropdown Options Box */}
        {isOpen && (
          <div style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            zIndex: 9999,
            background: '#111827',
            border: '1px solid var(--border-color)',
            borderRadius: '8px',
            maxHeight: '220px',
            overflowY: 'auto',
            boxShadow: '0 12px 28px rgba(0, 0, 0, 0.6)'
          }}>
            {loading && options.length === 0 ? (
              <div style={{ padding: '12px', textAlign: 'center', fontSize: '0.8rem', color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '8px' }}>
                <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
                Searching Supabase database...
              </div>
            ) : options.length === 0 ? (
              <div style={{ padding: '12px', textAlign: 'center', fontSize: '0.8rem', color: 'var(--text-muted)' }}>
                No matching taxonomy records found in database.
              </div>
            ) : (
              options.map((option) => {
                const isSelected = selectedItems.some(
                  (s) => (s.id && s.id === option.id) || s.name.toLowerCase() === option.name.toLowerCase()
                );
                return (
                  <div
                    key={option.id || option.name}
                    onClick={() => !isSelected && handleSelectItem(option)}
                    style={{
                      padding: '9px 12px',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      fontSize: '0.82rem',
                      cursor: isSelected ? 'default' : 'pointer',
                      background: isSelected ? 'rgba(255,255,255,0.03)' : 'transparent',
                      color: isSelected ? 'var(--text-muted)' : 'var(--text-primary)',
                      borderBottom: '1px solid rgba(255,255,255,0.05)',
                      transition: 'background 0.15s ease'
                    }}
                    onMouseEnter={(e) => {
                      if (!isSelected) e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
                    }}
                    onMouseLeave={(e) => {
                      if (!isSelected) e.currentTarget.style.background = 'transparent';
                    }}
                  >
                    <div style={{ display: 'flex', flexDirection: 'column' }}>
                      <span style={{ fontWeight: 600 }}>{option.name}</span>
                      {(option.category || option.city || option.country) && (
                        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                          {option.category || `${option.city || ''}${option.country ? ', ' + option.country : ''}`}
                        </span>
                      )}
                    </div>
                    {isSelected && <Check size={14} style={{ color: 'var(--signal-green)' }} />}
                  </div>
                );
              })
            )}
          </div>
        )}
      </div>

      {helpText && (
        <p style={{ fontSize: '0.75rem', color: 'var(--text-muted)', display: 'flex', alignItems: 'center', gap: '4px', marginTop: '2px' }}>
          <AlertCircle size={12} style={{ color: 'var(--text-secondary)' }} /> {helpText}
        </p>
      )}
    </div>
  );
}
