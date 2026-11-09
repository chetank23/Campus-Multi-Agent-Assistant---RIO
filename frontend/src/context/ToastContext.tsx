/**
 * frontend/src/context/ToastContext.tsx
 * -------------------------------------
 * Centralized, accessible, and deduplicated Toast notification system.
 * Supports: Success, Error, Warning, Information, and Long-Running Progress.
 * Built-in deduplication prevents toast spamming on rapid double-clicks.
 */

import React, { createContext, useContext, useState, useCallback, useRef, useEffect } from 'react';
import { CheckCircle2, AlertCircle, AlertTriangle, Info, Loader2, X } from 'lucide-react';

export type ToastType = 'success' | 'error' | 'warning' | 'info' | 'progress';

export interface ToastItem {
  id: string;
  key?: string;
  type: ToastType;
  title?: string;
  message: string;
  duration?: number;
  progress?: number;
  action?: {
    label: string;
    onClick: () => void;
  };
  createdAt: number;
}

export interface ToastOptions {
  id?: string;
  key?: string;
  title?: string;
  duration?: number;
  progress?: number;
  action?: {
    label: string;
    onClick: () => void;
  };
}

export interface ToastContextValue {
  toasts: ToastItem[];
  showToast: (type: ToastType, message: string, options?: ToastOptions) => string;
  updateToast: (id: string, updates: Partial<ToastItem>) => void;
  dismissToast: (id: string) => void;
  clearToasts: () => void;
  toast: {
    success: (message: string, options?: ToastOptions) => string;
    error: (message: string, options?: ToastOptions) => string;
    warning: (message: string, options?: ToastOptions) => string;
    info: (message: string, options?: ToastOptions) => string;
    progress: (message: string, options?: ToastOptions) => string;
  };
}

const ToastContext = createContext<ToastContextValue | null>(null);

const DEDUPE_WINDOW_MS = 2500;

export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const recentToastsRef = useRef<Map<string, number>>(new Map());

  const dismissToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const clearToasts = useCallback(() => {
    setToasts([]);
  }, []);

  const updateToast = useCallback((id: string, updates: Partial<ToastItem>) => {
    setToasts((prev) =>
      prev.map((t) => (t.id === id ? { ...t, ...updates } : t))
    );
  }, []);

  const showToast = useCallback(
    (type: ToastType, message: string, options?: ToastOptions): string => {
      const dedupeKey = options?.key || `${type}:${message}`;
      const now = Date.now();
      const lastShown = recentToastsRef.current.get(dedupeKey);

      // Prevent duplicate toasts within dedupe window
      if (lastShown && now - lastShown < DEDUPE_WINDOW_MS) {
        // Return existing or fake id
        return dedupeKey;
      }

      recentToastsRef.current.set(dedupeKey, now);

      const id = options?.id || `toast-${now}-${Math.random().toString(36).substring(2, 7)}`;
      const defaultDuration =
        type === 'error'
          ? 7000
          : type === 'warning'
          ? 5500
          : type === 'progress'
          ? 0 // persistent until updated/dismissed
          : 4000;

      const duration = options?.duration !== undefined ? options.duration : defaultDuration;

      const newToast: ToastItem = {
        id,
        key: dedupeKey,
        type,
        title: options?.title,
        message,
        duration,
        progress: options?.progress,
        action: options?.action,
        createdAt: now,
      };

      setToasts((prev) => {
        // Max 5 simultaneous toasts, keep newest
        const updated = [...prev, newToast];
        if (updated.length > 5) {
          return updated.slice(updated.length - 5);
        }
        return updated;
      });

      // Auto dismiss if duration > 0
      if (duration > 0) {
        setTimeout(() => {
          dismissToast(id);
        }, duration);
      }

      return id;
    },
    [dismissToast]
  );

  const toast = useRef({
    success: (msg: string, opt?: ToastOptions) => showToast('success', msg, opt),
    error: (msg: string, opt?: ToastOptions) => showToast('error', msg, opt),
    warning: (msg: string, opt?: ToastOptions) => showToast('warning', msg, opt),
    info: (msg: string, opt?: ToastOptions) => showToast('info', msg, opt),
    progress: (msg: string, opt?: ToastOptions) => showToast('progress', msg, opt),
  }).current;

  // Clean dedupe cache every 30s
  useEffect(() => {
    const interval = setInterval(() => {
      const now = Date.now();
      recentToastsRef.current.forEach((time, key) => {
        if (now - time > 10000) {
          recentToastsRef.current.delete(key);
        }
      });
    }, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <ToastContext.Provider
      value={{
        toasts,
        showToast,
        updateToast,
        dismissToast,
        clearToasts,
        toast,
      }}
    >
      {children}
      <ToastContainer toasts={toasts} onDismiss={dismissToast} />
    </ToastContext.Provider>
  );
};

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return ctx;
}

// ── Toast Container Component ───────────────────────────────────────────────

const ToastContainer: React.FC<{
  toasts: ToastItem[];
  onDismiss: (id: string) => void;
}> = ({ toasts, onDismiss }) => {
  if (toasts.length === 0) return null;

  return (
    <aside
      aria-label="Notifications"
      className="fixed bottom-5 right-5 z-50 flex flex-col gap-2.5 max-w-sm sm:max-w-md w-full pointer-events-none px-4 sm:px-0"
    >
      {toasts.map((t) => (
        <ToastCard key={t.id} item={t} onDismiss={() => onDismiss(t.id)} />
      ))}
    </aside>
  );
};

const ToastCard: React.FC<{
  item: ToastItem;
  onDismiss: () => void;
}> = ({ item, onDismiss }) => {
  const isError = item.type === 'error';
  const isWarning = item.type === 'warning';
  const isSuccess = item.type === 'success';
  const isProgress = item.type === 'progress';

  const borderClass = isSuccess
    ? 'border-emerald-200 bg-white'
    : isError
    ? 'border-rose-200 bg-white'
    : isWarning
    ? 'border-amber-200 bg-white'
    : isProgress
    ? 'border-indigo-200 bg-white'
    : 'border-blue-200 bg-white';

  const icon = isSuccess ? (
    <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
  ) : isError ? (
    <AlertCircle className="w-5 h-5 text-rose-600 shrink-0 mt-0.5" />
  ) : isWarning ? (
    <AlertTriangle className="w-5 h-5 text-amber-500 shrink-0 mt-0.5" />
  ) : isProgress ? (
    <Loader2 className="w-5 h-5 text-indigo-600 shrink-0 mt-0.5 animate-spin" />
  ) : (
    <Info className="w-5 h-5 text-blue-500 shrink-0 mt-0.5" />
  );

  const defaultTitle = isSuccess
    ? 'Success'
    : isError
    ? 'Error'
    : isWarning
    ? 'Notice'
    : isProgress
    ? 'Processing'
    : 'Information';

  return (
    <div
      role={isError ? 'alert' : 'status'}
      aria-live={isError ? 'assertive' : 'polite'}
      className={`pointer-events-auto rounded-xl border p-4 shadow-modal transition-all transform animate-in slide-in-from-bottom-3 duration-200 flex items-start gap-3 text-slate-800 ${borderClass}`}
    >
      {icon}
      <div className="flex-1 min-w-0 pr-1">
        <h3 className="text-xs font-bold text-slate-900 tracking-tight">
          {item.title || defaultTitle}
        </h3>
        <p className="text-xs text-slate-600 mt-0.5 break-words whitespace-pre-wrap leading-relaxed">
          {item.message}
        </p>
        {isProgress && typeof item.progress === 'number' && (
          <div className="w-full bg-slate-100 rounded-full h-1.5 mt-2 overflow-hidden">
            <div
              className="bg-indigo-600 h-1.5 rounded-full transition-all duration-300"
              style={{ width: `${Math.max(0, Math.min(100, item.progress))}%` }}
            />
          </div>
        )}
        {item.action && (
          <button
            type="button"
            onClick={item.action.onClick}
            className="mt-2 text-xs font-semibold text-primary-700 hover:text-primary-800 underline focus:outline-hidden"
          >
            {item.action.label}
          </button>
        )}
      </div>
      <button
        type="button"
        onClick={onDismiss}
        aria-label="Dismiss notification"
        className="p-1 rounded-md text-slate-400 hover:text-slate-600 hover:bg-slate-100 transition-colors shrink-0"
      >
        <X size={14} />
      </button>
    </div>
  );
};

