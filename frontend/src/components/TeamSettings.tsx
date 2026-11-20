"use client";
// Settings → Team (story 2.5, FR-9, FR-10): invite people, change Roles, deactivate members.
// Only the Owner reaches this page (access.ts), and the backend checks the Role again on
// every call (AD-5). Every change sends the new state, and the answer is the new team list.
import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { InviteForm } from "@/components/InviteForm";
import { LoadFailed } from "@/components/LoadFailed";
import { Button } from "@/components/ui/button";

type Team = components["schemas"]["TeamResponse"];
type TeamMember = components["schemas"]["TeamMember"];
type Role = components["schemas"]["Role"];
type Change = components["schemas"]["MemberUpdate"];

// The Roles the Owner can switch on and off here. The Owner Role itself never changes (MVP).
const SWITCHABLE: { role: Role; label: string }[] = [
  { role: "staff", label: "Staff" },
  { role: "technician", label: "Technician" },
];
const GENERAL_ERROR = "Something went wrong. Please try again.";

export function TeamSettings() {
  const [team, setTeam] = useState<Team | null>(null);
  const [failed, setFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // The member whose change is saving now. All controls are off until the answer comes,
  // so a quick second click cannot send a list built from the old Roles.
  const [pendingId, setPendingId] = useState<string | null>(null);

  const load = useCallback(() => {
    api
      .GET("/api/v1/team")
      .then(({ data }) => (data ? setTeam(data) : setFailed(true)))
      .catch(() => setFailed(true));
  }, []);

  useEffect(load, [load]);

  async function change(member: TeamMember, body: Change) {
    if (pendingId !== null) return; // one change at a time (the controls are disabled too)
    setError(null);
    setPendingId(member.membership_id);
    try {
      const { data, error: reply } = await api.PATCH("/api/v1/team/members/{membership_id}", {
        params: { path: { membership_id: member.membership_id } },
        body,
      });
      if (data) setTeam(data);
      else setError(reply?.error.fields?.[0]?.message ?? reply?.error.message ?? GENERAL_ERROR);
    } catch {
      setError(GENERAL_ERROR);
    } finally {
      setPendingId(null);
    }
  }

  function switchRole(member: TeamMember, role: Role, on: boolean) {
    const roles = on ? [...member.roles, role] : member.roles.filter((r) => r !== role);
    void change(member, { roles: [...new Set(roles)].sort() });
  }

  function deactivate(member: TeamMember) {
    if (window.confirm(`Deactivate ${member.email}? They are logged out at once.`)) {
      void change(member, { is_active: false });
    }
  }

  if (failed) {
    return (
      <LoadFailed
        onRetry={() => {
          setFailed(false);
          load();
        }}
      />
    );
  }

  return (
    <div className="flex w-full max-w-2xl flex-col gap-6">
      <InviteForm />
      {team === null ? (
        // Skeleton rows while we wait (UX-DR25).
        <div aria-busy="true" aria-label="Loading" className="flex flex-col gap-2">
          <div className="h-16 animate-pulse rounded-lg bg-muted" />
          <div className="h-16 animate-pulse rounded-lg bg-muted" />
        </div>
      ) : (
        <section className="flex flex-col gap-3">
          <h2 className="text-lg font-semibold">Members</h2>
          {team.just_you && <p className="text-muted-foreground">Just you for now</p>}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          <ul className="flex flex-col gap-2">
            {team.members.map((member) => {
              const busy = member.membership_id === pendingId;
              return (
                <li
                  key={member.membership_id}
                  aria-busy={busy || undefined}
                  className="flex flex-col gap-2 rounded-lg border bg-card p-4"
                >
                  <p className="font-medium break-all">
                    {member.email}
                    {member.is_you && <span className="text-muted-foreground"> (you)</span>}
                    {member.roles.includes("owner") && <span className="text-muted-foreground"> · Owner</span>}
                  </p>
                  {member.is_active ? (
                    <div className="flex flex-wrap items-center gap-x-6 gap-y-1">
                      {SWITCHABLE.map(({ role, label }) => (
                        <label key={role} className="flex min-h-11 items-center gap-3 text-sm">
                          <input
                            type="checkbox"
                            className="size-5"
                            checked={member.roles.includes(role)}
                            disabled={pendingId !== null}
                            onChange={(e) => switchRole(member, role, e.target.checked)}
                          />
                          {label}
                          {/* Hidden text: each checkbox gets a unique name, e.g. "Staff for ravi@shop.in". */}
                          <span className="sr-only"> for {member.email}</span>
                        </label>
                      ))}
                      {!member.is_you && (
                        <Button
                          variant="destructive"
                          disabled={pendingId !== null}
                          aria-label={`Deactivate ${member.email}`}
                          onClick={() => deactivate(member)}
                        >
                          Deactivate
                        </Button>
                      )}
                    </div>
                  ) : (
                    <div className="flex items-center gap-4">
                      <span className="text-sm text-muted-foreground">Deactivated</span>
                      <Button
                        variant="outline"
                        disabled={pendingId !== null}
                        aria-label={`Reactivate ${member.email}`}
                        onClick={() => void change(member, { is_active: true })}
                      >
                        Reactivate
                      </Button>
                    </div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
      )}
    </div>
  );
}
