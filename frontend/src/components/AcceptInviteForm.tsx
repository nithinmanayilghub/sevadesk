"use client";
// Accept an invite (FR-9): check the link, set a password, join the Business, and go in.
// The token travels only in POST bodies, never in an API path (request logs record paths).
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { landingPath } from "@/lib/pages";

// What the page shows: still checking, a dead link, a failed check, or the join form.
type State = { kind: "loading" } | { kind: "invalid" } | { kind: "failed" } | { kind: "ready"; email: string };

const GENERAL_ERROR = "Something went wrong. Please try again.";

export function AcceptInviteForm({ token }: { token: string }) {
  const router = useRouter();
  const [state, setState] = useState<State>({ kind: "loading" });
  const [password, setPassword] = useState("");
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [emailTaken, setEmailTaken] = useState(false);
  const [busy, setBusy] = useState(false);
  const passwordInput = useRef<HTMLInputElement | null>(null);

  const check = useCallback(() => {
    api
      .POST("/api/v1/invites/preview", { body: { token } })
      .then(({ data, error }) => {
        if (data) setState({ kind: "ready", email: data.email });
        else if (error?.error.code === "invite_invalid") setState({ kind: "invalid" });
        else setState({ kind: "failed" });
      })
      .catch(() => setState({ kind: "failed" }));
  }, [token]);

  useEffect(check, [check]);

  // After a new password error appears, move focus to the field.
  useEffect(() => {
    if (passwordError) passwordInput.current?.focus();
  }, [passwordError]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setPasswordError(null);
    setGeneralError(null);
    setEmailTaken(false);
    try {
      const { data, error } = await api.POST("/api/v1/invites/accept", { body: { token, password } });
      if (data) {
        // Joined and logged in: go to the right first page for these Roles. "busy" stays on,
        // so a second tap cannot post the used token again while the page loads.
        router.replace(landingPath(data.permissions));
        return;
      }
      const code = error?.error.code;
      const fieldError = error?.error.fields?.find((item) => item.field === "password");
      if (code === "invite_invalid") setState({ kind: "invalid" }); // used or expired meanwhile
      else if (fieldError) setPasswordError(fieldError.message);
      else {
        setEmailTaken(code === "email_taken");
        setGeneralError(error?.error.message ?? GENERAL_ERROR);
      }
    } catch {
      setGeneralError(GENERAL_ERROR);
    }
    setBusy(false);
  }

  if (state.kind === "loading") {
    return <div aria-busy="true" aria-label="Loading" className="h-40 animate-pulse rounded-lg bg-muted" />;
  }
  if (state.kind === "invalid") {
    return (
      <div className="flex flex-col gap-3">
        <h1 className="text-2xl font-semibold tracking-tight">This invite is no longer valid.</h1>
        <p className="text-muted-foreground">Ask the business owner for a new invite link.</p>
      </div>
    );
  }
  if (state.kind === "failed") {
    return (
      <div className="flex flex-col items-start gap-3">
        <p role="alert">Could not load. Please try again.</p>
        <Button
          onClick={() => {
            setState({ kind: "loading" });
            check();
          }}
        >
          Try again
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Join your team</h1>
      <p className="text-muted-foreground">You&apos;re joining as {state.email}.</p>
      {/* noValidate: the browser's own checks are off, so only the backend's messages show. */}
      <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-5 rounded-lg border bg-card p-6">
        <div className="flex flex-col gap-2">
          <Label htmlFor="password">Password</Label>
          <Input
            id="password"
            type="password"
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            aria-invalid={passwordError ? true : undefined}
            aria-describedby={passwordError ? "password-hint password-error" : "password-hint"}
            ref={passwordInput}
          />
          <p id="password-hint" className="text-sm text-muted-foreground">
            At least 12 characters.
          </p>
          {passwordError && (
            <p id="password-error" className="text-sm text-destructive">
              {passwordError}
            </p>
          )}
        </div>
        {generalError && (
          <div role="alert" className="flex flex-col gap-1 text-sm text-destructive">
            <p>{generalError}</p>
            {emailTaken && (
              <Link href="/login" className="font-medium text-foreground underline underline-offset-4">
                Log in
              </Link>
            )}
          </div>
        )}
        <Button type="submit" disabled={busy}>
          {busy ? "Joining…" : "Join"}
        </Button>
      </form>
    </div>
  );
}
