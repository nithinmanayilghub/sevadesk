// Tests for InviteForm: the request it sends, the link it shows, copy, and field errors.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { InviteForm } from "./InviteForm";

vi.mock("@/api/client", () => ({ api: { POST: vi.fn() } }));
const POST = vi.mocked(api.POST);
const writeText = vi.fn();
beforeEach(() => {
  POST.mockReset();
  writeText.mockReset().mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
});

function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "tech@shop.in" } });
  fireEvent.click(within(screen.getByRole("group", { name: "Roles" })).getByLabelText("Technician"));
  fireEvent.click(screen.getByRole("button", { name: "Create invite link" }));
}

test("sends the email and Roles, then shows the link to copy", async () => {
  POST.mockResolvedValue({ data: { token: "abc123", expires_at: "2026-11-23T10:00:00Z" } } as never);
  render(<InviteForm />);
  fillAndSubmit();
  const link = await screen.findByLabelText("Invite link");
  expect(POST).toHaveBeenCalledWith("/api/v1/team/invites", { body: { email: "tech@shop.in", roles: ["technician"] } });
  expect(link).toHaveValue(`${window.location.origin}/invite/abc123`);
  expect(screen.getByText("Works once. Expires in 7 days.")).toBeInTheDocument();

  fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
  expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/invite/abc123`);
  expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
});

test("shows a Roles error under the Roles group", async () => {
  POST.mockResolvedValue({
    error: {
      error: {
        code: "validation_error",
        message: "Some fields need fixing.",
        fields: [{ field: "roles", message: "Choose at least one Role." }],
      },
    },
  } as never);
  render(<InviteForm />);
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "tech@shop.in" } });
  fireEvent.click(screen.getByRole("button", { name: "Create invite link" }));
  expect(await screen.findByText("Choose at least one Role.")).toBeInTheDocument();
  expect(screen.getByRole("group", { name: "Roles" })).toHaveAccessibleDescription("Choose at least one Role.");
});
