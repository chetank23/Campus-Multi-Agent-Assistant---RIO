import React, { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  LogOut,
  ChevronDown,
  Menu,
  Shield,
  Building,
  Search,
  Calendar,
  X,
  Loader2,
  BookOpen,
  GraduationCap,
  Users,
  DoorOpen,
  FlaskConical,
  Layers,
} from 'lucide-react';
import { useAuth } from '@/auth/useAuth';
import { academicYearsApi } from '@/api/academicYears';
import { searchApi, type GlobalSearchResultItem, type SearchEntityType } from '@/api/search';
import { SignOutConfirmDialog } from '@/components/common';
import { NotificationBellDropdown } from '@/components/notifications/NotificationBellDropdown';
import type { UserRole } from '@/auth/auth.types';

interface TopbarProps {
  title?: string;
  onToggleMobile?: () => void;
}

const roleLabel: Record<UserRole, string> = {
  SUPER_ADMIN: 'Super Administrator',
  ADMIN: 'System Admin',
  FACULTY: 'Faculty Member',
  STUDENT: 'Enrolled Student',
};

const ENTITY_ICON_MAP: Record<SearchEntityType, React.ReactNode> = {
  student: <Users size={14} className="text-blue-600 shrink-0" />,
  faculty: <GraduationCap size={14} className="text-indigo-600 shrink-0" />,
  department: <Building size={14} className="text-sky-600 shrink-0" />,
  program: <Layers size={14} className="text-violet-600 shrink-0" />,
  course: <BookOpen size={14} className="text-emerald-600 shrink-0" />,
  room: <DoorOpen size={14} className="text-amber-600 shrink-0" />,
  lab: <FlaskConical size={14} className="text-cyan-600 shrink-0" />,
};

export const Topbar: React.FC<TopbarProps> = ({ onToggleMobile }) => {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [loggingOut, setLoggingOut] = useState(false);
  const [showSignOutConfirm, setShowSignOutConfirm] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [searchTerm, setSearchTerm] = useState('');
  const [searchResults, setSearchResults] = useState<GlobalSearchResultItem[]>([]);
  const [searchOpen, setSearchOpen] = useState(false);
  const [searchLoading, setSearchLoading] = useState(false);
  const [searchError, setSearchError] = useState<string | null>(null);
  const [activeIndex, setActiveIndex] = useState<number>(-1);
  const menuRef = useRef<HTMLDivElement>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const searchSeqRef = useRef<number>(0);

  // Fetch real active academic year for context pill
  const { data: academicYears } = useQuery({
    queryKey: ['academicYears'],
    queryFn: academicYearsApi.getAll,
    staleTime: 300_000,
  });

  const activeYear = academicYears?.find((y) => y.is_active) || academicYears?.[0];
  const yearDisplayName = activeYear?.year_name || '2026 – 2027';

  // Close dropdown on outside click or escape
  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
        setMenuOpen(false);
      }
    }
    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        setMenuOpen(false);
      }
    }
    if (menuOpen) {
      document.addEventListener('mousedown', handleClickOutside);
      document.addEventListener('keydown', handleKeyDown);
    }
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
      document.removeEventListener('keydown', handleKeyDown);
    };
  }, [menuOpen]);

  // Close search dropdown on outside click
  useEffect(() => {
    function handleSearchOutside(event: MouseEvent) {
      if (searchRef.current && !searchRef.current.contains(event.target as Node)) {
        setSearchOpen(false);
      }
    }
    document.addEventListener('mousedown', handleSearchOutside);
    return () => document.removeEventListener('mousedown', handleSearchOutside);
  }, []);

  // Debounced role-aware global search with stale-response protection
  useEffect(() => {
    const trimmed = searchTerm.trim();
    if (trimmed.length < 2) {
      return;
    }

    const seq = ++searchSeqRef.current;
    const controller = new AbortController();

    const timer = window.setTimeout(async () => {
      setSearchLoading(true);
      setSearchError(null);
      try {
        const res = await searchApi.search(trimmed, 20, controller.signal);
        if (seq !== searchSeqRef.current) return;
        setSearchResults(res.results);
        setSearchOpen(true);
        setActiveIndex(res.results.length > 0 ? 0 : -1);
      } catch (err: unknown) {
        if (controller.signal.aborted || seq !== searchSeqRef.current) return;
        setSearchError(err instanceof Error ? err.message : 'Search failed. Please try again.');
        setSearchResults([]);
        setSearchOpen(true);
      } finally {
        if (seq === searchSeqRef.current) {
          setSearchLoading(false);
        }
      }
    }, 280);

    return () => {
      window.clearTimeout(timer);
      controller.abort();
    };
  }, [searchTerm]);

  const handleSelectResult = (item: GlobalSearchResultItem) => {
    setSearchOpen(false);
    setActiveIndex(-1);
    navigate(item.route);
  };

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Escape') {
      setSearchOpen(false);
      setActiveIndex(-1);
      return;
    }
    if (!searchOpen || searchResults.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setActiveIndex((prev) => (prev + 1) % searchResults.length);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setActiveIndex((prev) => (prev <= 0 ? searchResults.length - 1 : prev - 1));
    } else if (e.key === 'Enter' && activeIndex >= 0 && searchResults[activeIndex]) {
      e.preventDefault();
      handleSelectResult(searchResults[activeIndex]);
    }
  };

  const handleOpenSignOutConfirm = () => {
    setMenuOpen(false);
    setShowSignOutConfirm(true);
  };

  const handleLogoutConfirm = async () => {
    if (loggingOut) return;
    setLoggingOut(true);
    try {
      await logout();
      setShowSignOutConfirm(false);
    } catch (err) {
      console.error('Logout error:', err);
    } finally {
      setLoggingOut(false);
    }
  };

  if (!user) return null;

  const initials = user.name
    .split(' ')
    .map((n) => n[0])
    .filter(Boolean)
    .join('')
    .toUpperCase()
    .slice(0, 2) || 'AD';

  return (
    <header className="h-[70px] bg-white border-b border-[#E4EAF2] flex items-center justify-between px-4 sm:px-6 shrink-0 sticky top-0 z-30 shadow-[0_1px_2px_rgba(0,0,0,0.02)]">
      {/* Left: Mobile menu toggle + Global Search bar */}
      <div className="flex items-center gap-3 flex-1 min-w-0 mr-4">
        {onToggleMobile && (
          <button
            type="button"
            onClick={onToggleMobile}
            className="lg:hidden p-2 rounded-lg text-[#536783] hover:text-[#111D35] hover:bg-[#F4F7FB] transition-colors focus:outline-none focus:ring-2 focus:ring-[#93B5E8]"
            aria-label="Toggle navigation menu"
          >
            <Menu size={20} />
          </button>
        )}

        <div className="relative w-full max-w-md hidden sm:block" ref={searchRef}>
          <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-[#8190A5]">
            {searchLoading ? <Loader2 size={15} className="animate-spin text-blue-600" /> : <Search size={15} />}
          </div>
          <input
            type="text"
            value={searchTerm}
            onChange={(e) => {
              const val = e.target.value;
              setSearchTerm(val);
              if (val.trim().length < 2) {
                setSearchResults([]);
                setSearchOpen(false);
                setSearchLoading(false);
                setSearchError(null);
                setActiveIndex(-1);
              } else {
                setSearchOpen(true);
              }
            }}
            onFocus={() => {
              if (searchTerm.trim().length >= 2) setSearchOpen(true);
            }}
            onKeyDown={handleSearchKeyDown}
            placeholder="Search for students, faculty, rooms, courses..."
            aria-label="Global search"
            aria-expanded={searchOpen}
            aria-autocomplete="list"
            className="w-full pl-9 pr-8 py-2 bg-[#F4F7FB] border border-[#E4EAF2] rounded-lg text-xs text-[#111D35] placeholder-[#8190A5] focus:outline-none focus:ring-2 focus:ring-[#93B5E8] focus:border-[#2563EB] transition-colors"
          />
          {searchTerm && (
            <button
              type="button"
              onClick={() => {
                setSearchTerm('');
                setSearchResults([]);
                setSearchOpen(false);
                setSearchError(null);
              }}
              aria-label="Clear search"
              className="absolute inset-y-0 right-0 pr-2.5 flex items-center text-[#8190A5] hover:text-[#111D35]"
            >
              <X size={14} />
            </button>
          )}

          {/* Search Results Popover */}
          {searchOpen && searchTerm.trim().length >= 2 && (
            <div
              role="listbox"
              aria-label="Search results"
              className="absolute left-0 right-0 mt-1.5 bg-white border border-[#E4EAF2] rounded-xl shadow-modal z-50 max-h-80 overflow-y-auto divide-y divide-slate-100"
            >
              {searchLoading ? (
                <div className="px-4 py-3 text-xs text-slate-500 flex items-center gap-2">
                  <Loader2 size={14} className="animate-spin text-blue-600" />
                  <span>Searching campus records...</span>
                </div>
              ) : searchError ? (
                <div className="px-4 py-3 text-xs text-rose-600">{searchError}</div>
              ) : searchResults.length === 0 ? (
                <div className="px-4 py-3 text-xs text-slate-500">
                  No matching records found for &ldquo;{searchTerm.trim()}&rdquo;.
                </div>
              ) : (
                searchResults.map((item, idx) => (
                  <button
                    key={`${item.entity_type}-${item.id}`}
                    type="button"
                    role="option"
                    aria-selected={idx === activeIndex}
                    onClick={() => handleSelectResult(item)}
                    className={`w-full text-left px-3.5 py-2.5 flex items-center gap-3 transition-colors ${
                      idx === activeIndex ? 'bg-blue-50' : 'hover:bg-slate-50'
                    }`}
                  >
                    <div className="w-7 h-7 rounded-lg bg-slate-100 flex items-center justify-center shrink-0">
                      {ENTITY_ICON_MAP[item.entity_type]}
                    </div>
                    <div className="min-w-0 flex-1">
                      <p className="text-xs font-semibold text-[#111D35] truncate">{item.title}</p>
                      <p className="text-[11px] text-[#536783] truncate">{item.subtitle}</p>
                    </div>
                    <span className="text-[10px] uppercase font-bold tracking-wider px-2 py-0.5 rounded bg-slate-100 text-slate-600 shrink-0">
                      {item.entity_type}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>
      </div>

      {/* Right: Academic Year Dropdown, Notifications, User Profile */}
      <div className="flex items-center gap-3 sm:gap-4 shrink-0">
        {/* Academic Year Selector Pill */}
        <div className="hidden md:flex items-center gap-2.5 px-3 py-1.5 rounded-lg border border-[#E4EAF2] bg-white hover:bg-[#F8FAFC] transition-colors shadow-2xs">
          <div className="text-[#536783]">
            <Calendar size={15} />
          </div>
          <div className="text-left">
            <span className="text-[10px] uppercase font-semibold text-[#8190A5] tracking-wide block leading-none">
              Academic Year
            </span>
            <span className="text-xs font-bold text-[#111D35] leading-tight block mt-0.5">
              {yearDisplayName}
            </span>
          </div>
          <ChevronDown size={14} className="text-[#8190A5] ml-1" />
        </div>

        {/* Notification Bell Dropdown */}
        <NotificationBellDropdown />

        {/* User Profile Menu */}
        <div className="relative" ref={menuRef}>
          <button
            type="button"
            onClick={() => setMenuOpen((v) => !v)}
            className="flex items-center gap-2.5 rounded-lg p-1.5 hover:bg-[#F4F7FB] transition-colors focus:outline-none focus:ring-2 focus:ring-[#93B5E8]"
            aria-haspopup="true"
            aria-expanded={menuOpen}
          >
            {/* Deep Navy Avatar with bold initials */}
            <div className="w-9 h-9 rounded-full bg-[#10243A] flex items-center justify-center text-white text-xs font-bold shrink-0 shadow-xs ring-1 ring-[#2B4057]/40">
              {initials}
            </div>

            <div className="hidden sm:block text-left">
              <p className="text-xs font-bold text-[#111D35] leading-tight truncate max-w-[140px]">
                {user.name}
              </p>
              <p className="text-[11px] text-[#536783] leading-tight truncate max-w-[140px]">
                {roleLabel[user.role]}
              </p>
            </div>

            <ChevronDown size={14} className="text-[#8190A5] hidden sm:block transition-transform duration-150" />
          </button>

          {/* Profile Dropdown */}
          {menuOpen && (
            <div className="absolute right-0 mt-2 w-64 bg-white rounded-xl shadow-modal border border-[#E4EAF2] z-40 overflow-hidden animate-in fade-in zoom-in-95 duration-100">
              {/* User Identity Header */}
              <div className="p-4 border-b border-[#E4EAF2] bg-[#F8FAFC]">
                <p className="text-xs font-bold text-[#111D35] truncate">{user.name}</p>
                <p className="text-xs text-[#536783] mt-0.5 truncate">{user.email}</p>

                <div className="flex items-center gap-2 mt-2 pt-2 border-t border-[#E4EAF2] text-[11px] text-[#536783]">
                  <Shield size={12} className="text-[#8190A5] shrink-0" />
                  <span>Role: {roleLabel[user.role]}</span>
                </div>
                {user.department_id && (
                  <div className="flex items-center gap-2 mt-1 text-[11px] text-[#536783]">
                    <Building size={12} className="text-[#8190A5] shrink-0" />
                    <span>Dept. #{user.department_id}</span>
                  </div>
                )}
              </div>

              {/* Actions */}
              <div className="p-1.5">
                <button
                  type="button"
                  onClick={handleOpenSignOutConfirm}
                  disabled={loggingOut}
                  className="w-full flex items-center gap-2 px-3 py-2 text-xs font-semibold text-rose-600 hover:bg-rose-50 rounded-lg transition-colors disabled:opacity-50"
                >
                  <LogOut size={14} />
                  <span>Sign out of portal</span>
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      <SignOutConfirmDialog
        isOpen={showSignOutConfirm}
        isProcessing={loggingOut}
        onConfirm={handleLogoutConfirm}
        onCancel={() => setShowSignOutConfirm(false)}
      />
    </header>
  );
};
