// The route registry: every /app page, in one list. Each row says the page's link, its label,
// the permission it needs (if any), and where its link shows (a nav tab, or a link on More).
// The nav tabs (UX-DR16), the settings links, who may open a page (UX-DR27) and the first page
// after log-in (UX-DR18) are all read from this list.
//
// A new /app page = one new row here. A test fails if a page.tsx folder has no row.
//
// This only decides what to SHOW. The backend sends the User's permissions (GET /api/v1/me)
// and still answers 403 to any forbidden call (AD-5).
import { CalendarDays, Ellipsis, Inbox, LayoutDashboard, type LucideIcon } from "lucide-react";
import type { components } from "@/api/schema";

export type Permission = components["schemas"]["Permission"];

// alsoActiveUnder: other pages where this tab counts as the current one (e.g. More on
// /app/settings/*, because the settings pages are opened from More).
export type Tab = { href: string; label: string; icon: LucideIcon; alsoActiveUnder?: string[] };
export type SettingsLink = { href: string; label: string };

// needs: the permission a User must have. No needs = every logged-in User (all Roles).
type Page = { href: string; label: string; needs?: Permission } & (
  | { place: "tab"; icon: LucideIcon; alsoActiveUnder?: string[] }
  | { place: "settings" }
);

// Order matters: tabs and settings links show in this order, and the first tab a User may
// open is where they land after log-in.
export const PAGES: readonly Page[] = [
  { href: "/app", label: "Dashboard", place: "tab", icon: LayoutDashboard, needs: "see_dashboard" },
  { href: "/app/inbox", label: "Inbox", place: "tab", icon: Inbox, needs: "use_inbox_and_bookings" },
  { href: "/app/calendar", label: "Calendar", place: "tab", icon: CalendarDays },
  { href: "/app/more", label: "More", place: "tab", icon: Ellipsis, alsoActiveUnder: ["/app/settings"] },
  { href: "/app/settings/team", label: "Team", place: "settings", needs: "manage_setup" },
  { href: "/app/settings/appearance", label: "Appearance", place: "settings" },
];

// Does this page belong to this link? "/app" (the Dashboard) matches only itself;
// every other link also matches its sub-pages (e.g. /app/inbox/123 is under /app/inbox).
export function isUnder(pathname: string, href: string): boolean {
  return href === "/app" ? pathname === "/app" : pathname === href || pathname.startsWith(`${href}/`);
}

// May this User open this path? A path with no row is blocked (fail closed): a forgotten
// row shows "No access" instead of an open page.
export function canOpen(pathname: string, permissions: Permission[]): boolean {
  const page = PAGES.find(({ href }) => isUnder(pathname, href));
  if (page === undefined) return false;
  return page.needs === undefined || permissions.includes(page.needs);
}

// The nav tabs this User may open.
export function tabs(permissions: Permission[]): Tab[] {
  return PAGES.flatMap((page) =>
    page.place === "tab" && canOpen(page.href, permissions)
      ? [{ href: page.href, label: page.label, icon: page.icon, alsoActiveUnder: page.alsoActiveUnder }]
      : [],
  );
}

// The settings links (on More) this User may open.
export function settingsLinks(permissions: Permission[]): SettingsLink[] {
  return PAGES.flatMap((page) =>
    page.place === "settings" && canOpen(page.href, permissions) ? [{ href: page.href, label: page.label }] : [],
  );
}

// The first page after log-in: the first tab this User may open. Owner and Staff get the
// Dashboard; Technician-only Users get the Calendar. Calendar has no needs, so the
// fallback is only a safety net.
export function landingPath(permissions: Permission[]): string {
  return tabs(permissions)[0]?.href ?? "/app/calendar";
}
