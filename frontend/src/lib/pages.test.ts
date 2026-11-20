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

test("settings links: Owner sees Services, Working Hours, Chat link, Team, Appearance; Technician sees Appearance only", () => {
  expect(settingsLinks(OWNER).map((link) => link.label)).toEqual([
    "Services",
    "Working Hours",
    "Chat link",
    "Team",
    "Appearance",
  ]);
  expect(settingsLinks(TECHNICIAN).map((link) => link.label)).toEqual(["Appearance"]);
});

test("the Services link needs manage_setup", () => {
  const hrefs = (permissions: Permission[]) => settingsLinks(permissions).map((link) => link.href);
  expect(hrefs(["manage_setup"])).toContain("/app/settings/services");
  expect(hrefs([])).not.toContain("/app/settings/services");
});

test("the Working Hours link needs manage_setup, so Staff cannot open it", () => {
  const hrefs = (permissions: Permission[]) => settingsLinks(permissions).map((link) => link.href);
  expect(hrefs(["manage_setup"])).toContain("/app/settings/hours");
  expect(canOpen("/app/settings/hours", STAFF)).toBe(false);
});

test("the Chat link page needs manage_setup, so Staff cannot open it", () => {
  const hrefs = (permissions: Permission[]) => settingsLinks(permissions).map((link) => link.href);
  expect(hrefs(["manage_setup"])).toContain("/app/settings/chat-link");
  expect(canOpen("/app/settings/chat-link", STAFF)).toBe(false);
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

// Vite lists the page files at test time. "../app/app/settings/team/page.tsx" -> "/app/settings/team".
// Route groups like "(group)" are not part of the URL, so they are removed.
const pagePaths = Object.keys(import.meta.glob("../app/app/**/page.{tsx,ts,jsx,js}")).map((file) =>
  file
    .replace("../app", "")
    .replace(/\/\([^/]+\)/g, "")
    .replace(/\/page\.(tsx|ts|jsx|js)$/, ""),
);

test("every page file under app/app is covered by a row in PAGES", () => {
  // A sub-page (e.g. a future /app/inbox/[id]) is covered by its parent's row.
  expect(pagePaths.length).toBeGreaterThan(0);
  const uncovered = pagePaths.filter((path) => !PAGES.some((page) => isUnder(path, page.href)));
  expect(uncovered).toEqual([]);
});

test("every row in PAGES has a page file", () => {
  const missing = PAGES.filter((page) => !pagePaths.includes(page.href)).map((page) => page.href);
  expect(missing).toEqual([]);
});
