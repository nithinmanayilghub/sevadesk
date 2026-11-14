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
  POST.mockResolvedValue({ response: { status: 204 } } as never);
  render(<LogoutButton />);
  fireEvent.click(screen.getByRole("button", { name: "Log out" }));
  await vi.waitFor(() => expect(goTo).toHaveBeenCalledWith("/login"));
  expect(POST).toHaveBeenCalledWith("/api/v1/logout");
});

test("still goes to /login when the network fails", async () => {
  POST.mockRejectedValue(new Error("network down"));
  render(<LogoutButton />);
  fireEvent.click(screen.getByRole("button", { name: "Log out" }));
  await vi.waitFor(() => expect(goTo).toHaveBeenCalledWith("/login"));
});
