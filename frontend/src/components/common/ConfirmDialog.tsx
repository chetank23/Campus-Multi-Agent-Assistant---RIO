import { AlertTriangle, Loader2 } from 'lucide-react';
import { useEffect, useRef } from 'react';

interface ConfirmDialogProps {
  isOpen: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isDestructive?: boolean;
  isProcessing?: boolean;
  processingLabel?: string;
  icon?: React.ReactNode;
  iconContainerClassName?: string;
  onConfirm: () => void;
  onCancel: () => void;
}

export function ConfirmDialog({
  isOpen,
  title,
  message,
  confirmLabel = 'Confirm',
  cancelLabel = 'Cancel',
  isDestructive = true,
  isProcessing = false,
  processingLabel = 'Processing…',
  icon,
  iconContainerClassName,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  const overlayRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && !isProcessing) {
        onCancel();
      }
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, onCancel, isProcessing]);

  if (!isOpen) return null;

  return (
    <div
      ref={overlayRef}
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-xs transition-opacity"
      onClick={(e) => {
        if (e.target === overlayRef.current && !isProcessing) onCancel();
      }}
      role="dialog"
      aria-modal="true"
      aria-labelledby="confirm-dialog-title"
    >
      <div className="bg-white rounded-xl shadow-modal border border-slate-200/90 w-full max-w-md overflow-hidden animate-in fade-in zoom-in-95 duration-150">
        <div className="p-6">
          <div className="flex items-start gap-4">
            <div
              className={`shrink-0 w-10 h-10 rounded-xl flex items-center justify-center ${
                iconContainerClassName
                  ? iconContainerClassName
                  : isDestructive
                    ? 'bg-rose-50 text-rose-600 border border-rose-200/80'
                    : 'bg-primary-50 text-primary-600 border border-primary-200/80'
              }`}
            >
              {icon ?? <AlertTriangle size={20} />}
            </div>
            <div className="min-w-0">
              <h3 id="confirm-dialog-title" className="text-base font-semibold text-slate-900 mb-1.5 tracking-tight">
                {title}
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">{message}</p>
            </div>
          </div>
        </div>
        <div className="bg-slate-50/70 px-6 py-3.5 flex items-center justify-end gap-2.5 border-t border-slate-200/80">
          <button
            type="button"
            onClick={onCancel}
            disabled={isProcessing}
            className="px-3.5 py-2 text-xs font-semibold text-slate-700 bg-white border border-slate-300 rounded-lg hover:bg-slate-50 focus:outline-none focus:ring-2 focus:ring-primary-600 disabled:opacity-50 transition-colors shadow-xs"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            disabled={isProcessing}
            className={`inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white rounded-lg focus:outline-none focus:ring-2 focus:ring-offset-2 disabled:opacity-50 transition-colors shadow-xs ${
              isDestructive
                ? 'bg-rose-600 hover:bg-rose-700 focus:ring-rose-500'
                : 'bg-primary-600 hover:bg-primary-700 focus:ring-primary-500'
            }`}
          >
            {isProcessing && <Loader2 size={13} className="animate-spin" />}
            <span>{isProcessing ? processingLabel : confirmLabel}</span>
          </button>
        </div>
      </div>
    </div>
  );
}
