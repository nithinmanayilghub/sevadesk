// Log-in helper. Role checks that protect data live in the backend only (AD-5).
// (Where a User lands after log-in is landingPath in lib/pages.ts.)

// A 401 means "no valid session" (logged out, or idle for 7 days): go to /login.
// Not for the log-in call itself (a 401 there is a wrong password), and not on /login.
export function shouldRedirectToLogin(status: number, schemaPath: string, currentPath: string): boolean {
  return status === 401 && schemaPath !== "/api/v1/login" && currentPath !== "/login";
}
