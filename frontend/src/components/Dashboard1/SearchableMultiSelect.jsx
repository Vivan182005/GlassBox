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
      (s) => s.id === item.id || s.name.toLowerCase() === item.name.toLowerCase()
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
    <div className="flex flex-col gap-2 w-full text-slate-800" ref={dropdownRef}>
      <div className="flex justify-between items-center">
        <label className="text-sm font-semibold text-slate-700 flex items-center gap-1.5">
          {IconComponent && <IconComponent className="w-4 h-4 text-slate-500" />}
          {label}
        </label>
        {maxSelections && (
          <span className="text-xs font-medium text-slate-500 bg-slate-100 px-2 py-0.5 rounded-full">
            {selectedItems.length} / {maxSelections} max
          </span>
        )}
      </div>

      {/* Selected Chips Area */}
      <div className="flex flex-wrap gap-2 min-h-[42px] p-2 bg-slate-50/80 border border-slate-200 rounded-xl transition-all">
        {selectedItems.length === 0 ? (
          <span className="text-xs text-slate-400 italic self-center px-1">
            No items selected yet. Search below to add from database.
          </span>
        ) : (
          selectedItems.map((item) => (
            <span
              key={item.id}
              className={`inline-flex items-center gap-1.5 px-3 py-1 text-xs font-medium rounded-lg shadow-sm border transition-all ${
                item.is_ai_extracted
                  ? 'bg-amber-50 text-amber-900 border-amber-200'
                  : 'bg-white text-slate-800 border-slate-200'
              }`}
            >
              {item.is_ai_extracted && (
                <span className="inline-flex items-center gap-0.5 px-1.5 py-0.2 text-[10px] uppercase font-bold bg-amber-200/70 text-amber-800 rounded">
                  <Sparkles className="w-2.5 h-2.5" />
                  AI
                </span>
              )}
              <span>{item.name}</span>
              <button
                type="button"
                onClick={() => handleRemoveItem(item.id)}
                className="p-0.5 hover:bg-slate-200/60 rounded-full transition-colors text-slate-400 hover:text-slate-700"
                title="Remove selection"
              >
                <X className="w-3 h-3" />
              </button>
            </span>
          ))
        )}
      </div>

      {/* Dropdown Input Area */}
      <div className="relative">
        <div
          onClick={() => !isMaxReached && setIsOpen(true)}
          className={`flex items-center border bg-white rounded-xl px-3.5 py-2.5 shadow-sm transition-all cursor-pointer ${
            isOpen ? 'ring-2 ring-indigo-500/20 border-indigo-500' : 'border-slate-200 hover:border-slate-300'
          } ${isMaxReached ? 'bg-slate-100 cursor-not-allowed opacity-75' : ''}`}
        >
          <Search className="w-4 h-4 text-slate-400 mr-2 shrink-0" />
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
            className="w-full bg-transparent text-sm text-slate-800 placeholder-slate-400 outline-none"
          />
          {loading ? (
            <Loader2 className="w-4 h-4 text-indigo-500 animate-spin ml-2 shrink-0" />
          ) : (
            <ChevronDown className={`w-4 h-4 text-slate-400 ml-2 transition-transform duration-200 ${isOpen ? 'rotate-180' : ''}`} />
          )}
        </div>

        {/* Dropdown Results List */}
        {isOpen && (
          <div className="absolute z-50 left-0 right-0 mt-1.5 bg-white border border-slate-200 rounded-xl shadow-xl max-h-60 overflow-y-auto divide-y divide-slate-100 animate-in fade-in slide-in-from-top-2 duration-150">
            {loading && options.length === 0 ? (
              <div className="p-4 text-center text-xs text-slate-500 flex items-center justify-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin text-indigo-500" />
                Searching Supabase database...
              </div>
            ) : options.length === 0 ? (
              <div className="p-4 text-center text-xs text-slate-500">
                No matching taxonomy records found in database.
              </div>
            ) : (
              options.map((option) => {
                const isSelected = selectedItems.some(
                  (s) => s.id === option.id || s.name.toLowerCase() === option.name.toLowerCase()
                );
                return (
                  <button
                    key={option.id}
                    type="button"
                    disabled={isSelected}
                    onClick={() => handleSelectItem(option)}
                    className={`w-full text-left px-4 py-2.5 flex items-center justify-between text-xs transition-colors ${
                      isSelected
                        ? 'bg-slate-50 text-slate-400 cursor-default'
                        : 'hover:bg-indigo-50/70 text-slate-700 font-medium'
                    }`}
                  >
                    <div className="flex flex-col">
                      <span className="font-semibold text-slate-800">{option.name}</span>
                      {(option.category || option.city || option.country) && (
                        <span className="text-[11px] text-slate-400">
                          {option.category || `${option.city || ''}, ${option.country || ''}`}
                        </span>
                      )}
                    </div>
                    {isSelected && <Check className="w-4 h-4 text-indigo-600 shrink-0" />}
                  </button>
                );
              })
            )}
          </div>
        )}
      </div>

      {helpText && <p className="text-[11px] text-slate-500 flex items-center gap-1"><AlertCircle className="w-3 h-3 text-slate-400" /> {helpText}</p>}
    </div>
  );
}
