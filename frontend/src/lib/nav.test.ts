// Tests for the nav items per Role (UX-DR16).
import { expect, test } from "vitest";
import { navItems } from "./nav";

const labels = (roles: string[]) => navItems(roles).map((item) => item.label);

test("Owner and Staff see Dashboard, Inbox, Calendar, More", () => {
  expect(labels(["owner", "technician"])).toEqual(["Dashboard", "Inbox", "Calendar", "More"]);
  expect(labels(["staff"])).toEqual(["Dashboard", "Inbox", "Calendar", "More"]);
});

test("Technician-only Users see Calendar and More", () => {
  expect(labels(["technician"])).toEqual(["Calendar", "More"]);
});

test("each item links to its page", () => {
  expect(navItems(["owner"]).map((item) => item.href)).toEqual(["/app", "/app/inbox", "/app/calendar", "/app/more"]);
});
