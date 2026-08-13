export const VIETNAM_TIMEZONE = "Asia/Ho_Chi_Minh";

function asUtcDate(value: string | Date): Date {
  if (value instanceof Date) return value;
  // API datetime columns are stored as naive UTC for portability. Treat an
  // offset-less ISO value as UTC instead of letting the browser interpret it
  // in the machine's local timezone.
  const normalized = /(?:Z|[+-]\d{2}:?\d{2})$/i.test(value) ? value : `${value}Z`;
  return new Date(normalized);
}

export function formatVietnamDateTime(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = asUtcDate(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: VIETNAM_TIMEZONE,
    dateStyle: "short",
    timeStyle: "short",
  }).format(date);
}

export function formatVietnamDate(value: string | Date | null | undefined): string {
  if (!value) return "—";
  const date = asUtcDate(value);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("vi-VN", {
    timeZone: VIETNAM_TIMEZONE,
    dateStyle: "medium",
  }).format(date);
}

export function vietnamDateRangeStart(range: "today" | "7d" | "30d"): string {
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: VIETNAM_TIMEZONE,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).formatToParts(new Date());
  const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
  const start = new Date(`${values.year}-${values.month}-${values.day}T00:00:00+07:00`);
  if (range === "7d") start.setUTCDate(start.getUTCDate() - 7);
  if (range === "30d") start.setUTCDate(start.getUTCDate() - 30);
  return start.toISOString();
}
