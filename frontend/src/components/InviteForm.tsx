"use client";
// Invite form on Settings → Team (FR-9). The Owner enters an email and Roles, and gets a
// single-use link to copy and send (SevaDesk sends no email). The backend owns every rule:
// this form shows the backend's messages under their fields (UX-DR33).
import { useState, type FormEvent } from "react";
import { api } from "@/api/client";
import { errorsForFields } from "@/lib/errorsForFields";
import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

type Role = components["schemas"]["Role"];
const FIELDS = ["email", "roles"] as const;
type Field = (typeof FIELDS)[number];

// The Roles an Owner may give (the backend refuses Owner).
const ROLE_CHOICES: { role: Role; label: string }[] = [
  { role: "staff", label: "Staff" },
  { role: "technician", label: "Technician" },
];
const GENERAL_ERROR = "Something went wrong. Please try again.";

export function InviteForm() {
  const [email, setEmail] = useState("");
  const [roles, setRoles] = useState<Role[]>([]);
  const [errors, setErrors] = useState<Partial<Record<Field, string>>>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [link, setLink] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  function toggleRole(role: Role, on: boolean) {
    setRoles((current) => (on ? [...current, role] : current.filter((r) => r !== role)));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setErrors({});
    setGeneralError(null);
    setLink(null);
    setCopied(false);
    try {
      const { data, error } = await api.POST("/api/v1/team/invites", { body: { email, roles } });
      if (data) {
        // The raw token comes back only this once. The page builds the full link from it.
        setLink(`${window.location.origin}/invite/${data.token}`);
        return;
      }
      const found = errorsForFields(error, FIELDS);
      if (Object.keys(found).length > 0) setErrors(found);
      else setGeneralError(error?.error.message ?? GENERAL_ERROR);
    } catch {
      setGeneralError(GENERAL_ERROR);
    } finally {
      setBusy(false);
    }
  }

  async function copyLink() {
    if (!link) return;
    try {
      await navigator.clipboard.writeText(link);
      setCopied(true);
    } catch {
      // No clipboard (old browser, no permission): the link field selects itself on tap instead.
    }
  }

  return (
    <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-5 rounded-lg border bg-card p-6">
      <h2 className="text-lg font-semibold">Invite someone</h2>
      <div className="flex flex-col gap-2">
        <Label htmlFor="invite-email">Email</Label>
        <Input
          id="invite-email"
          type="email"
          autoComplete="off"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-invalid={errors.email ? true : undefined}
          aria-describedby={errors.email ? "invite-email-error" : undefined}
        />
        {errors.email && (
          <p id="invite-email-error" className="text-sm text-destructive">
            {errors.email}
          </p>
        )}
      </div>

      <fieldset className="flex flex-col gap-2" aria-describedby={errors.roles ? "invite-roles-error" : undefined}>
        <legend className="mb-2 text-sm font-medium">Roles</legend>
        {ROLE_CHOICES.map(({ role, label }) => (
          <label key={role} className="flex min-h-11 items-center gap-3 text-sm">
            <input
              type="checkbox"
              className="size-5"
              checked={roles.includes(role)}
              onChange={(e) => toggleRole(role, e.target.checked)}
            />
            {label}
          </label>
        ))}
        {errors.roles && (
          <p id="invite-roles-error" className="text-sm text-destructive">
            {errors.roles}
          </p>
        )}
      </fieldset>

      {generalError && (
        <p role="alert" className="text-sm text-destructive">
          {generalError}
        </p>
      )}
      <Button type="submit" disabled={busy}>
        {busy ? "Creating…" : "Create invite link"}
      </Button>

      {/* aria-live: a screen reader reads the new link out when it appears. */}
      <div aria-live="polite">
        {link && (
          <div className="flex flex-col gap-2">
            <Label htmlFor="invite-link">Invite link</Label>
            <Input id="invite-link" readOnly value={link} onFocus={(e) => e.target.select()} />
            <p className="text-sm text-muted-foreground">Works once. Expires in 7 days.</p>
            <Button type="button" variant="outline" onClick={copyLink}>
              {copied ? "Copied" : "Copy link"}
            </Button>
          </div>
        )}
      </div>
    </form>
  );
}
