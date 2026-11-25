// Tests for ClosedDaysSettings: the list ("Fri, 25 Dec"), empty state, Add (and its errors),
// Remove (and where focus goes), and the loading state.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { ClosedDaysSettings } from "./ClosedDaysSettings";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn(), POST: vi.fn(), DELETE: vi.fn() } }));
const GET = vi.mocked(api.GET);
const POST = vi.mocked(api.POST);
const DELETE = vi.mocked(api.DELETE);

const XMAS = { closed_day_id: "c-1", day: "2026-12-25" };

beforeEach(() => {
  GET.mockReset();
  POST.mockReset();
  DELETE.mockReset();
});

function list(closed_days: object[]) {
  return { data: { closed_days } } as never;
}

test("shows a skeleton until the list arrives", () => {
  GET.mockReturnValue(new Promise(() => {}) as never);
  render(<ClosedDaysSettings />);
  expect(screen.getByLabelText("Loading")).toHaveAttribute("aria-busy", "true");
});

test("lists dates as Fri, 25 Dec, each with Remove", async () => {
  GET.mockResolvedValue(list([XMAS]));
  render(<ClosedDaysSettings />);
  expect(await screen.findByText("Fri, 25 Dec")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Remove Fri, 25 Dec" })).toBeInTheDocument();
  expect(GET).toHaveBeenCalledWith("/api/v1/closed-days");
});

test("an empty list says No closed days.", async () => {
  GET.mockResolvedValue(list([]));
  render(<ClosedDaysSettings />);
  expect(await screen.findByText("No closed days.")).toBeInTheDocument();
});

test("the date box has no min: the backend decides what is past, in the Business timezone", async () => {
  GET.mockResolvedValue(list([]));
  render(<ClosedDaysSettings />);
  expect(await screen.findByLabelText("Date")).not.toHaveAttribute("min");
});

test("Add sends the date, then reloads", async () => {
  GET.mockResolvedValue(list([]));
  POST.mockResolvedValue({ data: XMAS } as never);
  render(<ClosedDaysSettings />);
  fireEvent.change(await screen.findByLabelText("Date"), { target: { value: "2026-12-25" } });
  fireEvent.click(screen.getByRole("button", { name: "Add closed day" }));
  await vi.waitFor(() => expect(GET).toHaveBeenCalledTimes(2));
  expect(POST).toHaveBeenCalledWith("/api/v1/closed-days", { body: { day: "2026-12-25" } });
  expect(screen.getByLabelText("Date")).toHaveValue("");
});

test("an empty date box sends null, and the message shows under the box", async () => {
  GET.mockResolvedValue(list([]));
  POST.mockResolvedValue({
    error: { error: { code: "validation_error", message: "Some fields need fixing.", fields: [{ field: "day", message: "Pick a date." }] } },
  } as never);
  render(<ClosedDaysSettings />);
  fireEvent.click(await screen.findByRole("button", { name: "Add closed day" }));
  expect(await screen.findByText("Pick a date.")).toBeInTheDocument();
  expect(POST).toHaveBeenCalledWith("/api/v1/closed-days", { body: { day: null } });
  expect(screen.getByLabelText("Date")).toHaveAttribute("aria-invalid", "true");
});

test("Remove sends DELETE, reloads, and moves focus to the date box", async () => {
  GET.mockResolvedValueOnce(list([XMAS]));
  GET.mockResolvedValueOnce(list([]));
  DELETE.mockResolvedValue({ response: { ok: true } } as never);
  render(<ClosedDaysSettings />);
  fireEvent.click(await screen.findByRole("button", { name: "Remove Fri, 25 Dec" }));
  expect(await screen.findByText("No closed days.")).toBeInTheDocument();
  expect(DELETE).toHaveBeenCalledWith("/api/v1/closed-days/{closed_day_id}", {
    params: { path: { closed_day_id: "c-1" } },
  });
  await vi.waitFor(() => expect(screen.getByLabelText("Date")).toHaveFocus()); // focus moves in an effect
});

test("a Remove that finds the day already gone reloads the list", async () => {
  // Review fix: another tab removed it first. The 404 must not leave a dead row on screen.
  GET.mockResolvedValueOnce(list([XMAS]));
  GET.mockResolvedValueOnce(list([]));
  DELETE.mockResolvedValue({
    response: { ok: false, status: 404 },
    error: { error: { code: "not_found", message: "We could not find that." } },
  } as never);
  render(<ClosedDaysSettings />);
  fireEvent.click(await screen.findByRole("button", { name: "Remove Fri, 25 Dec" }));
  expect(await screen.findByText("No closed days.")).toBeInTheDocument();
  expect(GET).toHaveBeenCalledTimes(2);
});
