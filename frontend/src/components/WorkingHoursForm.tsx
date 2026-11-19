"use client";
// The weekly Working Hours form (story 3.2, FR-13). Each day is closed, or open with one
// start and one end time. Save replaces the whole week (PUT). The backend owns every rule:
// this form shows its messages under the right day (e.g. "tuesday.end_time") and moves
// focus to the first one (UX-DR33).
import { useCallback, useEffect, useId, useRef, useState, type FormEvent } from "react";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatTimeRange, toTimeInput } from "@/lib/time";

type WorkingHoursOut = components["schemas"]["WorkingHoursOut"];
type WeekIn = components["schemas"]["WeekIn"];

const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;
type Day = (typeof DAYS)[number];
const TIMES = ["start_time", "end_time"] as const;
type TimeField = (typeof TIMES)[number];
const TIME_LABELS: Record<TimeField, string> = { start_time: "Start", end_time: "End" };

// One day as the form holds it: the boxes keep their text even while the day is closed.
type DayForm = { open: boolean; start_time: string; end_time: string };
type WeekForm = Record<Day, DayForm>;
// Keyed by the backend's field path, e.g. "tuesday.end_time".
type FieldErrors = Partial<Record<string, string>>;

// Every field path in screen order: Monday to Sunday, start before end. Focus goes to the
// first one with an error.
const FIELD_ORDER = DAYS.flatMap((day) => TIMES.map((time) => `${day}.${time}`));
const GENERAL_ERROR = "Something went wrong. Please try again.";

function title(day: Day): string {
  return day[0].toUpperCase() + day.slice(1);
}

function formFrom(week: WorkingHoursOut): WeekForm {
  const form = {} as WeekForm;
  for (const day of DAYS) {
    const hours = week[day];
    form[day] = {
      open: hours !== null,
      start_time: toTimeInput(hours?.start_time ?? null),
      end_time: toTimeInput(hours?.end_time ?? null),
    };
  }
  return form;
}

// An empty box is sent as null: the backend then answers "Enter a start time." under it.
function bodyFrom(form: WeekForm): WeekIn {
  const body = {} as WeekIn;
  for (const day of DAYS) {
    const { open, start_time, end_time } = form[day];
    body[day] = open ? { start_time: start_time || null, end_time: end_time || null } : null;
  }
  return body;
}

export function WorkingHoursForm() {
  const id = useId();
  const [form, setForm] = useState<WeekForm | null>(null);
  const [timezone, setTimezone] = useState("");
  const [failed, setFailed] = useState(false);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  // A ref, not only state: two very quick clicks can both run before React re-renders.
  const saving = useRef(false);
  const inputs = useRef<Record<string, HTMLInputElement | null>>({});

  const load = useCallback(() => {
    api
      .GET("/api/v1/working-hours")
      .then(({ data }) => {
        if (!data) return setFailed(true);
        setForm(formFrom(data));
        setTimezone(data.timezone);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(load, [load]);

  // After new field errors appear on screen, move focus to the first field that has one.
  useEffect(() => {
    const first = FIELD_ORDER.find((path) => fieldErrors[path]);
    if (first) inputs.current[first]?.focus();
  }, [fieldErrors]);

  function change(day: Day, patch: Partial<DayForm>) {
    setSaved(false);
    setForm((current) => (current ? { ...current, [day]: { ...current[day], ...patch } } : current));
  }

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!form || saving.current) return; // one save at a time
    saving.current = true;
    setBusy(true);
    setFieldErrors({});
    setGeneralError(null);
    setSaved(false);
    try {
      const { data, error } = await api.PUT("/api/v1/working-hours", { body: bodyFrom(form) });
      if (data) {
        setForm(formFrom(data));
        setSaved(true);
        return;
      }
      const found: FieldErrors = {};
      const other: string[] = [];
      for (const item of error?.error.fields ?? []) {
        // Only "<day>.<time>" belongs under a box; anything else (e.g. "sunday") goes to the alert.
        if (FIELD_ORDER.includes(item.field)) found[item.field] = item.message;
        else other.push(item.message);
      }
      setFieldErrors(found);
      if (other.length > 0) setGeneralError(other.join(" "));
      else if (Object.keys(found).length === 0) setGeneralError(error?.error.message ?? GENERAL_ERROR);
    } catch {
      setGeneralError(GENERAL_ERROR);
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }

  if (failed) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p role="alert">Could not load. Please try again.</p>
        <Button
          onClick={() => {
            setFailed(false);
            load();
          }}
        >
          Try again
        </Button>
      </div>
    );
  }

  if (form === null) {
    // Skeleton rows while we wait (UX-DR25).
    return (
      <div aria-busy="true" aria-label="Loading" className="flex w-full max-w-2xl flex-col gap-2">
        <div className="h-16 animate-pulse rounded-lg bg-muted" />
        <div className="h-16 animate-pulse rounded-lg bg-muted" />
      </div>
    );
  }

  return (
    <form
      noValidate
      onSubmit={handleSubmit}
      aria-label="Weekly hours"
      className="flex w-full max-w-2xl flex-col gap-4 rounded-lg border bg-card p-6"
    >
      <h2 className="text-lg font-semibold">Weekly hours</h2>
      <p className="text-sm text-muted-foreground">Times are in {timezone}.</p>
      {generalError && (
        <p role="alert" className="text-sm text-destructive">
          {generalError}
        </p>
      )}
      {DAYS.map((day) => {
        const { open, start_time, end_time } = form[day];
        const checkboxId = `${id}-${day}-open`;
        return (
          <fieldset key={day} className="flex flex-col gap-3 border-t pt-4 first-of-type:border-t-0 first-of-type:pt-0">
            <legend className="sr-only">{title(day)}</legend>
            <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1">
              {/* The visible name. The legend above names the group for screen readers. */}
              <p aria-hidden="true" className="font-medium">
                {title(day)}
              </p>
              <p className="text-sm text-muted-foreground">
                {open ? (start_time && end_time ? formatTimeRange(start_time, end_time) : "") : "Closed"}
              </p>
            </div>
            <div className="flex min-h-11 items-center gap-2">
              <input
                id={checkboxId}
                type="checkbox"
                checked={open}
                onChange={(e) => change(day, { open: e.target.checked })}
                className="size-5 accent-primary"
              />
              <Label htmlFor={checkboxId}>Open</Label>
            </div>
            {open && (
              <div className="grid grid-cols-2 gap-3">
                {TIMES.map((time) => {
                  const path = `${day}.${time}`;
                  const inputId = `${id}-${path}`;
                  const errorId = `${inputId}-error`;
                  return (
                    <div key={time} className="flex flex-col gap-2">
                      <Label htmlFor={inputId}>{TIME_LABELS[time]}</Label>
                      <Input
                        id={inputId}
                        type="time"
                        ref={(el) => {
                          inputs.current[path] = el;
                        }}
                        className="min-h-11"
                        value={form[day][time]}
                        onChange={(e) => change(day, { [time]: e.target.value })}
                        aria-invalid={fieldErrors[path] ? true : undefined}
                        aria-describedby={fieldErrors[path] ? errorId : undefined}
                      />
                      {fieldErrors[path] && (
                        <p id={errorId} className="text-sm text-destructive">
                          {fieldErrors[path]}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            )}
          </fieldset>
        );
      })}
      <div className="flex flex-wrap items-center gap-3">
        {/* Never `disabled`: that drops keyboard focus (story 2.6 bug). Clicks are ignored while busy. */}
        <Button type="submit" aria-disabled={busy || undefined}>
          {busy ? "Saving…" : "Save hours"}
        </Button>
        <p role="status" className="text-sm text-muted-foreground">
          {saved ? "Saved." : ""}
        </p>
      </div>
    </form>
  );
}
