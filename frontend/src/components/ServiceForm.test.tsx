// Tests for ServiceForm: what it sends (paise, whole minutes, null for blanks), field errors
// with focus (UX-DR33), one save at a time, and an edit that keeps the same values.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { ServiceForm } from "./ServiceForm";

vi.mock("@/api/client", () => ({ api: { POST: vi.fn(), PUT: vi.fn() } }));
const POST = vi.mocked(api.POST);
const PUT = vi.mocked(api.PUT);

const SAVED = { service_id: "s-1", name: "Fan repair", duration_minutes: 60, price_paise: 49900, is_active: true };

beforeEach(() => {
  POST.mockReset();
  PUT.mockReset();
});

function fill(name: string, minutes: string, price: string) {
  fireEvent.change(screen.getByLabelText("Name"), { target: { value: name } });
  fireEvent.change(screen.getByLabelText("Duration (minutes)"), { target: { value: minutes } });
  fireEvent.change(screen.getByLabelText("Price (₹)"), { target: { value: price } });
}

test("add sends paise and whole minutes", async () => {
  POST.mockResolvedValue({ data: SAVED } as never);
  const onSaved = vi.fn();
  render(<ServiceForm onSaved={onSaved} />);
  fill("Fan repair", "60", "1,499");
  fireEvent.click(screen.getByRole("button", { name: "Add Service" }));
  await vi.waitFor(() => expect(onSaved).toHaveBeenCalled());
  expect(POST).toHaveBeenCalledWith("/api/v1/services", {
    body: { name: "Fan repair", duration_minutes: 60, price_paise: 149900, is_active: true },
  });
  expect(screen.getByLabelText("Name")).toHaveValue(""); // cleared for the next one
});

test("an empty duration sends null", async () => {
  POST.mockResolvedValue({ data: SAVED } as never);
  render(<ServiceForm onSaved={vi.fn()} />);
  fill("Fan repair", "", "499");
  fireEvent.click(screen.getByRole("button", { name: "Add Service" }));
  await vi.waitFor(() => expect(POST).toHaveBeenCalled());
  expect(POST.mock.calls[0][1]).toMatchObject({ body: { duration_minutes: null } });
});

test("a Price error shows next to the field and gets focus", async () => {
  POST.mockResolvedValue({
    error: {
      error: {
        code: "validation_error",
        message: "Some fields need fixing.",
        fields: [{ field: "price_paise", message: "Enter a Price in rupees, for example 499." }],
      },
    },
  } as never);
  render(<ServiceForm onSaved={vi.fn()} />);
  fill("Fan repair", "60", "");
  fireEvent.click(screen.getByRole("button", { name: "Add Service" }));
  expect(await screen.findByText("Enter a Price in rupees, for example 499.")).toBeInTheDocument();
  const price = screen.getByLabelText("Price (₹)");
  // Focus moves in a useEffect, which React may run just AFTER the error text is on screen:
  // wait for it, or a slow CI machine checks too early (flaky before).
  await vi.waitFor(() => expect(price).toHaveFocus());
  expect(price).toHaveAttribute("aria-invalid", "true");
});

test("add is sent once while saving", async () => {
  POST.mockReturnValue(new Promise(() => {}) as never); // never answers
  render(<ServiceForm onSaved={vi.fn()} />);
  fill("Fan repair", "60", "499");
  const button = screen.getByRole("button", { name: "Add Service" });
  fireEvent.click(button);
  fireEvent.click(button);
  expect(await screen.findByRole("button", { name: "Saving…" })).toBeInTheDocument();
  expect(POST).toHaveBeenCalledTimes(1);
});

test("the button is never disabled, so keyboard focus stays on it while saving", async () => {
  // A disabled button drops focus to <body> in real browsers (the story 2.6 bug).
  POST.mockReturnValue(new Promise(() => {}) as never);
  render(<ServiceForm onSaved={vi.fn()} />);
  fill("Fan repair", "60", "499");
  const button = screen.getByRole("button", { name: "Add Service" });
  button.focus();
  fireEvent.click(button);
  await screen.findByRole("button", { name: "Saving…" });
  expect(button).not.toBeDisabled();
  expect(button).toHaveAttribute("aria-disabled", "true");
  expect(button).toHaveFocus();
});

test("edit with no changes sends the same values", async () => {
  const initial = { ...SAVED, price_paise: 49950, is_active: false };
  PUT.mockResolvedValue({ data: initial } as never);
  render(<ServiceForm initial={initial} onSaved={vi.fn()} onCancel={vi.fn()} />);
  expect(screen.getByLabelText("Name")).toHaveFocus(); // edit opens on the first field
  fireEvent.click(screen.getByRole("button", { name: "Save" }));
  await vi.waitFor(() => expect(PUT).toHaveBeenCalled());
  expect(PUT).toHaveBeenCalledWith("/api/v1/services/{service_id}", {
    params: { path: { service_id: "s-1" } },
    body: { name: "Fan repair", duration_minutes: 60, price_paise: 49950, is_active: false },
  });
});
