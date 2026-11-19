"use client";
// Settings → Services (story 3.1, FR-12): list, add, edit, deactivate and reactivate Services.
// Only the Owner reaches this page (lib/pages.ts), and the backend checks the Role again on
// every call (AD-5). After any save, the page loads the list again from the backend.
import { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { ServiceForm } from "@/components/ServiceForm";
import { Button } from "@/components/ui/button";
import { formatRupees } from "@/lib/money";

type ServiceOut = components["schemas"]["ServiceOut"];
const GENERAL_ERROR = "Something went wrong. Please try again.";

export function ServicesSettings() {
  const [services, setServices] = useState<ServiceOut[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  // The row whose Deactivate / Activate is saving now. Clicks are ignored meanwhile, but the
  // buttons stay enabled: a disabled button would drop keyboard focus (the story 2.6 bug).
  const [pendingId, setPendingId] = useState<string | null>(null);
  // After an edit form closes, focus goes back to that row's Edit button.
  // A ref, not state: remembering it must not cause an extra render.
  const editButtons = useRef<Record<string, HTMLButtonElement | null>>({});
  const returnFocusTo = useRef<string | null>(null);

  const load = useCallback(() => {
    api
      .GET("/api/v1/services")
      .then(({ data }) => {
        if (!data) return setFailed(true);
        setServices(data.services);
        setError(null); // a fresh list: an old row error no longer applies
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(load, [load]);

  // Runs after the edit form is gone and the row (with its Edit button) is back on screen.
  useEffect(() => {
    if (returnFocusTo.current === null || editingId !== null) return;
    editButtons.current[returnFocusTo.current]?.focus();
    returnFocusTo.current = null;
  }, [editingId]);

  function closeEdit() {
    returnFocusTo.current = editingId;
    setEditingId(null);
  }

  async function setActive(service: ServiceOut, isActive: boolean) {
    if (pendingId !== null) return; // one change at a time
    setError(null);
    setPendingId(service.service_id);
    try {
      // PUT replaces the whole Service, so send every field, with only is_active flipped.
      const { name, duration_minutes, price_paise } = service;
      const { data, error: reply } = await api.PUT("/api/v1/services/{service_id}", {
        params: { path: { service_id: service.service_id } },
        body: { name, duration_minutes, price_paise, is_active: isActive },
      });
      if (data) load();
      else setError(reply?.error.fields?.[0]?.message ?? reply?.error.message ?? GENERAL_ERROR);
    } catch {
      setError(GENERAL_ERROR);
    } finally {
      setPendingId(null);
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

  return (
    <div className="flex w-full max-w-2xl flex-col gap-6">
      {services === null ? (
        // Skeleton rows while we wait (UX-DR25).
        <div aria-busy="true" aria-label="Loading" className="flex flex-col gap-2">
          <div className="h-16 animate-pulse rounded-lg bg-muted" />
          <div className="h-16 animate-pulse rounded-lg bg-muted" />
        </div>
      ) : (
        <section className="flex flex-col gap-3">
          {services.length === 0 && (
            <p className="text-muted-foreground">No Services yet. Add your first one below.</p>
          )}
          {error && (
            <p role="alert" className="text-sm text-destructive">
              {error}
            </p>
          )}
          {/* aria-busy tells screen readers a change is saving. */}
          <ul aria-busy={pendingId !== null || undefined} className="flex flex-col gap-2">
            {services.map((service) =>
              service.service_id === editingId ? (
                <li key={service.service_id}>
                  <ServiceForm
                    initial={service}
                    onSaved={() => {
                      closeEdit();
                      load();
                    }}
                    onCancel={closeEdit}
                  />
                </li>
              ) : (
                <li key={service.service_id} className="flex flex-col gap-3 rounded-lg border bg-card p-4">
                  <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
                    <p className="font-medium break-words">{service.name}</p>
                    <p className="font-semibold">{formatRupees(service.price_paise)}</p>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    {service.duration_minutes} min
                    {!service.is_active && (
                      <>
                        {" · "}
                        <span className="font-medium text-foreground">Inactive</span>
                      </>
                    )}
                  </p>
                  <div className="flex flex-wrap gap-3">
                    <Button
                      variant="outline"
                      ref={(el) => {
                        editButtons.current[service.service_id] = el;
                      }}
                      aria-label={`Edit ${service.name}`}
                      onClick={() => setEditingId(service.service_id)}
                    >
                      Edit
                    </Button>
                    {service.is_active ? (
                      <Button
                        variant="outline"
                        aria-label={`Deactivate ${service.name}`}
                        onClick={() => void setActive(service, false)}
                      >
                        Deactivate
                      </Button>
                    ) : (
                      <Button
                        variant="outline"
                        aria-label={`Activate ${service.name}`}
                        onClick={() => void setActive(service, true)}
                      >
                        Activate
                      </Button>
                    )}
                  </div>
                </li>
              ),
            )}
          </ul>
        </section>
      )}
      <ServiceForm onSaved={load} />
    </div>
  );
}
