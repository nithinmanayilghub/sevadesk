// Log-in helpers. Role checks that protect data live in the backend only (AD-5);
// these only choose which screen to show.

// UX-DR18: Owner and Staff start on the Dashboard; Technician-only Users on the Calendar.
export function landingPath(roles: string[]): "/app" | "/app/calendar" {
  return roles.includes("owner") || roles.includes("staff") ? "/app" : "/app/calendar";
}

// A 401 means "no valid session" (logged out, or idle for 7 days): go to /login.
// Not for the log-in call itself (a 401 there is a wrong password), and not on /login.
export function shouldRedirectToLogin(status: number, schemaPath: string, currentPath: string): boolean {
  return status === 401 && schemaPath !== "/api/v1/login" && currentPath !== "/login";
}
