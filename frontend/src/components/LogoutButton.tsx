"use client";
// Log out (FR-8): the server deletes the session at once, then we go to /login.
// If the server could NOT delete it, we stay and say so: leaving would make the User
// think they are logged out while their session still works (e.g. on a shared phone).
import { LogOut } from "lucide-react";
import { useState } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { goTo } from "@/lib/navigate";

export function LogoutButton() {
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  async function handleClick() {
    setBusy(true);
    setFailed(false);
    try {
      const { response } = await api.POST("/api/v1/logout");
      if (response.ok) {
        // A full page load, so no screen keeps data from the old session in memory.
        goTo("/login");
        return;
      }
    } catch {
      // network down: fall through to the message
    }
    setFailed(true);
    setBusy(false);
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <Button variant="outline" onClick={handleClick} disabled={busy}>
        <LogOut aria-hidden="true" />
        Log out
      </Button>
      {failed && (
        <p role="alert" className="text-sm text-destructive">
          Could not log out. Please try again.
        </p>
      )}
    </div>
  );
}
