// Tests for AppShell: a bottom tab bar (mobile) and a sidebar (desktop) with the Role's items,
// and the current page marked for screen readers.
import { render, screen, within } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { AppShell } from "./AppShell";

vi.mock("next/navigation", () => ({ usePathname: () => "/app/calendar" }));

test("shows the Owner's items in both navs, and marks the current page", () => {
  render(
    <AppShell roles={["owner", "technician"]}>
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
  render(<AppShell roles={["technician"]}>x</AppShell>);
  expect(screen.queryByRole("link", { name: "Dashboard" })).not.toBeInTheDocument();
});
