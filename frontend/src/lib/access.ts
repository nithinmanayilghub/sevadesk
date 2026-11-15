// Which /app pages a User may open (UX-DR27). The backend sends the User's permissions
// (GET /api/v1/me); the FR-10 rules live only there. This file only decides what to SHOW:
// the backend still answers 403 to any forbidden call (AD-5).
import type { components } from "@/api/schema";

export type Permission = components["schemas"]["Permission"];

// Does this page belong to this link? "/app" (the Dashboard) matches only itself;
// every other link also matches its sub-pages (e.g. /app/inbox/123 is under /app/inbox).
export function isUnder(pathname: string, href: string): boolean {
  return href === "/app" ? pathname === "/app" : pathname === href || pathname.startsWith(`${href}/`);
}

// Pages that need a permission. Any path NOT listed is open to every logged-in User
// (Calendar and More are for all Roles). Owner-only pages, like the settings pages,
// must add their row here in their own story.
const PAGE_RULES: { href: string; needs: Permission }[] = [
  { href: "/app", needs: "see_dashboard" },
  { href: "/app/inbox", needs: "use_inbox_and_bookings" },
];

export function canOpen(pathname: string, permissions: Permission[]): boolean {
  const rule = PAGE_RULES.find(({ href }) => isUnder(pathname, href));
  return rule === undefined || permissions.includes(rule.needs);
}
