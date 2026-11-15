// Tests for which /app pages a User may open (UX-DR27). The backend sends the permissions;
// this only decides what to SHOW. The backend still answers 403 for any forbidden call.
import { expect, test } from "vitest";
import { canOpen, isUnder, type Permission } from "./access";

const TECHNICIAN: Permission[] = ["see_own_bookings"];
const STAFF: Permission[] = ["use_inbox_and_bookings", "see_own_bookings", "see_dashboard"];

test("a Technician-only User cannot open the Dashboard or the Inbox", () => {
  expect(canOpen("/app", TECHNICIAN)).toBe(false);
  expect(canOpen("/app/inbox", TECHNICIAN)).toBe(false);
  expect(canOpen("/app/inbox/123", TECHNICIAN)).toBe(false);
});

test("a Technician-only User can open the Calendar and More", () => {
  expect(canOpen("/app/calendar", TECHNICIAN)).toBe(true);
  expect(canOpen("/app/more", TECHNICIAN)).toBe(true);
});

test("Staff can open all four pages", () => {
  for (const path of ["/app", "/app/inbox", "/app/calendar", "/app/more"]) {
    expect(canOpen(path, STAFF)).toBe(true);
  }
});

test("/app matches only itself; other links also match their sub-pages", () => {
  expect(isUnder("/app", "/app")).toBe(true);
  expect(isUnder("/app/inbox/1", "/app")).toBe(false);
  expect(isUnder("/app/inbox/1", "/app/inbox")).toBe(true);
  expect(isUnder("/app/inboxes", "/app/inbox")).toBe(false);
});
