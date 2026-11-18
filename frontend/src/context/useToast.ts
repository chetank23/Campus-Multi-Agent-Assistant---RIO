import { useContext } from 'react';
import { ToastContext } from './toastTypes';
import type { ToastType, ToastItem, ToastOptions, ToastContextValue } from './toastTypes';

export function useToast(): ToastContextValue {
  const ctx = useContext(ToastContext);
  if (!ctx) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return ctx;
}

export type { ToastType, ToastItem, ToastOptions, ToastContextValue };
