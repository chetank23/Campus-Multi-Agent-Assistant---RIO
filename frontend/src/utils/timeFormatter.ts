/**
 * frontend/src/utils/timeFormatter.ts
 * -----------------------------------
 * Centralized 12-hour AM/PM date/time formatting utility for all roles.
 * Respects the configured campus timezone (Asia/Kolkata).
 */

export const CAMPUS_TIMEZONE = 'Asia/Kolkata';

const time12hIntl = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: true,
  timeZone: CAMPUS_TIMEZONE,
});

const timeWithSeconds12hIntl = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hour12: true,
  timeZone: CAMPUS_TIMEZONE,
});

const dateTime12hIntl = new Intl.DateTimeFormat('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
  hour12: true,
  timeZone: CAMPUS_TIMEZONE,
});

/**
 * Formats a time string ("09:00", "13:30:00", "00:00", "12:00") or ISO timestamp
 * into a consistent zero-padded 12-hour AM/PM string (e.g. "09:00 AM", "01:30 PM").
 */
export const formatTime12h = (timeStr?: string | Date | null): string => {
  if (!timeStr) return '';
  if (timeStr instanceof Date) {
    return isNaN(timeStr.getTime()) ? '' : time12hIntl.format(timeStr);
  }
  const trimmed = String(timeStr).trim();
  if (!trimmed) return '';

  // ISO datetime string (e.g. "2026-11-30T13:30:00Z")
  if (trimmed.includes('T') || (trimmed.includes('-') && trimmed.includes(':'))) {
    const parsed = new Date(trimmed);
    if (!isNaN(parsed.getTime())) {
      return time12hIntl.format(parsed);
    }
  }

  const parts = trimmed.split(':');
  if (parts.length < 2) return trimmed;
  let hours = parseInt(parts[0], 10);
  const minutes = parts[1].slice(0, 2).padStart(2, '0');
  if (isNaN(hours) || hours < 0 || hours > 23) return trimmed;

  const ampm = hours >= 12 ? 'PM' : 'AM';
  hours = hours % 12;
  hours = hours ? hours : 12;
  return `${String(hours).padStart(2, '0')}:${minutes} ${ampm}`;
};

/**
 * Formats a start–end time interval in 12-hour AM/PM format.
 */
export const formatTimeRange12h = (
  start?: string | null,
  end?: string | null
): string => {
  const s = formatTime12h(start);
  const e = formatTime12h(end);
  if (s && e) return `${s} – ${e}`;
  return s || e || '';
};

/**
 * Formats a Date or ISO timestamp into a readable date + 12-hour AM/PM string.
 */
export const formatDateTime12h = (input?: string | Date | null): string => {
  if (!input) return '';
  const d = input instanceof Date ? input : new Date(input);
  if (isNaN(d.getTime())) return typeof input === 'string' ? input : '';
  return dateTime12hIntl.format(d);
};

/**
 * Formats a Date into a 12-hour AM/PM timestamp with seconds (e.g. for refresh indicators).
 */
export const formatTimestamp12h = (d: Date): string => {
  if (isNaN(d.getTime())) return '';
  return timeWithSeconds12hIntl.format(d);
};
