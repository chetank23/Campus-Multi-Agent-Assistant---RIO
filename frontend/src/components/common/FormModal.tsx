import React, { useEffect, useRef } from 'react';
import { X } from 'lucide-react';
import { IconButton } from './IconButton';

interface FormModalProps {
  isOpen: boolean;
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  onClose: () => void;
  children: React.ReactNode;
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';
  contentClassName?: string;
}

const maxWidthStyles = {
  sm: 'max-w-sm',
  md: 'max-w-md',
  lg: 'max-w-lg',
  xl: 'max-w-xl',
  '2xl': 'max-w-2xl',
};

export function FormModal({
  isOpen,
  title,
  subtitle,
  icon,
  onClose,
  children,
  maxWidth = 'lg',
  contentClassName,
}: FormModalProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        onClose();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 sm:p-6 bg-slate-900/50 backdrop-blur-xs transition-opacity"
      onClick={(e) => {
        if (e.target === overlayRef.current) onClose();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-title"
    >
      <div
        className={`bg-white rounded-xl shadow-modal border border-[#E4EAF2] w-full ${maxWidthStyles[maxWidth]} overflow-hidden flex flex-col max-h-[90vh] animate-in fade-in zoom-in-95 duration-150`}
      >
        <div className="px-6 py-4 border-b border-[#E4EAF2] flex items-center justify-between shrink-0 bg-[#F8FAFC]">
          <div className="flex items-center gap-3.5">
            {icon && (
              <div className="w-10 h-10 rounded-xl bg-blue-50 text-blue-600 flex items-center justify-center shrink-0 border border-blue-100 shadow-2xs">
                {icon}
              </div>
            )}
            <div>
              <h2 id="modal-title" className="text-base font-bold text-[#111D35] tracking-tight">
                {title}
              </h2>
              {subtitle && (
                <p className="text-xs text-[#536783] mt-0.5">{subtitle}</p>
              )}
            </div>
          </div>
          <IconButton
            icon={<X size={16} />}
            aria-label="Close dialog"
            variant="ghost"
            size="sm"
            onClick={onClose}
          />
        </div>
        <div className={`p-6 overflow-y-auto ${contentClassName || ''}`}>
          {children}
        </div>
      </div>
    </div>
  );
}
