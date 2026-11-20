// Time and date helpers (UX-DR4). Working Hours are clock times in the Business timezone
// ("10:00"), and closed days are plain dates ("2026-12-25"). Neither is a moment, so we
// never turn them into a Date in the viewer's own timezone: we only reformat the text.
//
// Written by hand, not with Intl: the spec fixes the exact text ("10:00 am – 6:00 pm",
// "Fri, 25 Dec"), and Intl output differs between browsers and Node.

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

// "18:00" or "18:00:00" -> "6:00 pm". Midnight is "12:00 am", noon is "12:00 pm".
export function formatTime(value: string): string {
  const [hours, minutes] = value.split(":").map(Number);
  const hour12 = hours % 12 === 0 ? 12 : hours % 12;
  return `${hour12}:${String(minutes).padStart(2, "0")} ${hours < 12 ? "am" : "pm"}`;
}

// "10:00 am – 6:00 pm" (an en dash with spaces).
export function formatTimeRange(start: string, end: string): string {
  return `${formatTime(start)} – ${formatTime(end)}`;
}

// "2026-12-25" -> "Fri, 25 Dec". Built in UTC and read in UTC, so the viewer's own
// timezone can never move the date to the day before.
export function formatDate(isoDate: string): string {
  const [year, month, day] = isoDate.split("-").map(Number);
  const date = new Date(Date.UTC(year, month - 1, day));
  return `${WEEKDAYS[date.getUTCDay()]}, ${day} ${MONTHS[date.getUTCMonth()]}`;
}

// The API sends "10:00:00"; an <input type="time"> shows "10:00". null (closed) -> "".
export function toTimeInput(value: string | null): string {
  return value === null ? "" : value.slice(0, 5);
}

// A Service duration in minutes -> "30 min", "1 h", "1 h 30 min". A zero part is left out.
export function formatDuration(minutes: number): string {
  const hours = Math.floor(minutes / 60);
  const rest = minutes % 60;
  const parts = [hours > 0 ? `${hours} h` : "", rest > 0 ? `${rest} min` : ""];
  return parts.filter(Boolean).join(" ");
}
