"use client";
// Log-in form (FR-8). Same pattern as SignupForm: the backend owns every rule; this form
// sends the fields and shows each error the backend returns (UX-DR33).
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { landingPath } from "@/lib/auth";

const FIELDS = ["email", "password"] as const;
type Field = (typeof FIELDS)[number];
type FieldErrors = Partial<Record<Field, string>>;

const GENERAL_ERROR = "Something went wrong. Please try again.";

export function LoginForm() {
  const router = useRouter();
  const [values, setValues] = useState<Record<Field, string>>({ email: "", password: "" });
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputs = useRef<Partial<Record<Field, HTMLInputElement | null>>>({});

  // After new field errors appear, move focus to the first field that has one.
  useEffect(() => {
    const first = FIELDS.find((name) => fieldErrors[name]);
    if (first) inputs.current[first]?.focus();
  }, [fieldErrors]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setFieldErrors({});
    setGeneralError(null);
    try {
      const { data, error } = await api.POST("/api/v1/login", { body: values });
      if (data) {
        // The session cookie is set; go to the right first screen for the Roles.
        router.replace(landingPath(data.roles));
        return;
      }
      const errors: FieldErrors = {};
      for (const item of error?.error.fields ?? []) {
        if ((FIELDS as readonly string[]).includes(item.field)) errors[item.field as Field] = item.message;
      }
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors);
      } else {
        // Wrong password (401), too many tries (429), or log-in down (503): the backend's sentence.
        setGeneralError(error?.error.message ?? GENERAL_ERROR);
      }
    } catch {
      setGeneralError(GENERAL_ERROR);
    } finally {
      setBusy(false);
    }
  }

  function field(name: Field, label: string, props: { type: string; autoComplete: string }) {
    const error = fieldErrors[name];
    return (
      <div className="flex flex-col gap-2">
        <Label htmlFor={name}>{label}</Label>
        <Input
          id={name}
          name={name}
          type={props.type}
          autoComplete={props.autoComplete}
          value={values[name]}
          onChange={(e) => setValues({ ...values, [name]: e.target.value })}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${name}-error` : undefined}
          ref={(el) => {
            inputs.current[name] = el;
          }}
        />
        {error && (
          <p id={`${name}-error`} className="text-sm text-destructive">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    // noValidate: the browser's own checks are off, so only the backend's messages show.
    <form noValidate onSubmit={handleSubmit} className="flex flex-col gap-5 rounded-lg border bg-card p-6">
      {field("email", "Email", { type: "email", autoComplete: "email" })}
      {field("password", "Password", { type: "password", autoComplete: "current-password" })}
      {generalError && (
        <p role="alert" className="text-sm text-destructive">
          {generalError}
        </p>
      )}
      <Button type="submit" disabled={busy}>
        {busy ? "Logging in…" : "Log in"}
      </Button>
      <p className="text-sm text-muted-foreground">
        New here?{" "}
        <Link href="/signup" className="font-medium text-foreground underline underline-offset-4">
          Create your Business
        </Link>
      </p>
    </form>
  );
}
