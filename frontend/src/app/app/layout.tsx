"use client";
// Layout for every /app page: asks the backend who is logged in, then shows the app shell.
// No session? GET /api/v1/me returns 401, and the API client sends the User to /login.
import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import { AppShell } from "@/components/AppShell";
import { Button } from "@/components/ui/button";

export default function AppLayout({ children }: LayoutProps<"/app">) {
  const [roles, setRoles] = useState<string[] | null>(null);
  const [failed, setFailed] = useState(false);

  const checkSession = useCallback(() => {
    api
      .GET("/api/v1/me")
      .then(({ data, response }) => {
        if (data) setRoles(data.roles);
        // 401 = not logged in: the API client is already on its way to /login.
        // Anything else (500, 503: e.g. the demo database waking up) gets a message and a retry.
        else if (response.status !== 401) setFailed(true);
      })
      .catch(() => setFailed(true)); // network down
  }, []);

  useEffect(() => {
    checkSession();

    // Back after log-out: Chrome may show a frozen copy of this page from its back-forward
    // cache, without loading it again. "persisted" says so. Ask the server again: a 401
    // then sends the browser to /login, so nobody sees the old session's screen.
    function onPageShow(event: PageTransitionEvent) {
      if (event.persisted) checkSession();
    }
    window.addEventListener("pageshow", onPageShow);
    return () => window.removeEventListener("pageshow", onPageShow);
  }, [checkSession]);

  if (failed) {
    return (
      <div className="flex flex-col items-start gap-3 px-page-x py-6">
        <p role="alert">Could not load. Please try again.</p>
        <Button
          onClick={() => {
            setFailed(false); // back to the loading block while we ask again
            checkSession();
          }}
        >
          Try again
        </Button>
      </div>
    );
  }
  if (!roles) {
    // A plain placeholder block while we wait (UX-DR25 skeleton style).
    return <div aria-busy="true" aria-label="Loading" className="m-6 h-24 animate-pulse rounded-lg bg-muted" />;
  }
  return <AppShell roles={roles}>{children}</AppShell>;
}
