// Tests for LogoutButton: it ends the session on the server, then goes to /login.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { goTo } from "@/lib/navigate";
import { LogoutButton } from "./LogoutButton";

vi.mock("@/api/client", () => ({ api: { POST: vi.fn() } }));
vi.mock("@/lib/navigate", () => ({ goTo: vi.fn() }));
const POST = vi.mocked(api.POST);
beforeEach(() => {
  POST.mockReset();
  vi.mocked(goTo).mockReset();
});

test("logs out on the server, then goes to /login", async () => {
  POST.mockResolvedValue({ response: { ok: true, status: 204 } } as never);
  render(<LogoutButton />);
  fireEvent.click(screen.getByRole("button", { name: "Log out" }));
  await vi.waitFor(() => expect(goTo).toHaveBeenCalledWith("/login"));
  expect(POST).toHaveBeenCalledWith("/api/v1/logout");
});

// Regression (final review): leaving for /login when the server did NOT end the session
// made a shared-phone user think they were logged out while the session still worked.
test("stays and says so when the server could not log out", async () => {
  POST.mockResolvedValue({ error: { error: { code: "internal_error" } }, response: { ok: false, status: 500 } } as never);
  render(<LogoutButton />);
  fireEvent.click(screen.getByRole("button", { name: "Log out" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not log out. Please try again.");
  expect(goTo).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Log out" })).toBeEnabled(); // the user can try again
});

test("stays and says so when the network fails", async () => {
  POST.mockRejectedValue(new Error("network down"));
  render(<LogoutButton />);
  fireEvent.click(screen.getByRole("button", { name: "Log out" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not log out. Please try again.");
  expect(goTo).not.toHaveBeenCalled();
});
