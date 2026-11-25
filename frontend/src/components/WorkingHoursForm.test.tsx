// Tests for WorkingHoursForm: the week (open / closed days), "10:00 am – 6:00 pm" text,
// what Save sends, errors under the right day, focus, and loading / failed states.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { WorkingHoursForm } from "./WorkingHoursForm";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn(), PUT: vi.fn() } }));
const GET = vi.mocked(api.GET);
const PUT = vi.mocked(api.PUT);

const SAVED = { start_time: "10:00:00", end_time: "18:00:00" };
const DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"] as const;
// Mon–Sat 10–6, Sunday closed.
const WEEK = { timezone: "Asia/Kolkata", ...Object.fromEntries(DAYS.map((d) => [d, d === "sunday" ? null : SAVED])) };

beforeEach(() => {
  GET.mockReset();
  PUT.mockReset();
});

function day(name: string) {
  return within(screen.getByRole("group", { name }));
}

async function renderLoaded(week: object = WEEK) {
  GET.mockResolvedValue({ data: week } as never);
  render(<WorkingHoursForm />);
  await screen.findByRole("group", { name: "Monday" });
}

function sentBody() {
  return (PUT.mock.calls[0][1] as { body: Record<string, unknown> }).body;
}

test("shows a skeleton until the week arrives", () => {
  GET.mockReturnValue(new Promise(() => {}) as never);
  render(<WorkingHoursForm />);
  expect(screen.getByLabelText("Loading")).toHaveAttribute("aria-busy", "true");
});

test("shows 7 days; an open day has times and its range, a closed day says Closed", async () => {
  await renderLoaded();
  const names = screen.getAllByRole("group").map((group) => group.querySelector("legend")?.textContent);
  expect(names).toEqual(["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]);
  expect(day("Monday").getByRole("checkbox", { name: "Open" })).toBeChecked();
  expect(day("Monday").getByLabelText("Start")).toHaveValue("10:00");
  expect(day("Monday").getByText("10:00 am – 6:00 pm")).toBeInTheDocument();
  expect(day("Sunday").getByRole("checkbox", { name: "Open" })).not.toBeChecked();
  expect(day("Sunday").getByText("Closed")).toBeInTheDocument();
  expect(day("Sunday").queryByLabelText("Start")).not.toBeInTheDocument();
  expect(screen.getByText("Times are in Asia/Kolkata.")).toBeInTheDocument();
});

test("ticking Open on a closed day shows two empty time boxes", async () => {
  await renderLoaded();
  fireEvent.click(day("Sunday").getByRole("checkbox", { name: "Open" }));
  expect(day("Sunday").getByLabelText("Start")).toHaveValue("");
  expect(day("Sunday").getByLabelText("End")).toHaveValue("");
});

test("Save sends the full week, closed days as null", async () => {
  await renderLoaded();
  PUT.mockResolvedValue({ data: WEEK } as never);
  fireEvent.change(day("Monday").getByLabelText("End"), { target: { value: "17:30" } });
  fireEvent.click(screen.getByRole("button", { name: "Save hours" }));
  await vi.waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));
  expect(PUT.mock.calls[0][0]).toBe("/api/v1/working-hours");
  expect(sentBody()).toEqual({
    ...Object.fromEntries(DAYS.map((d) => [d, d === "sunday" ? null : { start_time: "10:00", end_time: "18:00" }])),
    monday: { start_time: "10:00", end_time: "17:30" },
  });
  expect(await screen.findByText("Saved.")).toBeInTheDocument();
});

test("an empty time box sends null", async () => {
  await renderLoaded();
  PUT.mockResolvedValue({ data: WEEK } as never);
  fireEvent.click(day("Sunday").getByRole("checkbox", { name: "Open" }));
  fireEvent.click(screen.getByRole("button", { name: "Save hours" }));
  await vi.waitFor(() => expect(PUT).toHaveBeenCalledTimes(1));
  expect(sentBody().sunday).toEqual({ start_time: null, end_time: null });
});

test("a field error shows under its day, and focus moves to the first error", async () => {
  await renderLoaded();
  PUT.mockResolvedValue({
    error: {
      error: {
        code: "validation_error",
        message: "Some fields need fixing.",
        fields: [
          { field: "friday.end_time", message: "Enter an end time." },
          { field: "tuesday.end_time", message: "End time must be after the start time." },
        ],
      },
    },
  } as never);
  fireEvent.click(screen.getByRole("button", { name: "Save hours" }));
  expect(await day("Tuesday").findByText("End time must be after the start time.")).toBeInTheDocument();
  expect(day("Friday").getByText("Enter an end time.")).toBeInTheDocument();
  // Focus moves in a useEffect, just after the text shows: wait for it (flaky on slow CI before).
  await vi.waitFor(() => expect(day("Tuesday").getByLabelText("End")).toHaveFocus()); // Tuesday comes before Friday
  expect(day("Tuesday").getByLabelText("End")).toHaveAttribute("aria-invalid", "true");
});

test("a field error with no day goes to the general alert", async () => {
  await renderLoaded();
  PUT.mockResolvedValue({
    error: { error: { code: "validation_error", message: "Some fields need fixing.", fields: [{ field: "sunday", message: "This field is required." }] } },
  } as never);
  fireEvent.click(screen.getByRole("button", { name: "Save hours" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("This field is required.");
});

test("Save is sent once while saving, and the button keeps focus", async () => {
  await renderLoaded();
  PUT.mockReturnValue(new Promise(() => {}) as never); // never answers
  const button = screen.getByRole("button", { name: "Save hours" });
  button.focus();
  fireEvent.click(button);
  fireEvent.click(button);
  expect(PUT).toHaveBeenCalledTimes(1);
  expect(button).not.toBeDisabled(); // disabled would drop keyboard focus (story 2.6 bug)
  expect(button).toHaveFocus();
});

test("a load failure offers Try again", async () => {
  GET.mockRejectedValueOnce(new Error("offline"));
  GET.mockResolvedValueOnce({ data: WEEK } as never);
  render(<WorkingHoursForm />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load. Please try again.");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByRole("group", { name: "Monday" })).toBeInTheDocument();
});
