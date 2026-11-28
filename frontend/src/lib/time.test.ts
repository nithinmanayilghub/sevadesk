// Tests for the time and date helpers (UX-DR4): "10:00 am – 6:00 pm" and "Fri, 25 Dec".
import { describe, expect, test } from "vitest";
import { formatDate, formatDuration, formatListTime, formatSlot, formatTime, formatTimeRange, toTimeInput } from "./time";

test("formatTime shows a 12-hour clock with lowercase am/pm", () => {
  expect(formatTime("00:00")).toBe("12:00 am");
  expect(formatTime("09:05:00")).toBe("9:05 am");
  expect(formatTime("12:00")).toBe("12:00 pm");
  expect(formatTime("18:00:00")).toBe("6:00 pm");
  expect(formatTime("23:59")).toBe("11:59 pm");
});

test("formatTimeRange joins two times with an en dash", () => {
  expect(formatTimeRange("10:00:00", "18:00:00")).toBe("10:00 am – 6:00 pm");
});

test("formatDate shows short weekday, day and month", () => {
  expect(formatDate("2026-12-25")).toBe("Fri, 25 Dec");
  expect(formatDate("2026-11-04")).toBe("Wed, 4 Nov");
});

test("toTimeInput gives the HH:MM a time box takes", () => {
  expect(toTimeInput("10:00:00")).toBe("10:00");
  expect(toTimeInput(null)).toBe("");
});

test("formatDuration shows hours and minutes, and leaves out a zero part", () => {
  expect(formatDuration(30)).toBe("30 min");
  expect(formatDuration(60)).toBe("1 h");
  expect(formatDuration(90)).toBe("1 h 30 min");
  expect(formatDuration(480)).toBe("8 h");
});

// formatListTime (story 4.3): an Inbox row's time, in the BUSINESS timezone (UX-DR4), never
// the viewer's. Fixed UTC instants, so the test means the same on any machine.
const IST = "Asia/Kolkata"; // UTC + 5:30

test("formatListTime shows the clock time for a message from today", () => {
  // 05:12 UTC = 10:42 am IST; "now" is later the same IST day.
  expect(formatListTime("2026-11-25T05:12:00Z", new Date("2026-11-25T10:00:00Z"), IST)).toBe("10:42 am");
});

test("formatListTime uses the Business timezone", () => {
  // 23:30 UTC on the 24th is already 5:00 am on the 25th in IST.
  expect(formatListTime("2026-11-24T23:30:00Z", new Date("2026-11-25T10:00:00Z"), IST)).toBe("5:00 am");
  expect(formatListTime("2026-11-24T23:30:00Z", new Date("2026-11-26T10:00:00Z"), IST)).toBe("Wed, 25 Nov");
});

test("formatListTime shows a date for an older day, and the year for an older year", () => {
  expect(formatListTime("2026-11-04T06:00:00Z", new Date("2026-11-25T10:00:00Z"), IST)).toBe("Wed, 4 Nov");
  expect(formatListTime("2025-12-04T06:00:00Z", new Date("2026-11-25T10:00:00Z"), IST)).toBe("Thu, 4 Dec 2025");
});

// formatSlot (story 5.2): a Slot start in the BUSINESS timezone, for the booking form.
describe("formatSlot", () => {
  test("shows the Business clock, not UTC", () => {
    // 04:30 UTC is 10:00 in India.
    expect(formatSlot("2026-11-30T04:30:00Z", "Asia/Kolkata")).toBe("Mon, 30 Nov, 10:00 am");
  });

  test("a late UTC time is already the next Business day", () => {
    // 19:00 UTC on Sun 29 Nov is 00:30 on Mon 30 Nov in India.
    expect(formatSlot("2026-11-29T19:00:00Z", "Asia/Kolkata")).toBe("Mon, 30 Nov, 12:30 am");
  });
});
