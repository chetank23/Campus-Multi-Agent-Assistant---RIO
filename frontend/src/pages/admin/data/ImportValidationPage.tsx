import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  UploadCloud,
  FileCheck,
  AlertTriangle,
  CheckCircle2,
  Table,
  Download,
} from 'lucide-react';
import { PageHeader, ConfirmDialog } from '@/components/common';
import {
  dataImportApi,
  type ImportEntityType,
  type ImportPreviewResponse,
  type ImportCommitResponse,
} from '@/api/dataImport';

const SAMPLE_TEMPLATES: Record<ImportEntityType, { csv: string; filename: string }> = {
  rooms: {
    filename: 'rooms_template.csv',
    csv: `room_number,building_id,capacity,room_type\nMB-201,1,60,CLASSROOM\nMB-202,1,60,CLASSROOM\nSB-301,2,30,LAB`,
  },
  courses: {
    filename: 'courses_template.csv',
    csv: `course_code,course_name,department_id,course_type,credits\nCS501,Advanced Algorithms,1,THEORY,4\nCS502,Machine Learning Lab,1,LAB,2\nEE501,Control Systems,3,THEORY,3`,
  },
  faculty: {
    filename: 'faculty_template.csv',
    csv: `faculty_id,name,email,department_id,designation\nFAC901,Dr. John Doe,john.doe@campus.edu,1,Associate Professor\nFAC902,Dr. Jane Miller,jane.miller@campus.edu,1,Professor`,
  },
  students: {
    filename: 'students_template.csv',
    csv: `student_id,name,email,department_id,section_id\nSTU8001,Alex Johnson,alex.j@campus.edu,1,1\nSTU8002,Beatrix Kiddo,beatrix.k@campus.edu,1,1`,
  },
};

export function ImportValidationPage() {
  const [entityType, setEntityType] = useState<ImportEntityType>('rooms');
  const [rawText, setRawText] = useState(SAMPLE_TEMPLATES.rooms.csv);
  const [previewResult, setPreviewResult] = useState<ImportPreviewResponse | null>(null);
  const [commitResult, setCommitResult] = useState<ImportCommitResponse | null>(null);
  const [isConfirmOpen, setIsConfirmOpen] = useState(false);
  const [parseError, setParseError] = useState<string | null>(null);

  const handleEntityChange = (type: ImportEntityType) => {
    setEntityType(type);
    setRawText(SAMPLE_TEMPLATES[type].csv);
    setPreviewResult(null);
    setCommitResult(null);
    setParseError(null);
  };

  const parseCSVToObjects = (csv: string): Record<string, any>[] => {
    const lines = csv
      .split('\n')
      .map((l) => l.trim())
      .filter((l) => l.length > 0);
    if (lines.length < 2) throw new Error('CSV must contain a header row and at least one data row.');

    const headers = lines[0].split(',').map((h) => h.trim());
    const rows: Record<string, any>[] = [];

    for (let i = 1; i < lines.length; i++) {
      const values = lines[i].split(',').map((v) => v.trim());
      const row: Record<string, any> = {};
      headers.forEach((h, idx) => {
        row[h] = values[idx] !== undefined ? values[idx] : '';
      });
      rows.push(row);
    }
    return rows;
  };

  const previewMutation = useMutation({
    mutationFn: ({ type, rows }: { type: ImportEntityType; rows: Record<string, any>[] }) =>
      dataImportApi.preview(type, rows),
    onSuccess: (data) => {
      setPreviewResult(data);
      setCommitResult(null);
    },
    onError: (err: any) => {
      setParseError(err.response?.data?.detail || err.message || 'Validation failed.');
    },
  });

  const commitMutation = useMutation({
    mutationFn: ({ type, rows }: { type: ImportEntityType; rows: Record<string, any>[] }) =>
      dataImportApi.commit(type, rows),
    onSuccess: (data) => {
      setCommitResult(data);
      setIsConfirmOpen(false);
    },
    onError: (err: any) => {
      setParseError(err.response?.data?.detail || err.message || 'Commit failed.');
      setIsConfirmOpen(false);
    },
  });

  const handleRunValidation = () => {
    setParseError(null);
    setCommitResult(null);
    try {
      let rows: Record<string, any>[] = [];
      const trimmed = rawText.trim();
      if (trimmed.startsWith('[') || trimmed.startsWith('{')) {
        const parsed = JSON.parse(trimmed);
        rows = Array.isArray(parsed) ? parsed : [parsed];
      } else {
        rows = parseCSVToObjects(trimmed);
      }

      if (rows.length === 0) {
        setParseError('No data records found in input.');
        return;
      }
      previewMutation.mutate({ type: entityType, rows });
    } catch (err: any) {
      setParseError(err.message || 'Failed to parse CSV or JSON.');
    }
  };

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (event) => {
      const content = event.target?.result as string;
      setRawText(content);
      setPreviewResult(null);
      setCommitResult(null);
    };
    reader.readAsText(file);
  };

  const handleDownloadTemplate = () => {
    const template = SAMPLE_TEMPLATES[entityType];
    const blob = new Blob([template.csv], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = template.filename;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Import & Validation"
        subtitle="Staged ingestion workflow: upload CSV/JSON, preview foreign-key checks, review row-level errors, and commit."
        actions={
          <button
            onClick={handleDownloadTemplate}
            className="inline-flex items-center gap-2 px-3.5 py-2 border border-slate-300 hover:bg-slate-50 text-slate-700 text-xs font-semibold rounded-lg shadow-xs transition-colors"
          >
            <Download size={16} />
            Download Sample CSV
          </button>
        }
      />

      {/* Commit Result Banner */}
      {commitResult && (
        <div className="p-4 rounded-xl bg-emerald-50 border border-emerald-200 text-emerald-900 flex items-start gap-3">
          <CheckCircle2 size={22} className="text-emerald-600 shrink-0 mt-0.5" />
          <div>
            <h4 className="text-sm font-bold">Import Succeeded</h4>
            <p className="text-xs text-emerald-700 mt-0.5">{commitResult.message}</p>
          </div>
        </div>
      )}

      {/* Step 1: Entity & File Selection */}
      <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-4">
        <h2 className="text-sm font-bold text-slate-900 uppercase tracking-wider">
          Step 1: Choose Dataset & Input Format
        </h2>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
          {(['rooms', 'courses', 'faculty', 'students'] as ImportEntityType[]).map((type) => (
            <button
              key={type}
              type="button"
              onClick={() => handleEntityChange(type)}
              className={`p-3 rounded-xl border text-left transition-all ${
                entityType === type
                  ? 'border-primary-600 bg-primary-50/50 ring-2 ring-primary-500/20'
                  : 'border-slate-200 bg-white hover:border-slate-300'
              }`}
            >
              <div className="text-xs font-bold uppercase tracking-wider text-slate-500">
                Entity
              </div>
              <div className="text-sm font-bold text-slate-900 capitalize mt-0.5">
                {type}
              </div>
            </button>
          ))}
        </div>

        <div className="space-y-2 pt-2">
          <div className="flex items-center justify-between">
            <label className="text-xs font-semibold text-slate-700">
              CSV Data or Upload File:
            </label>
            <label className="cursor-pointer text-xs font-bold text-primary-600 hover:text-primary-700 flex items-center gap-1">
              <UploadCloud size={14} />
              <span>Upload CSV File</span>
              <input
                type="file"
                accept=".csv,.txt"
                onChange={handleFileUpload}
                className="hidden"
              />
            </label>
          </div>
          <textarea
            rows={6}
            value={rawText}
            onChange={(e) => setRawText(e.target.value)}
            className="w-full font-mono text-xs p-3 border border-slate-200 rounded-xl focus:outline-none focus:ring-2 focus:ring-primary-500/20 bg-slate-50/50"
            placeholder="Paste CSV rows here with headers…"
          />
        </div>

        {parseError && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 font-medium">
            {parseError}
          </div>
        )}

        <div className="flex justify-end pt-2">
          <button
            onClick={handleRunValidation}
            disabled={previewMutation.isPending}
            className="flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-700 text-white text-sm font-bold rounded-xl shadow-xs transition-colors disabled:opacity-50"
          >
            <FileCheck size={16} />
            <span>
              {previewMutation.isPending ? 'Validating Against Database…' : 'Validate & Preview Rows'}
            </span>
          </button>
        </div>
      </div>

      {/* Step 2: Validation Results & Row Inspection */}
      {previewResult && (
        <div className="bg-white p-6 rounded-2xl border border-slate-200 shadow-xs space-y-6">
          <div className="flex items-center justify-between border-b border-slate-100 pb-4">
            <div>
              <h2 className="text-base font-bold text-slate-900">
                Step 2: Pre-Commit Validation Report
              </h2>
              <p className="text-xs text-slate-500">
                Checked against existing foreign keys, duplicate indices, and database constraints
              </p>
            </div>
            <div className="flex items-center gap-3">
              <span className="px-3 py-1 bg-emerald-50 text-emerald-800 text-xs font-bold rounded-lg border border-emerald-200">
                {previewResult.valid_rows_count} Valid Rows
              </span>
              {previewResult.invalid_rows_count > 0 && (
                <span className="px-3 py-1 bg-red-50 text-red-800 text-xs font-bold rounded-lg border border-red-200">
                  {previewResult.invalid_rows_count} Issues Found
                </span>
              )}
            </div>
          </div>

          {/* Error Diagnostics Table */}
          {previewResult.errors.length > 0 && (
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-red-700 text-xs font-bold uppercase tracking-wider">
                <AlertTriangle size={16} />
                <span>Validation Errors (Must be resolved or skipped before commit)</span>
              </div>
              <div className="border border-red-200 rounded-xl overflow-hidden bg-red-50/30">
                <table className="w-full text-left text-xs">
                  <thead className="bg-red-100/50 text-red-900 font-bold border-b border-red-200">
                    <tr>
                      <th className="py-2 px-3 w-20">Row #</th>
                      <th className="py-2 px-3 w-32">Field</th>
                      <th className="py-2 px-3">Violation Reason</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-red-100">
                    {previewResult.errors.map((err, i) => (
                      <tr key={i} className="hover:bg-red-50/70">
                        <td className="py-2 px-3 font-mono font-bold text-red-800">
                          #{err.row_index + 1}
                        </td>
                        <td className="py-2 px-3 font-mono text-slate-700">
                          {err.field}
                        </td>
                        <td className="py-2 px-3 text-red-800 font-medium">
                          {err.message}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}

          {/* Valid Data Preview Table */}
          <div className="space-y-2">
            <div className="flex items-center justify-between text-xs font-bold uppercase tracking-wider text-slate-700">
              <div className="flex items-center gap-2">
                <Table size={16} className="text-primary-600" />
                <span>Validated Rows Ready for Commit ({previewResult.preview_data.length} previewed)</span>
              </div>
            </div>

            {previewResult.preview_data.length > 0 ? (
              <div className="border border-slate-200 rounded-xl overflow-x-auto">
                <table className="w-full text-left text-xs">
                  <thead className="bg-slate-50 text-slate-700 font-bold border-b border-slate-200">
                    <tr>
                      {Object.keys(previewResult.preview_data[0] || {}).map((col) => (
                        <th key={col} className="py-2.5 px-3 capitalize">
                          {col.replace('_', ' ')}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {previewResult.preview_data.map((row, idx) => (
                      <tr key={idx} className="hover:bg-slate-50/50 font-mono">
                        {Object.values(row).map((val: any, j) => (
                          <td key={j} className="py-2.5 px-3 text-slate-700">
                            {String(val)}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="p-4 bg-slate-50 border border-slate-200 rounded-xl text-center text-xs text-slate-500">
                No valid rows available in current input payload.
              </div>
            )}
          </div>

          {/* Step 3: Explicit Commit Action */}
          <div className="flex items-center justify-between pt-4 border-t border-slate-100">
            <p className="text-xs text-slate-500">
              Only verified records will be ingested into the authoritative database tables.
            </p>
            <button
              onClick={() => setIsConfirmOpen(true)}
              disabled={previewResult.valid_rows_count === 0 || commitMutation.isPending}
              className="flex items-center gap-2 px-6 py-2.5 bg-emerald-600 hover:bg-emerald-700 text-white text-sm font-bold rounded-xl shadow-xs transition-colors disabled:opacity-50"
            >
              <CheckCircle2 size={16} />
              <span>Confirm & Commit {previewResult.valid_rows_count} Records</span>
            </button>
          </div>
        </div>
      )}

      {/* Confirmation Dialog */}
      <ConfirmDialog
        isOpen={isConfirmOpen}
        onCancel={() => setIsConfirmOpen(false)}
        title="Confirm Institutional Data Import"
        message={`Are you sure you want to write ${previewResult?.valid_rows_count || 0} ${entityType} records to the database? This transaction will be audited.`}
        confirmLabel="Execute Commit"
        isProcessing={commitMutation.isPending}
        onConfirm={() => {
          if (!previewResult) return;
          commitMutation.mutate({
            type: entityType,
            rows: previewResult.preview_data,
          });
        }}
      />
    </div>
  );
}
