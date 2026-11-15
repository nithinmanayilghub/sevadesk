// Tests for the /app layout. Regression (story 2.2 live check): after log-out, the browser's
// Back button showed the app from Chrome's back-forward cache without asking the server.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import AppLayout from "./layout";

// The current page. vi.hoisted makes it exist before the mock below runs; each test may change it.
const location = vi.hoisted(() => ({ pathname: "/app" }));
vi.mock("@/api/client", () => ({ api: { GET: vi.fn() } }));
vi.mock("next/navigation", () => ({ usePathname: () => location.pathname }));
const GET = vi.mocked(api.GET);
const OWNER = {
  roles: ["owner", "technician"],
  permissions: ["manage_setup", "use_inbox_and_bookings", "see_own_bookings", "see_dashboard"],
};
const TECHNICIAN = { roles: ["technician"], permissions: ["see_own_bookings"] };
beforeEach(() => {
  location.pathname = "/app";
  GET.mockReset();
  GET.mockResolvedValue({ data: OWNER } as never);
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

test("a Technician-only User on a forbidden page sees the no-access message in the normal shell", async () => {
  location.pathname = "/app/inbox";
  GET.mockResolvedValue({ data: TECHNICIAN } as never);
  render(<AppLayout params={Promise.resolve({})}>inbox body</AppLayout>);
  expect(await screen.findByRole("heading", { name: "You don't have access to this page." })).toBeInTheDocument();
  expect(screen.queryByText("inbox body")).not.toBeInTheDocument();
  // The nav stays, so the User can go to a page they may use.
  expect(screen.getAllByRole("link", { name: "Calendar" }).length).toBeGreaterThan(0);
});

test("an Owner on the same page sees the page itself", async () => {
  location.pathname = "/app/inbox";
  render(<AppLayout params={Promise.resolve({})}>inbox body</AppLayout>);
  expect(await screen.findByText("inbox body")).toBeInTheDocument();
  expect(screen.queryByText("You don't have access to this page.")).not.toBeInTheDocument();
});

// Regression (final review): any failure other than 401 left the loading block on screen forever.
test("shows an error with a retry when /me fails with a server error", async () => {
  GET.mockResolvedValueOnce({ error: { error: { code: "internal_error" } }, response: { status: 500 } } as never);
  render(<AppLayout params={Promise.resolve({})}>body</AppLayout>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load. Please try again.");
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  // The second call (the default mock) succeeds, and the shell appears.
  expect(await screen.findByRole("navigation", { name: "Main" })).toBeInTheDocument();
});

test("shows the same error when the network fails", async () => {
  GET.mockRejectedValueOnce(new Error("network down"));
  render(<AppLayout params={Promise.resolve({})}>body</AppLayout>);
  expect(await screen.findByRole("alert")).toHaveTextContent("Could not load. Please try again.");
});

test("asks the server again when Back restores the page from the cache", async () => {
  render(<AppLayout params={Promise.resolve({})}>body</AppLayout>);
  await screen.findByRole("navigation", { name: "Main" });
  act(() => restoreFromBackForwardCache());
  // A second /me call: after log-out it returns 401, and the API client goes to /login.
  await vi.waitFor(() => expect(GET).toHaveBeenCalledTimes(2));
});
