"use client";
// Closed days (story 3.2, FR-13): single dates the Business is closed, whatever the weekly
// hours say (holidays). Add one, or Remove one to open that date again. The backend decides
// what "today" is, in the Business timezone, so the date box has no `min` of its own.
import { useId, useRef, useState, type FormEvent } from "react";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { LoadFailed } from "@/components/LoadFailed";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatDate } from "@/lib/time";
import { useLoad } from "@/lib/useLoad";

type ClosedDayOut = components["schemas"]["ClosedDayOut"];
const GENERAL_ERROR = "Something went wrong. Please try again.";

export function ClosedDaysSettings() {
  const id = useId();
  const loaded = useLoad(() => api.GET("/api/v1/closed-days"), []);
  const [value, setValue] = useState("");
  const [dayError, setDayError] = useState<string | null>(null);
  const [generalError, setGeneralError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // A ref, not only state: two very quick clicks can both run before React re-renders.
  const working = useRef(false);
  const dateInput = useRef<HTMLInputElement | null>(null);

  // Runs one change at a time, and turns a thrown error into the general message.
  async function once(action: () => Promise<void>) {
    if (working.current) return;
    working.current = true;
    setBusy(true);
    setDayError(null);
    setGeneralError(null);
    try {
      await action();
    } catch {
      setGeneralError(GENERAL_ERROR);
    } finally {
      working.current = false;
      setBusy(false);
    }
  }

  function add(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void once(async () => {
      // An empty box is sent as null: the backend answers "Pick a date." under it.
      const { data, error } = await api.POST("/api/v1/closed-days", { body: { day: value || null } });
      if (data) {
        setValue("");
        loaded.reload();
        return;
      }
      const message = error?.error.fields?.find((item) => item.field === "day")?.message;
      if (message) {
        setDayError(message);
        dateInput.current?.focus();
      } else setGeneralError(error?.error.message ?? GENERAL_ERROR);
    });
  }

  function remove(row: ClosedDayOut) {
    void once(async () => {
      const { error, response } = await api.DELETE("/api/v1/closed-days/{closed_day_id}", {
        params: { path: { closed_day_id: row.closed_day_id } },
      });
      // 404: already removed (e.g. in another tab). Either way the day is open now, so
      // reload: the list then matches the backend, with no dead row left on screen.
      if (response.ok || response.status === 404) {
        loaded.reload();
        dateInput.current?.focus(); // the row and its button are gone: focus a stable place
      } else setGeneralError(error?.error.message ?? GENERAL_ERROR);
    });
  }

  if (loaded.status === "failed" || loaded.status === "not_found") return <LoadFailed onRetry={loaded.reload} />;
  const days: ClosedDayOut[] | null = loaded.status === "ready" ? loaded.data.closed_days : null;

  const inputId = `${id}-day`;
  const errorId = `${inputId}-error`;
  return (
    <section aria-label="Closed days" className="flex w-full max-w-2xl flex-col gap-4 rounded-lg border bg-card p-6">
      <h2 className="text-lg font-semibold">Closed days</h2>
      <p className="text-sm text-muted-foreground">Holidays and other days off. They win over the weekly hours.</p>
      {days === null ? (
        // Skeleton rows while we wait (UX-DR25).
        <div aria-busy="true" aria-label="Loading" className="flex flex-col gap-2">
          <div className="h-11 animate-pulse rounded-lg bg-muted" />
        </div>
      ) : days.length === 0 ? (
        <p className="text-muted-foreground">No closed days.</p>
      ) : (
        <ul aria-busy={busy || undefined} className="flex flex-col gap-2">
          {days.map((row) => {
            const label = formatDate(row.day);
            return (
              <li key={row.closed_day_id} className="flex min-h-11 items-center justify-between gap-3">
                <span className="font-medium">{label}</span>
                <Button variant="outline" aria-label={`Remove ${label}`} onClick={() => remove(row)}>
                  Remove
                </Button>
              </li>
            );
          })}
        </ul>
      )}
      {generalError && (
        <p role="alert" className="text-sm text-destructive">
          {generalError}
        </p>
      )}
      <form noValidate onSubmit={add} className="flex flex-wrap items-end gap-3">
        <div className="flex flex-col gap-2">
          <Label htmlFor={inputId}>Date</Label>
          <Input
            id={inputId}
            type="date"
            ref={dateInput}
            className="min-h-11"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            aria-invalid={dayError ? true : undefined}
            aria-describedby={dayError ? errorId : undefined}
          />
        </div>
        {/* Never `disabled`: that drops keyboard focus (story 2.6 bug). Clicks are ignored while busy. */}
        <Button type="submit" aria-disabled={busy || undefined}>
          Add closed day
        </Button>
        {dayError && (
          <p id={errorId} className="w-full text-sm text-destructive">
            {dayError}
          </p>
        )}
      </form>
    </section>
  );
}
