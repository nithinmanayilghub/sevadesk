// Tests for ServicesSettings: the list (Indian-grouped Prices), empty state, Deactivate,
// a failed change, and unique ids when an edit form and the add form show together.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { ServicesSettings } from "./ServicesSettings";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn(), POST: vi.fn(), PUT: vi.fn() } }));
const GET = vi.mocked(api.GET);
const PUT = vi.mocked(api.PUT);

const FAN = { service_id: "s-1", name: "Fan repair", duration_minutes: 60, price_paise: 10000000, is_active: true };

beforeEach(() => {
  GET.mockReset();
  PUT.mockReset();
});

function list(services: object[]) {
  return { data: { services } } as never;
}

test("rows show Indian-grouped Prices and minutes", async () => {
  GET.mockResolvedValue(list([FAN]));
  render(<ServicesSettings />);
  expect(await screen.findByText("₹1,00,000")).toBeInTheDocument();
  expect(screen.getByText("60 min")).toBeInTheDocument();
  expect(GET).toHaveBeenCalledWith("/api/v1/services");
});

test("an empty list says No Services yet", async () => {
  GET.mockResolvedValue(list([]));
  render(<ServicesSettings />);
  expect(await screen.findByText("No Services yet. Add your first one below.")).toBeInTheDocument();
});

test("Deactivate sends the full row with is_active false, then reloads", async () => {
  GET.mockResolvedValue(list([FAN]));
  PUT.mockResolvedValue({ data: { ...FAN, is_active: false } } as never);
  render(<ServicesSettings />);
  fireEvent.click(await screen.findByRole("button", { name: "Deactivate Fan repair" }));
  await vi.waitFor(() => expect(GET).toHaveBeenCalledTimes(2));
  expect(PUT).toHaveBeenCalledWith("/api/v1/services/{service_id}", {
    params: { path: { service_id: "s-1" } },
    body: { name: "Fan repair", duration_minutes: 60, price_paise: 10000000, is_active: false },
  });
});

test("an inactive row says Inactive and offers Activate", async () => {
  GET.mockResolvedValue(list([{ ...FAN, is_active: false }]));
  render(<ServicesSettings />);
  expect(await screen.findByText("Inactive")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Activate Fan repair" })).toBeInTheDocument();
});

test("a failed Deactivate shows an alert", async () => {
  GET.mockResolvedValue(list([FAN]));
  PUT.mockResolvedValue({ error: { error: { code: "forbidden", message: "You don't have access to this." } } } as never);
  render(<ServicesSettings />);
  fireEvent.click(await screen.findByRole("button", { name: "Deactivate Fan repair" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("You don't have access to this.");
});

test("editing keeps ids unique next to the add form", async () => {
  GET.mockResolvedValue(list([FAN]));
  render(<ServicesSettings />);
  fireEvent.click(await screen.findByRole("button", { name: "Edit Fan repair" }));
  const names = screen.getAllByLabelText("Name");
  expect(names).toHaveLength(2);
  expect(names[0].id).not.toBe(names[1].id);
  expect(within(screen.getByRole("form", { name: "Edit Fan repair" })).getByLabelText("Name")).toHaveValue("Fan repair");
});

test("Cancel closes the edit form and puts focus back on Edit", async () => {
  GET.mockResolvedValue(list([FAN]));
  render(<ServicesSettings />);
  fireEvent.click(await screen.findByRole("button", { name: "Edit Fan repair" }));
  fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
  expect(screen.getByRole("button", { name: "Edit Fan repair" })).toHaveFocus();
});
