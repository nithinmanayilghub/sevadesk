"use client";
// BookingSheet (story 5.2, FR-27, UX-DR29): a team member books a job.
// - Without conversationId (the Calendar): for a Customer who phoned. Name and phone are asked.
// - With conversationId (an open chat, UJ-2): for that chat's Customer. No name or phone.
// Owner and Staff only: the button shows only with "use_inbox_and_bookings". The backend checks
// the Role again on every request (AD-5); hiding the button is only for show.
//
// How it loads: nothing until the sheet opens (the form is only rendered while open). Then the
// form facts (active Services, active Technicians); after a Service is picked, its free Slots.
// The Technician picker shows only with 2+ Technicians: with one, the server assigns them.
//
// The backend owns every rule (UX-DR33): a 422 puts its messages under the fields; a 409 (the
// time was just taken) shows its message and loads the Slots again.
import { useRef, useState } from "react";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { errorsForFields } from "@/lib/errorsForFields";
import { usePermissions } from "@/lib/permissions";
import { formatSlot } from "@/lib/time";
import { useLoad } from "@/lib/useLoad";
import { LoadFailed } from "./LoadFailed";

type Options = components["schemas"]["BookingOptionsOut"];
type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];

// Every field the server can name in a 422, in screen order.
const FIELDS = ["customer_name", "customer_phone", "service_id", "starts_at", "technician_membership_id"] as const;
type Field = (typeof FIELDS)[number];

// The same look as <Input>, for the native <select>s (there is no shadcn Select in this app).
const SELECT = "h-11 w-full rounded-md border border-input bg-background px-3 text-base";

export function BookingSheet({ conversationId }: { conversationId?: string }) {
  const mayBook = usePermissions().includes("use_inbox_and_bookings");
  if (!mayBook) return null;
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" className="min-h-11">
          {conversationId ? "Book a job" : "New booking"}
        </Button>
      </SheetTrigger>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>{conversationId ? "Book a job" : "New booking"}</SheetTitle>
          <SheetDescription>
            {conversationId ? "A confirmed job for this customer." : "A confirmed job for a customer who phoned."}
          </SheetDescription>
        </SheetHeader>
        {/* Only rendered while the sheet is open, so the data loads when it opens. */}
        <BookingForm conversationId={conversationId} />
      </SheetContent>
    </Sheet>
  );
}

function BookingForm({ conversationId }: { conversationId?: string }) {
  const options = useLoad(() => api.GET("/api/v1/bookings/options"), []);
  if (options.status === "loading") {
    return <div aria-busy="true" aria-label="Loading booking form" className="mx-4 h-40 animate-pulse rounded-xl bg-muted" />;
  }
  if (options.status !== "ready") return <LoadFailed onRetry={options.reload} />;
  return <FormFields conversationId={conversationId} options={options.data} />;
}

function FormFields({ conversationId, options }: { conversationId?: string; options: Options }) {
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [serviceId, setServiceId] = useState("");
  const [start, setStart] = useState("");
  const [technicianId, setTechnicianId] = useState("");
  // Raised after a 409, so the Slot list loads again (the taken time drops out).
  const [slotsVersion, setSlotsVersion] = useState(0);
  const [fieldErrors, setFieldErrors] = useState<Partial<Record<Field, string>>>({});
  const [message, setMessage] = useState("");
  const [booked, setBooked] = useState("");
  const [busy, setBusy] = useState(false);
  // A ref, not only state: two quick taps can both run before React shows "busy".
  const saving = useRef(false);

  // No Service picked yet: no request, just "no Slots" (the Time box is not shown then).
  const slots = useLoad(
    () =>
      serviceId
        ? api.GET("/api/v1/bookings/slots", { params: { query: { service_id: serviceId } } })
        : Promise.resolve({ data: { timezone: "", slots: [] }, response: new Response() }),
    [serviceId, slotsVersion],
  );
  const timezone = slots.status === "ready" ? slots.data.timezone : "Asia/Kolkata";
  const service = options.services.find((item) => item.service_id === serviceId);
  // With one Technician the server assigns them: no picker, no question (UX-DR29).
  const pickTechnician = options.technicians.length > 1;

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    if (saving.current) return;
    saving.current = true;
    setBusy(true);
    setFieldErrors({});
    setMessage("");
    const choice = {
      service_id: serviceId,
      starts_at: start,
      technician_membership_id: pickTechnician && technicianId ? technicianId : null,
    };
    try {
      const { data, error, response } = conversationId
        ? await api.POST("/api/v1/inbox/conversations/{conversation_id}/bookings", {
            params: { path: { conversation_id: conversationId } },
            body: choice,
          })
        : await api.POST("/api/v1/inbox/phone-bookings", {
            body: { customer_name: name, customer_phone: phone, ...choice },
          });
      if (data) {
        setBooked(`Booked: ${service?.name ?? "job"}, ${formatSlot(start, timezone)}.`);
        return;
      }
      const envelope = error as ErrorEnvelope | undefined;
      if (response.status === 409) {
        // Taken meanwhile (or the Technician is busy): show why, and offer fresh times.
        setMessage(envelope?.error.message ?? "This time is no longer free. Pick another time.");
        setStart("");
        setSlotsVersion((version) => version + 1);
        return;
      }
      const found = errorsForFields(envelope, FIELDS);
      setFieldErrors(found);
      if (Object.keys(found).length === 0) setMessage("Could not save the booking. Try again.");
    } catch {
      setMessage("Could not save the booking. Try again."); // network down
    } finally {
      saving.current = false;
      setBusy(false);
    }
  }

  if (booked) {
    return (
      <p role="status" className="px-4">
        {booked}
      </p>
    );
  }

  // One labelled box with its error under it. The id links the label, box and message.
  function field(id: Field, label: string, box: (props: FieldProps) => React.ReactNode) {
    const error = fieldErrors[id];
    const errorId = `${id}-error`;
    return (
      <div className="flex flex-col gap-1">
        <Label htmlFor={id}>{label}</Label>
        {box({ id, "aria-invalid": error ? true : undefined, "aria-describedby": error ? errorId : undefined })}
        {error && (
          <p id={errorId} className="text-sm text-destructive">
            {error}
          </p>
        )}
      </div>
    );
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="flex flex-col gap-4 px-4" noValidate>
      {!conversationId && (
        <>
          {field("customer_name", "Customer name", (props) => (
            <Input {...props} value={name} onChange={(event) => setName(event.target.value)} autoComplete="off" />
          ))}
          {field("customer_phone", "Phone", (props) => (
            <Input {...props} type="tel" value={phone} onChange={(event) => setPhone(event.target.value)} />
          ))}
        </>
      )}

      {field("service_id", "Service", (props) => (
        <select
          {...props}
          className={SELECT}
          value={serviceId}
          onChange={(event) => {
            setServiceId(event.target.value);
            setStart(""); // another Service has other Slots
          }}
        >
          <option value="">Pick a service</option>
          {options.services.map((item) => (
            <option key={item.service_id} value={item.service_id}>
              {item.name}
            </option>
          ))}
        </select>
      ))}

      {serviceId &&
        field("starts_at", "Time", (props) => (
          <select {...props} className={SELECT} value={start} onChange={(event) => setStart(event.target.value)}>
            <option value="">{slots.status === "loading" ? "Loading times…" : "Pick a time"}</option>
            {slots.status === "ready" &&
              slots.data.slots.map((slot) => (
                <option key={slot.start} value={slot.start}>
                  {formatSlot(slot.start, slots.data.timezone)}
                </option>
              ))}
          </select>
        ))}
      {serviceId && slots.status === "ready" && slots.data.slots.length === 0 && (
        <p className="text-sm text-muted-foreground">No free times in the next 7 days.</p>
      )}
      {serviceId && slots.status === "failed" && <LoadFailed onRetry={slots.reload} />}

      {pickTechnician &&
        field("technician_membership_id", "Technician", (props) => (
          <select
            {...props}
            className={SELECT}
            value={technicianId}
            onChange={(event) => setTechnicianId(event.target.value)}
          >
            <option value="">Pick a technician</option>
            {options.technicians.map((technician) => (
              <option key={technician.membership_id} value={technician.membership_id}>
                {technician.email}
              </option>
            ))}
          </select>
        ))}

      {message && (
        <p role="alert" className="text-sm text-destructive">
          {message}
        </p>
      )}
      {/* aria-disabled, not disabled: a disabled button loses keyboard focus. submit ignores taps. */}
      <Button type="submit" className="min-h-11 self-start" aria-disabled={busy || undefined}>
        Book
      </Button>
    </form>
  );
}

type FieldProps = {
  id: string;
  "aria-invalid": true | undefined;
  "aria-describedby": string | undefined;
};
