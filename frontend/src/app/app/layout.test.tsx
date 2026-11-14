// Tests for the /app layout. Regression (story 2.2 live check): after log-out, the browser's
// Back button showed the app from Chrome's back-forward cache without asking the server.
import { act, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import AppLayout from "./layout";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn() } }));
vi.mock("next/navigation", () => ({ usePathname: () => "/app" }));
const GET = vi.mocked(api.GET);
beforeEach(() => {
  GET.mockReset();
  GET.mockResolvedValue({ data: { roles: ["owner"] } } as never);
});

function restoreFromBackForwardCache() {
  // What Chrome fires when Back shows a frozen copy of the page.
  const event = new Event("pageshow");
  Object.defineProperty(event, "persisted", { value: true });
  window.dispatchEvent(event);
}

test("shows the shell for the logged-in User", async () => {
  render(<AppLayout params={Promise.resolve({})}>body</AppLayout>);
  expect(await screen.findByRole("navigation", { name: "Main" })).toBeInTheDocument();
  expect(GET).toHaveBeenCalledWith("/api/v1/me");
});

test("asks the server again when Back restores the page from the cache", async () => {
  render(<AppLayout params={Promise.resolve({})}>body</AppLayout>);
  await screen.findByRole("navigation", { name: "Main" });
  act(() => restoreFromBackForwardCache());
  // A second /me call: after log-out it returns 401, and the API client goes to /login.
  await vi.waitFor(() => expect(GET).toHaveBeenCalledTimes(2));
});
