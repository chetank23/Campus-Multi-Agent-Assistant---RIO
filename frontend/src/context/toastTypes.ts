import { createContext } from 'react';

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

export const ToastContext = createContext<ToastContextValue | null>(null);
