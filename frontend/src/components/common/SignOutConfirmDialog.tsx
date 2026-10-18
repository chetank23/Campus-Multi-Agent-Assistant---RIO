/**
 * components/common/SignOutConfirmDialog.tsx
 * -------------------------------------------
 * Reusable sign-out confirmation modal shared across ADMIN, FACULTY, and STUDENT portals.
 * Standardizes title, message, logout icon, accessible backdrop/escape behavior,
 * and single-submission safeguards.
 */

import React from 'react';
import { LogOut } from 'lucide-react';
import { ConfirmDialog } from './ConfirmDialog';

export interface SignOutConfirmDialogProps {
  isOpen: boolean;
  isProcessing?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export const SignOutConfirmDialog: React.FC<SignOutConfirmDialogProps> = ({
  isOpen,
  isProcessing = false,
  onConfirm,
  onCancel,
}) => {
  return (
    <ConfirmDialog
      isOpen={isOpen}
      title="Sign out of RIO-MJP?"
      message="Are you sure you want to sign out of your account? You'll need to sign in again to access your portal."
      confirmLabel="Sign Out"
      cancelLabel="Cancel"
      isDestructive={true}
      isProcessing={isProcessing}
      processingLabel="Signing out…"
      icon={<LogOut size={18} className="text-slate-700" />}
      iconContainerClassName="bg-slate-100 text-slate-700 border border-slate-200/80"
      onConfirm={onConfirm}
      onCancel={onCancel}
    />
  );
};
