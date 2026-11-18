// Tests for SettingsLinks: the settings pages on More, shown only to Users who may open them.
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import type { Permission } from "@/lib/pages";
import { PermissionsProvider } from "@/lib/permissions";
import { SettingsLinks } from "./SettingsLinks";

function renderWith(permissions: Permission[]) {
  render(
    <PermissionsProvider permissions={permissions}>
      <SettingsLinks />
    </PermissionsProvider>,
  );
}

test("the Owner sees a Team link", () => {
  renderWith(["manage_setup", "see_own_bookings"]);
  expect(screen.getByRole("link", { name: "Team" })).toHaveAttribute("href", "/app/settings/team");
});

test("a Technician-only User sees no Team link", () => {
  renderWith(["see_own_bookings"]);
  expect(screen.queryByRole("link", { name: "Team" })).not.toBeInTheDocument();
});

test("every User sees Appearance, even with no permissions", () => {
  renderWith([]);
  expect(screen.getByRole("link", { name: "Appearance" })).toHaveAttribute("href", "/app/settings/appearance");
});

test("the Owner sees both Team and Appearance", () => {
  renderWith(["manage_setup"]);
  expect(screen.getByRole("link", { name: "Team" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Appearance" })).toBeInTheDocument();
});
