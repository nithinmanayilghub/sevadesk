"use client";
// Log out (FR-8): the server deletes the session at once, then we go to /login.
import { LogOut } from "lucide-react";
import { useState } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { goTo } from "@/lib/navigate";

export function LogoutButton() {
  const [busy, setBusy] = useState(false);

  async function handleClick() {
    setBusy(true);
    try {
      await api.POST("/api/v1/logout");
    } catch {
      // Even if the network failed, leave the app; the next request will be a 401 anyway.
    }
    // A full page load, so no screen keeps data from the old session in memory.
    goTo("/login");
  }

  return (
    <Button variant="outline" onClick={handleClick} disabled={busy}>
      <LogOut aria-hidden="true" />
      Log out
    </Button>
  );
}
