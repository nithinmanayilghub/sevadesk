"use client";
// One form to add a Service, or to edit one (story 3.1, FR-12). The backend owns every rule:
// this form only turns the typed text into numbers, then shows the backend's messages under
// their fields and moves focus to the first one (UX-DR33).
import { useEffect, useId, useRef, useState, type FormEvent } from "react";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { paiseToRupeesText, rupeesToPaise } from "@/lib/money";

type ServiceOut = components["schemas"]["ServiceOut"];

// The order of the fields on screen. Focus goes to the first one with an error.
const FIELDS = ["name", "duration_minutes", "price_paise"] as const;
type Field = (typeof FIELDS)[number];
type FieldErrors = Partial<Record<Field, string>>;

const LABELS: Record<Field, string> = {
  name: "Name",
  duration_minutes: "Duration (minutes)",
  price_paise: "Price (₹)",
};
// inputMode picks the phone keyboard: digits only for minutes, digits and "." for rupees.
const INPUT_MODES = { name: "text", duration_minutes: "numeric", price_paise: "decimal" } as const;
const GENERAL_ERROR = "Something went wrong. Please try again.";

function textFrom(service?: ServiceOut): Record<Field, string> {
  if (!service) return { name: "", duration_minutes: "", price_paise: "" };
  return {
    name: service.name,
    duration_minutes: String(service.duration_minutes),
    price_paise: paiseToRupeesText(service.price_paise),
  };
}

// Digits only. A blank box must be null: Number("") is 0, which would hide the real message.
function minutesFrom(text: string): number | null {
  return /^\d+$/.test(text.trim()) ? Number(text) : null;
}

type Props = {
  initial?: ServiceOut; // given = edit this Service; missing = add a new one
  onSaved: () => void;
  onCancel?: () => void;
};

export function ServiceForm({ initial, onSaved, onCancel }: Props) {
  // useId gives this form its own prefix, so the add form and an edit form on the same
  // page never share an id (a shared id breaks the label <-> input link).
  const id = useId();
  const [values, setValues] = useState(() => textFrom(initial));
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const inputs = useRef<Partial<Record<Field, HTMLInputElement | null>>>({});
  const editing = initial !== undefined;

  // An edit form opens with focus on its first field.
  useEffect(() => {
    if (editing) inputs.current.name?.focus();
  }, [editing]);

  // After new field errors appear on screen, move focus to the first field that has one.
  useEffect(() => {
    const first = FIELDS.find((name) => fieldErrors[name]);
    if (first) inputs.current[first]?.focus();
  }, [fieldErrors]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return; // one save at a time: a double tap must not add the Service twice
    setBusy(true);
    setFieldErrors({});
    setGeneralError(null);
    const body = {
      name: values.name,
      duration_minutes: minutesFrom(values.duration_minutes),
      price_paise: rupeesToPaise(values.price_paise),
      // A new Service starts active. An edit keeps its own state (Deactivate is a row button).
      is_active: initial?.is_active ?? true,
    };
    try {
      const { data, error } = initial
        ? await api.PUT("/api/v1/services/{service_id}", { params: { path: { service_id: initial.service_id } }, body })
        : await api.POST("/api/v1/services", { body });
      if (data) {
        if (!editing) setValues(textFrom()); // ready for the next one
        onSaved();
        return;
      }
      const found: FieldErrors = {};
      for (const item of error?.error.fields ?? []) {
        if ((FIELDS as readonly string[]).includes(item.field)) found[item.field as Field] = item.message;
      }
      if (Object.keys(found).length > 0) setFieldErrors(found);
      else setGeneralError(error?.error.message ?? GENERAL_ERROR);
    } catch {
      setGeneralError(GENERAL_ERROR);
    } finally {
      setBusy(false);
    }
  }

  const title = editing ? `Edit ${initial.name}` : "Add a Service";
  return (
    <form
      noValidate
      onSubmit={handleSubmit}
      aria-label={title}
      className="flex w-full flex-col gap-5 rounded-lg border bg-card p-6"
    >
      {!editing && <h2 className="text-lg font-semibold">{title}</h2>}
      {FIELDS.map((field) => {
        const inputId = `${id}-${field}`;
        const errorId = `${inputId}-error`;
        return (
          <div key={field} className="flex flex-col gap-2">
            <Label htmlFor={inputId}>{LABELS[field]}</Label>
            <Input
              id={inputId}
              ref={(el) => {
                inputs.current[field] = el;
              }}
              inputMode={INPUT_MODES[field]}
              autoComplete="off"
              value={values[field]}
              onChange={(e) => setValues((current) => ({ ...current, [field]: e.target.value }))}
              aria-invalid={fieldErrors[field] ? true : undefined}
              aria-describedby={fieldErrors[field] ? errorId : undefined}
            />
            {fieldErrors[field] && (
              <p id={errorId} className="text-sm text-destructive">
                {fieldErrors[field]}
              </p>
            )}
          </div>
        );
      })}
      {generalError && (
        <p role="alert" className="text-sm text-destructive">
          {generalError}
        </p>
      )}
      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={busy}>
          {busy ? "Saving…" : editing ? "Save" : "Add Service"}
        </Button>
        {onCancel && (
          <Button type="button" variant="outline" onClick={onCancel}>
            Cancel
          </Button>
        )}
      </div>
    </form>
  );
}
