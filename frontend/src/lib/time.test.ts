// Tests for the time and date helpers (UX-DR4): "10:00 am – 6:00 pm" and "Fri, 25 Dec".
import { expect, test } from "vitest";
import { formatDate, formatDuration, formatTime, formatTimeRange, toTimeInput } from "./time";

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
