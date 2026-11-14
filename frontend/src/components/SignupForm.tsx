"use client";
// Sign-up form (FR-7). The backend owns every validation rule: this form sends the fields
// and shows each error the backend returns next to its field (UX-DR33).
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// The order of the fields on screen. Focus goes to the first one with an error.
const FIELDS = ["business_name", "email", "password"] as const;
type Field = (typeof FIELDS)[number];
type FieldErrors = Partial<Record<Field, string>>;

const GENERAL_ERROR = "Something went wrong. Please try again.";

export function SignupForm() {
  const router = useRouter();
  const [values, setValues] = useState<Record<Field, string>>({ business_name: "", email: "", password: "" });
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputs = useRef<Partial<Record<Field, HTMLInputElement | null>>>({});

  // After new field errors appear on screen, move focus to the first field that has one.
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
      const { data, error } = await api.POST("/api/v1/signup", { body: values });
      if (data) {
        // Sign-up also logged the new Owner in (story 2.2), so go straight to the Dashboard.
        router.replace("/app");
        return;
      }
      // Keep only errors for fields this form shows; anything else becomes a general error.
      const errors: FieldErrors = {};
      for (const item of error?.error.fields ?? []) {
        if ((FIELDS as readonly string[]).includes(item.field)) errors[item.field as Field] = item.message;
      }
      if (Object.keys(errors).length > 0) {
        setFieldErrors(errors);
      } else {
        setGeneralError(error?.error.message ?? GENERAL_ERROR);
      }
    } catch {
      setGeneralError(GENERAL_ERROR);
    } finally {
      setBusy(false);
    }
  }

  // One labelled field, with an optional always-visible hint and its error underneath.
  function field(name: Field, label: string, props: { type?: string; autoComplete?: string; hint?: string }) {
    const error = fieldErrors[name];
    const describedBy = [props.hint && `${name}-hint`, error && `${name}-error`].filter(Boolean).join(" ");
    return (
      <div className="flex flex-col gap-2">
        <Label htmlFor={name}>{label}</Label>
        <Input
          id={name}
          name={name}
          type={props.type ?? "text"}
          autoComplete={props.autoComplete}
          value={values[name]}
          onChange={(e) => setValues({ ...values, [name]: e.target.value })}
          aria-invalid={error ? true : undefined}
          aria-describedby={describedBy || undefined}
          ref={(el) => {
            inputs.current[name] = el;
          }}
        />
        {props.hint && (
          <p id={`${name}-hint`} className="text-sm text-muted-foreground">
            {props.hint}
          </p>
        )}
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
      {field("business_name", "Business name", { autoComplete: "organization" })}
      {field("email", "Email", { type: "email", autoComplete: "email" })}
      {field("password", "Password", {
        type: "password",
        autoComplete: "new-password",
        hint: "At least 12 characters.",
      })}
      {generalError && (
        <p role="alert" className="text-sm text-destructive">
          {generalError}
        </p>
      )}
      <Button type="submit" disabled={busy}>
        {busy ? "Creating…" : "Create my Business"}
      </Button>
    </form>
  );
}
