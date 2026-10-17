import React from 'react';
import { Search, X } from 'lucide-react';

interface SearchBarProps {
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
  className?: string;
  disabled?: boolean;
}

export const SearchBar: React.FC<SearchBarProps> = ({
  value,
  onChange,
  placeholder = 'Search records…',
  className = '',
  disabled = false,
}) => {
  return (
    <div className={`relative flex items-center ${className}`}>
      <Search
        size={15}
        className="absolute left-3 text-slate-400 pointer-events-none shrink-0"
        aria-hidden="true"
      />
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        disabled={disabled}
        placeholder={placeholder}
        className="w-full pl-9 pr-8 py-1.5 text-xs text-slate-800 bg-white border border-slate-300 rounded-lg placeholder-slate-400 transition-colors focus:outline-none focus:ring-2 focus:ring-primary-600 focus:border-primary-600 disabled:bg-slate-50 disabled:cursor-not-allowed"
      />
      {value && (
        <button
          type="button"
          onClick={() => onChange('')}
          disabled={disabled}
          aria-label="Clear search"
          className="absolute right-2 text-slate-400 hover:text-slate-600 p-0.5 rounded transition-colors focus:outline-none"
        >
          <X size={14} />
        </button>
      )}
    </div>
  );
};
