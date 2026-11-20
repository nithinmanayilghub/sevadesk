// Tests for SetupChecklist on the Dashboard: Add Services -> Set Working Hours -> Copy chat link.
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import type { Permission } from "@/lib/pages";
import { PermissionsProvider } from "@/lib/permissions";
import { SetupChecklist } from "./SetupChecklist";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn() } }));
const GET = vi.mocked(api.GET);

beforeEach(() => GET.mockReset());

function renderWith(setup: { has_services: boolean; has_working_hours: boolean }, permissions: Permission[] = ["manage_setup"]) {
  GET.mockResolvedValue({ data: { chat_slug: "ravi-k7m2qx", ...setup } } as never);
  return render(
    <PermissionsProvider permissions={permissions}>
      <SetupChecklist />
    </PermissionsProvider>,
  );
}

test("shows three steps for a new Business", async () => {
  renderWith({ has_services: false, has_working_hours: false });
  expect(await screen.findByRole("link", { name: "Add Services" })).toHaveAttribute("href", "/app/settings/services");
  expect(screen.getByRole("link", { name: "Set Working Hours" })).toHaveAttribute("href", "/app/settings/hours");
  expect(screen.getByText("Copy chat link")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Copy chat link" })).not.toBeInTheDocument();
});

test("marks done steps", async () => {
  renderWith({ has_services: true, has_working_hours: false });
  expect(await screen.findByRole("link", { name: "Add Services, done" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Set Working Hours" })).toBeInTheDocument();
});

test("turns emerald with a Copy chat link button when both are done", async () => {
  renderWith({ has_services: true, has_working_hours: true });
  expect(await screen.findByRole("button", { name: "Copy chat link" })).toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Set up your chat link" })).toHaveClass("bg-brand-soft");
});

test("shows Coming soon. without manage_setup, and asks the API nothing", () => {
  renderWith({ has_services: false, has_working_hours: false }, []);
  expect(screen.getByText("Coming soon.")).toBeInTheDocument();
  expect(screen.queryByRole("region")).not.toBeInTheDocument();
  expect(GET).not.toHaveBeenCalled();
});
