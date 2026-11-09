import React from 'react';

interface BreadcrumbItem {
  label: string;
  href?: string;
}

interface PageHeaderProps {
  title: string;
  subtitle?: string;
  icon?: React.ReactNode;
  badge?: React.ReactNode;
  breadcrumbs?: BreadcrumbItem[];
  actions?: React.ReactNode;
  refresh?: React.ReactNode;
  className?: string;
}

export const PageHeader: React.FC<PageHeaderProps> = ({
  title,
  subtitle,
  icon,
  badge,
  breadcrumbs,
  actions,
  refresh,
  className = '',
}) => {
  return (
    <div className={`space-y-2 mb-6 ${className}`}>
      {breadcrumbs && breadcrumbs.length > 0 && (
        <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-slate-500 mb-1">
          {breadcrumbs.map((crumb, idx) => (
            <React.Fragment key={idx}>
              {idx > 0 && <span className="text-slate-300">/</span>}
              {crumb.href ? (
                <a href={crumb.href} className="hover:text-slate-800 transition-colors">
                  {crumb.label}
                </a>
              ) : (
                <span className="text-slate-700 font-medium">{crumb.label}</span>
              )}
            </React.Fragment>
          ))}
        </nav>
      )}

      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div className="flex items-start gap-3 min-w-0">
          {icon && (
            <div className="w-10 h-10 rounded-xl bg-[#EDF5FF] text-[#1685E8] flex items-center justify-center shrink-0 mt-0.5 border border-[#D8E9FE] shadow-2xs">
              {icon}
            </div>
          )}
          <div className="min-w-0">
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-xl sm:text-2xl font-extrabold tracking-tight text-[#111D35] truncate">
                {title}
              </h1>
              {badge}
            </div>
            {subtitle && (
              <p className="text-xs sm:text-sm text-[#536783] mt-0.5 leading-relaxed max-w-3xl font-medium">
                {subtitle}
              </p>
            )}
          </div>
        </div>

        {(actions || refresh) && (
          <div className="flex items-center gap-2.5 shrink-0 self-start sm:self-center flex-wrap">
            {refresh}
            {actions}
          </div>
        )}
      </div>
    </div>
  );
};
