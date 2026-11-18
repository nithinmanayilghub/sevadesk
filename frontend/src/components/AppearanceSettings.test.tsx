// Tests for AppearanceSettings: pick System, Light or Dark; it applies at once and is saved.
// If the save fails, the old choice comes back and the page says so.
import { fireEvent, render, screen } from "@testing-library/react";
import { useState } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { type Theme, ThemeProvider } from "@/lib/theme";
import { AppearanceSettings } from "./AppearanceSettings";

vi.mock("@/api/client", () => ({ api: { PUT: vi.fn() } }));
const PUT = vi.mocked(api.PUT);

beforeEach(() => {
  PUT.mockReset();
});

// A real state holder, like the /app layout, so a change shows up on screen.
function Harness({ start }: { start: Theme }) {
  const [theme, setTheme] = useState<Theme>(start);
  return (
    <ThemeProvider theme={theme} setTheme={setTheme}>
      <AppearanceSettings />
    </ThemeProvider>
  );
}

const saved = { response: { ok: true } } as never;
const notSaved = { response: { ok: false } } as never;

test("shows the saved choice", () => {
  render(<Harness start="dark" />);
  expect(screen.getByRole("radio", { name: "Dark" })).toBeChecked();
  expect(screen.getByRole("group", { name: "Theme" })).toBeInTheDocument();
});

test("applies at once and saves", async () => {
  let finish: (value: never) => void = () => {};
  PUT.mockReturnValue(new Promise((resolve) => (finish = resolve)) as never);
  render(<Harness start="dark" />);

  fireEvent.click(screen.getByRole("radio", { name: "Light" }));

  // Checked before the server answers: the change is instant.
  expect(screen.getByRole("radio", { name: "Light" })).toBeChecked();
  expect(PUT).toHaveBeenCalledWith("/api/v1/me/theme", { body: { theme: "light" } });
  finish(saved);
  expect(await screen.findByRole("radio", { name: "Light" })).toBeEnabled();
});

test("goes back and says so when the save fails", async () => {
  PUT.mockResolvedValue(notSaved);
  render(<Harness start="dark" />);

  fireEvent.click(screen.getByRole("radio", { name: "Light" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Could not save. Please try again.");
  expect(screen.getByRole("radio", { name: "Dark" })).toBeChecked();
});

test("goes back and says so when the network is down", async () => {
  PUT.mockRejectedValue(new Error("network down"));
  render(<Harness start="system" />);

  fireEvent.click(screen.getByRole("radio", { name: "Dark" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Could not save. Please try again.");
  expect(screen.getByRole("radio", { name: "System" })).toBeChecked();
});

test("one save at a time: the choices are disabled while saving", async () => {
  let finish: (value: never) => void = () => {};
  PUT.mockReturnValue(new Promise((resolve) => (finish = resolve)) as never);
  render(<Harness start="system" />);

  fireEvent.click(screen.getByRole("radio", { name: "Dark" }));

  for (const name of ["System", "Light", "Dark"]) {
    expect(screen.getByRole("radio", { name })).toBeDisabled();
  }
  finish(saved);
  expect(await screen.findByRole("radio", { name: "System" })).toBeEnabled();
});
