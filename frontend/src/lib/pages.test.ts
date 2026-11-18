/// <reference types="vite/client" />
// Tests for the route registry: which /app pages exist, who may open them (UX-DR27),
// the nav tabs (UX-DR16), the settings links, and where a User lands after log-in (UX-DR18).
// This only decides what to SHOW. The backend still answers 403 for any forbidden call (AD-5).
import { expect, test } from "vitest";
import { canOpen, isUnder, landingPath, PAGES, settingsLinks, tabs, type Permission } from "./pages";

const OWNER: Permission[] = ["manage_setup", "use_inbox_and_bookings", "see_own_bookings", "see_dashboard"];
const STAFF: Permission[] = ["use_inbox_and_bookings", "see_own_bookings", "see_dashboard"];
const TECHNICIAN: Permission[] = ["see_own_bookings"];
const tabLabels = (permissions: Permission[]) => tabs(permissions).map((tab) => tab.label);

// --- canOpen ---

test("a Technician-only User cannot open the Dashboard or the Inbox", () => {
  expect(canOpen("/app", TECHNICIAN)).toBe(false);
  expect(canOpen("/app/inbox", TECHNICIAN)).toBe(false);
  expect(canOpen("/app/inbox/123", TECHNICIAN)).toBe(false);
});

test("a Technician-only User can open the Calendar and More", () => {
  expect(canOpen("/app/calendar", TECHNICIAN)).toBe(true);
  expect(canOpen("/app/more", TECHNICIAN)).toBe(true);
});

test("Staff can open all four tab pages", () => {
  for (const path of ["/app", "/app/inbox", "/app/calendar", "/app/more"]) {
    expect(canOpen(path, STAFF)).toBe(true);
  }
});

test("only the Owner (manage_setup) can open Settings → Team", () => {
  expect(canOpen("/app/settings/team", STAFF)).toBe(false);
  expect(canOpen("/app/settings/team", TECHNICIAN)).toBe(false);
  expect(canOpen("/app/settings/team", ["manage_setup"])).toBe(true);
});

test("every User can open Settings → Appearance, even with no permissions", () => {
  expect(canOpen("/app/settings/appearance", [])).toBe(true);
});

test("a path with no row is blocked, even for the Owner (fail closed)", () => {
  expect(canOpen("/app/foo", OWNER)).toBe(false);
  expect(canOpen("/app/settings", OWNER)).toBe(false);
  expect(canOpen("/app/inboxes", OWNER)).toBe(false);
  expect(canOpen("/app/settings/teams", OWNER)).toBe(false);
});

test("a sub-page follows its parent's rule", () => {
  expect(canOpen("/app/settings/team/5", ["manage_setup"])).toBe(true);
  expect(canOpen("/app/settings/team/5", STAFF)).toBe(false);
});

// --- isUnder ---

test("/app matches only itself; other links also match their sub-pages", () => {
  expect(isUnder("/app", "/app")).toBe(true);
  expect(isUnder("/app/inbox/1", "/app")).toBe(false);
  expect(isUnder("/app/inbox/1", "/app/inbox")).toBe(true);
  expect(isUnder("/app/inboxes", "/app/inbox")).toBe(false);
});

// --- tabs ---

test("Owner and Staff see Dashboard, Inbox, Calendar, More", () => {
  expect(tabLabels(OWNER)).toEqual(["Dashboard", "Inbox", "Calendar", "More"]);
  expect(tabLabels(STAFF)).toEqual(["Dashboard", "Inbox", "Calendar", "More"]);
});

test("Technician-only Users see Calendar and More", () => {
  expect(tabLabels(TECHNICIAN)).toEqual(["Calendar", "More"]);
});

test("each tab links to its page", () => {
  expect(tabs(OWNER).map((tab) => tab.href)).toEqual(["/app", "/app/inbox", "/app/calendar", "/app/more"]);
});

// --- settingsLinks ---

test("settings links: Owner sees Team then Appearance; Technician sees Appearance only", () => {
  expect(settingsLinks(OWNER).map((link) => link.label)).toEqual(["Team", "Appearance"]);
  expect(settingsLinks(TECHNICIAN).map((link) => link.label)).toEqual(["Appearance"]);
});

// --- landingPath ---

test("Owner and Staff land on the Dashboard", () => {
  expect(landingPath(OWNER)).toBe("/app");
  expect(landingPath(STAFF)).toBe("/app");
});

test("Technician-only Users land on the Calendar", () => {
  expect(landingPath(TECHNICIAN)).toBe("/app/calendar");
});

// --- the registry itself ---

test("every page.tsx under app/app has a row in PAGES", () => {
  // Vite lists the files at test time. "../app/app/settings/team/page.tsx" -> "/app/settings/team".
  const files = Object.keys(import.meta.glob("../app/app/**/page.tsx"));
  const hrefs = files.map((file) => file.replace("../app", "").replace(/\/page\.tsx$/, ""));
  expect(hrefs.length).toBeGreaterThan(0);
  expect(PAGES.map((page) => page.href).sort()).toEqual(hrefs.sort());
});
