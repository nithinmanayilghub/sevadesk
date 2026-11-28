// Tests for BookingSheet (story 5.2, FR-27, UX-DR29): the form that books a job, for a Customer
// who phoned (from the Calendar) or for the Customer of an open chat (from the Conversation).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import type { Permission } from "@/lib/pages";
import { PermissionsProvider } from "@/lib/permissions";
import { BookingSheet } from "./BookingSheet";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn(), POST: vi.fn() } }));
const GET = vi.mocked(api.GET);
const POST = vi.mocked(api.POST);

const SERVICE = { service_id: "svc-1", name: "Fan repair", duration_minutes: 60, price_paise: 49900, is_active: true };
const ONE_TECH = [{ membership_id: "tech-1", email: "ravi@example.com" }];
const TWO_TECHS = [...ONE_TECH, { membership_id: "tech-2", email: "anil@example.com" }];
const SLOTS = {
  timezone: "Asia/Kolkata",
  slots: [{ start: "2026-11-30T04:30:00Z", end: "2026-11-30T05:30:00Z" }], // Mon 10:00 in India
};
const BOOKING = { booking_id: "b-1", state: "confirmed" };

function ok(data: unknown) {
  return Promise.resolve({ data, response: new Response() } as never);
}

function failed(status: number, error: unknown) {
  return Promise.resolve({ data: undefined, error, response: new Response(null, { status }) } as never);
}

function serveGets(technicians = ONE_TECH) {
  GET.mockImplementation(((path: string) =>
    path === "/api/v1/bookings/options" ? ok({ services: [SERVICE], technicians }) : ok(SLOTS)) as never);
}

beforeEach(() => {
  GET.mockReset();
  POST.mockReset();
  serveGets();
  POST.mockImplementation((() => ok(BOOKING)) as never);
});

function renderSheet(props: { conversationId?: string } = {}, permissions: Permission[] = ["use_inbox_and_bookings"]) {
  render(
    <PermissionsProvider permissions={permissions}>
      <BookingSheet {...props} />
    </PermissionsProvider>,
  );
}

// Open the sheet, pick the Service and the one Slot.
async function openAndPick(trigger = "New booking") {
  fireEvent.click(screen.getByRole("button", { name: trigger }));
  fireEvent.change(await screen.findByLabelText("Service"), { target: { value: "svc-1" } });
  const slot = await screen.findByRole("option", { name: "Mon, 30 Nov, 10:00 am" });
  fireEvent.change(screen.getByLabelText("Time"), { target: { value: slot.getAttribute("value") } });
}

function fillCustomer() {
  fireEvent.change(screen.getByLabelText("Customer name"), { target: { value: "Asha" } });
  fireEvent.change(screen.getByLabelText("Phone"), { target: { value: "98765 43210" } });
}

const book = () => fireEvent.click(screen.getByRole("button", { name: "Book" }));

test("users without Inbox access see no button", () => {
  renderSheet({}, []);
  expect(screen.queryByRole("button", { name: "New booking" })).not.toBeInTheDocument();
});

test("nothing loads until the sheet opens", async () => {
  renderSheet();
  expect(GET).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "New booking" }));
  expect(await screen.findByLabelText("Service")).toBeInTheDocument();
});

test("no Technician picker with one Technician", async () => {
  renderSheet();
  await openAndPick();
  expect(screen.queryByLabelText("Technician")).not.toBeInTheDocument();
});

test("a Technician picker with two Technicians", async () => {
  serveGets(TWO_TECHS);
  renderSheet();
  await openAndPick();
  expect(screen.getByRole("option", { name: "anil@example.com" })).toBeInTheDocument();
});

test("phone-in posts name, phone, Service and Slot, then says it is booked", async () => {
  renderSheet();
  await openAndPick();
  fillCustomer();
  book();
  expect(await screen.findByText("Booked: Fan repair, Mon, 30 Nov, 10:00 am.")).toBeInTheDocument();
  expect(POST).toHaveBeenCalledWith("/api/v1/inbox/phone-bookings", {
    body: {
      customer_name: "Asha",
      customer_phone: "98765 43210",
      service_id: "svc-1",
      starts_at: "2026-11-30T04:30:00Z",
      technician_membership_id: null,
    },
  });
});

test("from a chat posts to the Conversation route, with no name or phone", async () => {
  renderSheet({ conversationId: "conv-1" });
  await openAndPick("Book a job");
  expect(screen.queryByLabelText("Customer name")).not.toBeInTheDocument();
  book();
  await screen.findByText(/^Booked:/);
  expect(POST).toHaveBeenCalledWith("/api/v1/inbox/conversations/{conversation_id}/bookings", {
    params: { path: { conversation_id: "conv-1" } },
    body: { service_id: "svc-1", starts_at: "2026-11-30T04:30:00Z", technician_membership_id: null },
  });
});

test("a taken Slot shows the message and loads the Slots again", async () => {
  POST.mockImplementation((() =>
    failed(409, {
      error: { code: "slot_unavailable", message: "This time is no longer free. Pick another time." },
    })) as never);
  renderSheet();
  await openAndPick();
  fillCustomer();
  const slotLoads = () =>
    GET.mock.calls.filter((call) => (call as unknown[])[0] === "/api/v1/bookings/slots").length;
  const before = slotLoads();
  book();
  expect(await screen.findByText("This time is no longer free. Pick another time.")).toBeInTheDocument();
  await waitFor(() => expect(slotLoads()).toBe(before + 1));
});

test("a bad phone shows the field error", async () => {
  POST.mockImplementation((() =>
    failed(422, {
      error: {
        code: "validation_error",
        message: "Some fields need fixing.",
        fields: [{ field: "customer_phone", message: "Enter a valid Indian mobile number." }],
      },
    })) as never);
  renderSheet();
  await openAndPick();
  fillCustomer();
  book();
  expect(await screen.findByText("Enter a valid Indian mobile number.")).toBeInTheDocument();
  expect(screen.getByLabelText("Phone")).toHaveAttribute("aria-invalid", "true");
});

test("a second tap while saving sends one request", async () => {
  POST.mockImplementation((() => new Promise(() => {})) as never); // never answers
  renderSheet();
  await openAndPick();
  fillCustomer();
  book();
  book();
  expect(POST).toHaveBeenCalledTimes(1);
});
