// Tests for CustomerSheet (story 4.5, NFR-8, UX-DR28): the Owner-only Customer detail sheet
// and the delete confirm dialog.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import type { Permission } from "@/lib/pages";
import { PermissionsProvider } from "@/lib/permissions";
import { CustomerSheet } from "./CustomerSheet";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn(), DELETE: vi.fn() } }));
const push = vi.fn();
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));
const GET = vi.mocked(api.GET);
const DELETE = vi.mocked(api.DELETE);

const CUSTOMER = {
  customer_id: "cust-1",
  created_at: "2026-11-20T10:00:00Z",
  conversation_count: 1,
  message_count: 3,
};

beforeEach(() => {
  GET.mockReset();
  DELETE.mockReset();
  push.mockReset();
  GET.mockResolvedValue({ data: CUSTOMER, response: new Response() } as never);
});

function renderAs(permissions: Permission[]) {
  render(
    <PermissionsProvider permissions={permissions}>
      <CustomerSheet conversationId="conv-1" />
    </PermissionsProvider>,
  );
}

const OWNER: Permission[] = ["use_inbox_and_bookings", "manage_customer_data"];

async function openConfirm() {
  fireEvent.click(screen.getByRole("button", { name: "Customer" }));
  expect(await screen.findByText("3")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Delete customer" }));
  return screen.findByRole("alertdialog");
}

test("the owner sees a Customer button", () => {
  renderAs(OWNER);
  expect(screen.getByRole("button", { name: "Customer" })).toBeInTheDocument();
});

test("staff (no manage_customer_data) see no Customer button", () => {
  renderAs(["use_inbox_and_bookings"]);
  expect(screen.queryByRole("button", { name: "Customer" })).not.toBeInTheDocument();
});

test("the sheet shows the Customer's counts", async () => {
  renderAs(OWNER);
  fireEvent.click(screen.getByRole("button", { name: "Customer" }));
  expect(await screen.findByText("3")).toBeInTheDocument(); // messages
  expect(screen.getByText("20 Nov 2026")).toBeInTheDocument(); // Customer since
  expect(GET).toHaveBeenCalledWith("/api/v1/inbox/conversations/{conversation_id}/customer", {
    params: { path: { conversation_id: "conv-1" } },
  });
});

test("the confirm names what is deleted and says it cannot be undone", async () => {
  renderAs(OWNER);
  const dialog = await openConfirm();
  expect(dialog).toHaveTextContent("This deletes their 1 conversation and 3 messages. This cannot be undone.");
});

test("confirm deletes and goes back to the Inbox", async () => {
  DELETE.mockResolvedValue({ response: new Response(null, { status: 204 }) } as never);
  renderAs(OWNER);
  await openConfirm();
  fireEvent.click(screen.getByRole("button", { name: "Delete customer" }));
  await vi.waitFor(() => expect(push).toHaveBeenCalledWith("/app/inbox"));
  expect(DELETE).toHaveBeenCalledWith("/api/v1/inbox/customers/{customer_id}", {
    params: { path: { customer_id: "cust-1" } },
  });
});

test("a failed delete shows an alert and stays", async () => {
  DELETE.mockResolvedValue({ response: new Response(null, { status: 500 }) } as never);
  renderAs(OWNER);
  await openConfirm();
  fireEvent.click(screen.getByRole("button", { name: "Delete customer" }));
  expect(await screen.findByText("Could not delete the customer. Try again.")).toBeInTheDocument();
  expect(push).not.toHaveBeenCalled();
});

test("cancel deletes nothing", async () => {
  renderAs(OWNER);
  await openConfirm();
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  await vi.waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
  expect(DELETE).not.toHaveBeenCalled();
});

test("the sheet has a description for screen readers", async () => {
  renderAs(OWNER);
  fireEvent.click(screen.getByRole("button", { name: "Customer" }));
  const sheet = await screen.findByRole("dialog");
  expect(sheet).toHaveAccessibleDescription("Details and data deletion for this customer.");
});