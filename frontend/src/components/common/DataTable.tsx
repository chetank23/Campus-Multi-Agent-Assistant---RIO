import React from 'react';
import { Pencil, Trash2 } from 'lucide-react';
import { IconButton } from './IconButton';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { SearchBar } from './SearchBar';

export interface Column<T> {
  header: string;
  accessor?: keyof T;
  render?: (row: T) => React.ReactNode;
  align?: 'left' | 'center' | 'right';
  className?: string;
}

interface DataTableProps<T> {
  columns: Column<T>[];
  data: T[] | undefined;
  isLoading: boolean;
  isError: boolean;
  error?: Error | null;
  onRefresh?: () => void;
  onEdit?: (row: T) => void;
  onDelete?: (row: T) => void;
  keyExtractor: (row: T) => string | number;
  emptyMessage?: string;
  // Optional enterprise visual extensions
  title?: string;
  subtitle?: string;
  searchValue?: string;
  onSearchChange?: (val: string) => void;
  searchPlaceholder?: string;
  actions?: React.ReactNode;
}

export function DataTable<T>({
  columns,
  data,
  isLoading,
  isError,
  error,
  onRefresh,
  onEdit,
  onDelete,
  keyExtractor,
  emptyMessage = 'No records found.',
  title,
  subtitle,
  searchValue,
  onSearchChange,
  searchPlaceholder,
  actions,
}: DataTableProps<T>) {
  if (isError) {
    return (
      <ErrorState
        title="Error loading table records"
        message={error?.message || 'An unexpected error occurred while fetching table records.'}
        onRetry={onRefresh}
      />
    );
  }

  const hasHeaderToolbar = title || subtitle || onSearchChange || actions;
  const colSpanCount = columns.length + (onEdit || onDelete ? 1 : 0);

  return (
    <div className="bg-white rounded-xl shadow-subtle border border-[#E4EAF2] overflow-hidden">
      {hasHeaderToolbar && (
        <div className="p-4 sm:px-6 sm:py-4 border-b border-[#E4EAF2] flex flex-col sm:flex-row sm:items-center justify-between gap-3 bg-white">
          {(title || subtitle) && (
            <div>
              {title && <h3 className="text-sm sm:text-base font-bold text-[#111D35] tracking-tight">{title}</h3>}
              {subtitle && <p className="text-xs text-[#536783] mt-0.5">{subtitle}</p>}
            </div>
          )}
          <div className="flex items-center gap-3 ml-auto w-full sm:w-auto">
            {onSearchChange && (
              <SearchBar
                value={searchValue || ''}
                onChange={onSearchChange}
                placeholder={searchPlaceholder || 'Filter rows…'}
                className="w-full sm:w-64"
              />
            )}
            {actions}
          </div>
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse text-xs">
          <thead>
            <tr className="bg-[#F8FAFC] border-b border-[#E4EAF2]">
              {columns.map((col, idx) => (
                <th
                  key={idx}
                  className={`px-6 py-3.5 text-[11px] font-bold text-[#536783] uppercase tracking-wider whitespace-nowrap ${
                    col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'
                  } ${col.className || ''}`}
                >
                  {col.header}
                </th>
              ))}
              {(onEdit || onDelete) && (
                <th className="px-6 py-3.5 text-[11px] font-bold text-[#536783] uppercase tracking-wider text-right w-24 whitespace-nowrap">
                  Actions
                </th>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E4EAF2]/60">
            {isLoading ? (
              Array.from({ length: 5 }).map((_, i) => (
                <tr key={i} className="animate-pulse">
                  {columns.map((_, cIdx) => (
                    <td key={cIdx} className="px-6 py-4">
                      <div
                        className="h-4 bg-slate-200/80 rounded"
                        style={{ width: `${Math.max(30, 85 - (cIdx % 3) * 20)}%` }}
                      />
                    </td>
                  ))}
                  {(onEdit || onDelete) && (
                    <td className="px-6 py-4 text-right">
                      <div className="h-4 bg-slate-200/80 rounded w-12 ml-auto" />
                    </td>
                  )}
                </tr>
              ))
            ) : !data || data.length === 0 ? (
              <tr>
                <td colSpan={colSpanCount} className="p-0 border-0">
                  <EmptyState title={emptyMessage} description="No data records currently match the current selection." />
                </td>
              </tr>
            ) : (
              data.map((row) => (
                <tr
                  key={keyExtractor(row)}
                  className="hover:bg-[#F8FAFC]/80 transition-colors group"
                >
                  {columns.map((col, cIdx) => (
                    <td
                      key={cIdx}
                      className={`px-6 py-3.5 text-sm text-slate-700 ${
                        col.align === 'right' ? 'text-right' : col.align === 'center' ? 'text-center' : 'text-left'
                      } ${col.className || ''}`}
                    >
                      {col.render ? col.render(row) : (col.accessor ? String(row[col.accessor] ?? '') : '')}
                    </td>
                  ))}
                  {(onEdit || onDelete) && (
                    <td className="px-6 py-3.5 text-right whitespace-nowrap">
                      <div className="flex items-center justify-end gap-1.5 opacity-90 group-hover:opacity-100 transition-opacity">
                        {onEdit && (
                          <IconButton
                            icon={<Pencil size={14} />}
                            aria-label="Edit record"
                            variant="primary"
                            size="sm"
                            title="Edit"
                            onClick={() => onEdit(row)}
                          />
                        )}
                        {onDelete && (
                          <IconButton
                            icon={<Trash2 size={14} />}
                            aria-label="Delete record"
                            variant="danger"
                            size="sm"
                            title="Delete"
                            onClick={() => onDelete(row)}
                          />
                        )}
                      </div>
                    </td>
                  )}
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>

      {data && data.length > 0 && (
        <div className="px-6 py-3 bg-slate-50/60 border-t border-slate-200/80 flex items-center justify-between text-xs text-slate-500">
          <span className="font-medium font-tabular">
            Showing {data.length} {data.length === 1 ? 'record' : 'records'}
          </span>
          <span className="text-[11px] text-slate-400">Campus Information System</span>
        </div>
      )}
    </div>
  );
}
