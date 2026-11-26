// Tests for AppShell: a bottom tab bar (mobile) and a sidebar (desktop) with the Role's items,
// and the current page marked for screen readers.
import { render, screen, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { AppShell } from "./AppShell";

const path = vi.hoisted(() => ({ current: "/app/calendar" }));
vi.mock("next/navigation", () => ({ usePathname: () => path.current }));
beforeEach(() => {
  path.current = "/app/calendar";
});

test("shows the Owner's items in both navs, and marks the current page", () => {
  render(
    <AppShell permissions={["manage_setup", "use_inbox_and_bookings", "see_own_bookings", "see_dashboard"]}>
      <p>page body</p>
    </AppShell>,
  );
  for (const name of ["Main", "Sidebar"]) {
    const nav = within(screen.getByRole("navigation", { name }));
    expect(nav.getAllByRole("link").map((link) => link.textContent)).toEqual(["Dashboard", "Inbox", "Calendar", "More"]);
    expect(nav.getByRole("link", { name: "Calendar" })).toHaveAttribute("aria-current", "page");
    expect(nav.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
  }
  expect(screen.getByText("page body")).toBeInTheDocument();
});

test("a Technician-only User sees no Dashboard", () => {
  render(<AppShell permissions={["see_own_bookings"]}>x</AppShell>);
  expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
});

test("on a settings page, More is the current item", () => {
  path.current = "/app/settings/team";
  render(<AppShell permissions={["manage_setup", "see_own_bookings"]}>x</AppShell>);
  for (const name of ["Main", "Sidebar"]) {
    const nav = within(screen.getByRole("navigation", { name }));
    expect(nav.getByRole("link", { name: "More" })).toHaveAttribute("aria-current", "page");
  }
});

// Story 4.3: the red Needs Human count on the Inbox tab (UX-DR16).
const OWNER_PERMISSIONS = ["manage_setup", "use_inbox_and_bookings", "see_own_bookings", "see_dashboard"] as const;

test("shows a red count on Inbox, read once by screen readers", () => {
  render(<AppShell permissions={[...OWNER_PERMISSIONS]} inboxCount={3}>x</AppShell>);
  for (const name of ["Main", "Sidebar"]) {
    const nav = within(screen.getByRole("navigation", { name }));
    expect(nav.getByRole("link", { name: "Inbox, 3 need a human" })).toBeInTheDocument();
    expect(nav.getByText("3")).toHaveAttribute("aria-hidden", "true");
  }
});

test("shows 99+ above 99", () => {
  render(<AppShell permissions={[...OWNER_PERMISSIONS]} inboxCount={150}>x</AppShell>);
  expect(screen.getAllByText("99+")).toHaveLength(2);
  expect(screen.getAllByRole("link", { name: "Inbox, 150 need a human" })).toHaveLength(2);
});

test("no pill at 0", () => {
  render(<AppShell permissions={[...OWNER_PERMISSIONS]} inboxCount={0}>x</AppShell>);
  expect(screen.getAllByRole("link", { name: "Inbox" })).toHaveLength(2);
});

test("no pill when inboxCount is omitted", () => {
  render(<AppShell permissions={[...OWNER_PERMISSIONS]}>x</AppShell>);
  expect(screen.getAllByRole("link", { name: "Inbox" })).toHaveLength(2);
});
