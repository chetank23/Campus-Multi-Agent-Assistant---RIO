import React from 'react';

export type IconButtonVariant = 'default' | 'primary' | 'danger' | 'ghost';
export type IconButtonSize = 'sm' | 'md' | 'lg';

interface IconButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  icon: React.ReactNode;
  'aria-label': string;
  variant?: IconButtonVariant;
  size?: IconButtonSize;
  title?: string;
}

const variantStyles: Record<IconButtonVariant, string> = {
  default: 'text-slate-500 hover:text-slate-800 hover:bg-slate-100 border border-slate-200/80 bg-white shadow-xs',
  primary: 'text-primary-700 hover:text-primary-800 hover:bg-primary-50 border border-primary-200/80 bg-white shadow-xs',
  danger: 'text-rose-600 hover:text-rose-700 hover:bg-rose-50 border border-rose-200/80 bg-white shadow-xs',
  ghost: 'text-slate-400 hover:text-slate-700 hover:bg-slate-100/80 border-transparent bg-transparent',
};

const sizeStyles: Record<IconButtonSize, string> = {
  sm: 'p-1 rounded-md text-xs',
  md: 'p-1.5 rounded-lg text-sm',
  lg: 'p-2 rounded-lg text-base',
};

export const IconButton = React.forwardRef<HTMLButtonElement, IconButtonProps>(
  (
    {
      icon,
      'aria-label': ariaLabel,
      variant = 'default',
      size = 'md',
      title,
      className = '',
      disabled,
      ...props
    },
    ref
  ) => {
    return (
      <button
        ref={ref}
        type="button"
        title={title || ariaLabel}
        aria-label={ariaLabel}
        disabled={disabled}
        className={`inline-flex items-center justify-center transition-colors focus:outline-none focus:ring-2 focus:ring-primary-600 focus:ring-offset-1 disabled:opacity-40 disabled:cursor-not-allowed ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
        {...props}
      >
        {icon}
      </button>
    );
  }
);

IconButton.displayName = 'IconButton';
