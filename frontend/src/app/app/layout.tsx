"use client";
// Layout for every /app page: asks the backend who is logged in, then shows the app shell.
// No session? GET /api/v1/me returns 401, and the API client sends the User to /login.
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { AppShell } from "@/components/AppShell";

export default function AppLayout({ children }: LayoutProps<"/app">) {
  const [roles, setRoles] = useState<string[] | null>(null);

  useEffect(() => {
    api.GET("/api/v1/me").then(({ data }) => {
      if (data) setRoles(data.roles);
    });
  }, []);

  if (!roles) {
    // A plain placeholder block while we wait (UX-DR25 skeleton style).
    return <div aria-busy="true" aria-label="Loading" className="m-6 h-24 animate-pulse rounded-lg bg-muted" />;
  }
  return <AppShell roles={roles}>{children}</AppShell>;
}
