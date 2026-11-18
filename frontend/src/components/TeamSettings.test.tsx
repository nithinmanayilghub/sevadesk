// Tests for TeamSettings: the member list, "Just you for now", Role changes, deactivate, retry.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { TeamSettings } from "./TeamSettings";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn(), PATCH: vi.fn(), POST: vi.fn() } }));
const GET = vi.mocked(api.GET);
const PATCH = vi.mocked(api.PATCH);

const OWNER = { membership_id: "m-owner", email: "owner@shop.in", roles: ["owner", "technician"], is_active: true, is_you: true };
const TECH = { membership_id: "m-tech", email: "tech@shop.in", roles: ["technician"], is_active: true, is_you: false };

beforeEach(() => {
  GET.mockReset();
  PATCH.mockReset();
  vi.restoreAllMocks();
});

function team(members: object[], just_you: boolean) {
  return { data: { members, just_you } } as never;
}

test("a solo Owner sees Just you for now", async () => {
  GET.mockResolvedValue(team([OWNER], true));
  render(<TeamSettings />);
  expect(await screen.findByText("Just you for now")).toBeInTheDocument();
  expect(GET).toHaveBeenCalledWith("/api/v1/team");
});

test("with a second Technician, the page lists them and does not say Just you", async () => {
  GET.mockResolvedValue(team([OWNER, TECH], false));
  render(<TeamSettings />);
  expect(await screen.findByText("tech@shop.in")).toBeInTheDocument();
  expect(screen.queryByText("Just you for now")).not.toBeInTheDocument();
});

test("ticking Staff sends the member's full new Role list", async () => {
  GET.mockResolvedValue(team([OWNER, TECH], false));
  PATCH.mockResolvedValue(team([OWNER, { ...TECH, roles: ["staff", "technician"] }], false));
  render(<TeamSettings />);
  fireEvent.click(await screen.findByLabelText("Staff for tech@shop.in"));
  await vi.waitFor(() =>
    expect(PATCH).toHaveBeenCalledWith("/api/v1/team/members/{membership_id}", {
      params: { path: { membership_id: "m-tech" } },
      body: { roles: ["staff", "technician"] },
    }),
  );
});

test("the Owner's own row has no Deactivate button", async () => {
  GET.mockResolvedValue(team([OWNER, TECH], false));
  render(<TeamSettings />);
  await screen.findByText("tech@shop.in");
  expect(screen.getAllByRole("button", { name: /Deactivate/ })).toHaveLength(1);
});

test("Deactivate asks first, then sends is_active false", async () => {
  GET.mockResolvedValue(team([OWNER, TECH], false));
  PATCH.mockResolvedValue(team([OWNER, { ...TECH, is_active: false }], false));
  vi.spyOn(window, "confirm").mockReturnValue(true);
  render(<TeamSettings />);
  fireEvent.click(await screen.findByRole("button", { name: "Deactivate tech@shop.in" }));
  expect(window.confirm).toHaveBeenCalledWith("Deactivate tech@shop.in? They are logged out at once.");
  await vi.waitFor(() =>
    expect(PATCH).toHaveBeenCalledWith("/api/v1/team/members/{membership_id}", {
      params: { path: { membership_id: "m-tech" } },
      body: { is_active: false },
    }),
  );
  expect(await screen.findByText("Deactivated")).toBeInTheDocument();
});

test("a failed load shows a retry, and Try again asks again", async () => {
  GET.mockResolvedValueOnce({ response: { status: 503 } } as never).mockResolvedValue(team([OWNER], true));
  render(<TeamSettings />);
  expect(await screen.findByText("Could not load. Please try again.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(await screen.findByText("Just you for now")).toBeInTheDocument();
});

test("while a change saves, the controls are off, so a quick second click sends nothing", async () => {
  // Two quick clicks would both read the old Roles and send a wrong list.
  GET.mockResolvedValue(team([OWNER, TECH], false));
  let finish: (value: unknown) => void = () => {};
  PATCH.mockReturnValue(new Promise((resolve) => (finish = resolve)) as never);
  render(<TeamSettings />);
  fireEvent.click(await screen.findByLabelText("Staff for tech@shop.in"));
  const technician = screen.getByLabelText("Technician for tech@shop.in");
  expect(technician).toBeDisabled();
  expect(screen.getByRole("button", { name: "Deactivate tech@shop.in" })).toBeDisabled();
  fireEvent.click(technician);
  expect(PATCH).toHaveBeenCalledTimes(1);
  expect(screen.getByLabelText("Staff for owner@shop.in")).toBeDisabled(); // one change at a time

  finish(team([OWNER, { ...TECH, roles: ["staff", "technician"] }], false));
  await vi.waitFor(() => expect(screen.getByLabelText("Technician for tech@shop.in")).toBeEnabled());
});

test("a refused change shows the backend's message", async () => {
  GET.mockResolvedValue(team([OWNER, TECH], false));
  PATCH.mockResolvedValue({
    error: { error: { code: "validation_error", message: "Check the fields.", fields: [{ field: "roles", message: "Choose at least one Role." }] } },
    response: { status: 422 },
  } as never);
  render(<TeamSettings />);
  fireEvent.click(await screen.findByLabelText("Technician for tech@shop.in"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Choose at least one Role.");
});
