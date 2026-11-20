"use client";
// Layout for every /app page: asks the backend who is logged in, then shows the app shell.
// No session? GET /api/v1/me returns 401, and the API client sends the User to /login.
// A page the User's Role may not open shows "You don't have access to this page." (UX-DR27).
import { usePathname } from "next/navigation";
import { useEffect } from "react";
import { api } from "@/api/client";
import { AppShell } from "@/components/AppShell";
import { NoAccess } from "@/components/NoAccess";
import { LoadFailed } from "@/components/LoadFailed";
import { canOpen } from "@/lib/pages";
import { PermissionsProvider } from "@/lib/permissions";
import { applyTheme, ThemeProvider, type Theme } from "@/lib/theme";
import { useLoad } from "@/lib/useLoad";

export default function AppLayout({ children }: LayoutProps<"/app">) {
  const pathname = usePathname();
  // 401 = not logged in: useLoad stays "loading" while the API client goes to /login.
  // Anything else (500, 503: e.g. the demo database waking up) gets a message and a retry.
  const me = useLoad(() => api.GET("/api/v1/me"), []);
  const { reload } = me;
  // null while there is no data: loading, or a failed reload.
  const theme: Theme | null = me.status === "ready" ? me.data.theme : null;

  useEffect(() => {
    // Back after log-out: Chrome may show a frozen copy of this page from its back-forward
    // cache, without loading it again. "persisted" says so. Ask the server again: a 401
    // then sends the browser to /login, so nobody sees the old session's screen.
    function onPageShow(event: PageTransitionEvent) {
      if (event.persisted) reload();
    }
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  }, [reload]);

  // Write the theme on <html> once we know it. With no data, keep what is there: the error
  // screen after a failed reload keeps the User's theme.
  useEffect(() => {
    if (theme !== null) applyTheme(theme);
  }, [theme]);
  // Remove it when /app closes, so public pages follow the device.
  useEffect(() => () => applyTheme(null), []);

  if (me.status === "failed" || me.status === "not_found") {
    return (
      <div className="px-page-x py-6">
        <LoadFailed onRetry={reload} />
      </div>
    );
  }
  if (me.status === "loading") {
    // A plain placeholder block while we wait (UX-DR25 skeleton style).
    return <div aria-busy="true" aria-label="Loading" className="m-6 h-24 animate-pulse rounded-lg bg-muted" />;
  }
  const { permissions } = me.data;
  // A theme change replaces the loaded data: Appearance settings show it at once (and put the
  // old one back if the save fails), and a later reload brings the saved theme. The updater
  // changes only the theme of the newest data, so it never brings back old permissions.
  const setTheme = (next: Theme) => me.replace((current) => ({ ...current, theme: next }));
  return (
    // The provider shares the permissions with every page, so a page can hide its own buttons.
    <PermissionsProvider permissions={permissions}>
      <ThemeProvider theme={me.data.theme} setTheme={setTheme}>
        <AppShell permissions={permissions}>{canOpen(pathname, permissions) ? children : <NoAccess />}</AppShell>
      </ThemeProvider>
    </PermissionsProvider>
  );
}
