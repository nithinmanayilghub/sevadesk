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

// The calendar date and clock time of a moment in a timezone, as plain numbers.
// Intl gives the numbers (it knows every timezone's offsets); we write the text ourselves,
// as everywhere in this file, so it is the same in every browser and in Node.
function partsIn(moment: Date, timeZone: string) {
  const parts = new Intl.DateTimeFormat("en-GB", {
    timeZone,
    year: "numeric",
    month: "numeric",
    day: "numeric",
    hour: "numeric",
    minute: "numeric",
    hourCycle: "h23",
  }).formatToParts(moment);
  const get = (type: Intl.DateTimeFormatPartTypes) => Number(parts.find((part) => part.type === type)?.value);
  return { year: get("year"), month: get("month"), day: get("day"), hour: get("hour"), minute: get("minute") };
}

// An Inbox row's time (story 4.3), in the BUSINESS timezone (UX-DR4), not the viewer's:
// today -> "10:42 am"; earlier this year -> "Wed, 4 Nov"; an older year -> "Thu, 4 Dec 2025".
// "Today" is also the Business's today: 23:30 UTC is already the next day in IST.
export function formatListTime(iso: string, now: Date, timeZone: string): string {
  const at = partsIn(new Date(iso), timeZone);
  const today = partsIn(now, timeZone);
  if (at.year === today.year && at.month === today.month && at.day === today.day) {
    return formatTime(`${at.hour}:${at.minute}`);
  }
  // The weekday of that calendar date (built in UTC, so no timezone can move it).
  const weekday = WEEKDAYS[new Date(Date.UTC(at.year, at.month - 1, at.day)).getUTCDay()];
  const date = `${weekday}, ${at.day} ${MONTHS[at.month - 1]}`;
  return at.year === today.year ? date : `${date} ${at.year}`;
}
