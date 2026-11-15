// Log-in helpers. Role checks that protect data live in the backend only (AD-5);
// these only choose which screen to show.

import type { Permission } from "@/lib/access";

// UX-DR18: Users who may see the Dashboard (Owner, Staff) start there; Technician-only
// Users start on the Calendar.
export function landingPath(permissions: Permission[]): "/app" | "/app/calendar" {
  return permissions.includes("see_dashboard") ? "/app" : "/app/calendar";
}

// A 401 means "no valid session" (logged out, or idle for 7 days): go to /login.
// Not for the log-in call itself (a 401 there is a wrong password), and not on /login.
export function shouldRedirectToLogin(status: number, schemaPath: string, currentPath: string): boolean {
  return status === 401 && schemaPath !== "/api/v1/login" && currentPath !== "/login";
}
