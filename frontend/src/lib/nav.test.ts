// Tests for the nav items per permission (UX-DR16, UX-DR27).
import { expect, test } from "vitest";
import type { Permission } from "./access";
import { navItems } from "./nav";

const OWNER: Permission[] = ["manage_setup", "use_inbox_and_bookings", "see_own_bookings", "see_dashboard"];
const STAFF: Permission[] = ["use_inbox_and_bookings", "see_own_bookings", "see_dashboard"];
const labels = (permissions: Permission[]) => navItems(permissions).map((item) => item.label);

test("Owner and Staff see Dashboard, Inbox, Calendar, More", () => {
  expect(labels(OWNER)).toEqual(["Dashboard", "Inbox", "Calendar", "More"]);
  expect(labels(STAFF)).toEqual(["Dashboard", "Inbox", "Calendar", "More"]);
});

test("Technician-only Users see Calendar and More", () => {
  expect(labels(["see_own_bookings"])).toEqual(["Calendar", "More"]);
});

test("each item links to its page", () => {
  expect(navItems(OWNER).map((item) => item.href)).toEqual(["/app", "/app/inbox", "/app/calendar", "/app/more"]);
});
