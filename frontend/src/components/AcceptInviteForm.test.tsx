// Tests for AcceptInviteForm: check the link, set a password, join, and every error state.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { AcceptInviteForm } from "./AcceptInviteForm";

vi.mock("@/api/client", () => ({ api: { POST: vi.fn() } }));
const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
const POST = vi.mocked(api.POST);

const INVALID = {
  error: { error: { code: "invite_invalid", message: "This invite is no longer valid." } },
  response: { status: 404 },
} as never;

// POST answers by path: preview first, then accept.
function answer(preview: unknown, accept?: unknown) {
  POST.mockImplementation(((path: string) =>
    Promise.resolve(path === "/api/v1/invites/preview" ? preview : accept)) as never);
}

beforeEach(() => {
  POST.mockReset();
  replace.mockReset();
});

function join(password = "correct horse battery") {
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: password } });
  fireEvent.click(screen.getByRole("button", { name: "Join" }));
}

test("an invalid link says so and shows no password field", async () => {
  answer(INVALID);
  render(<AcceptInviteForm token="t1" />);
  expect(await screen.findByRole("heading", { name: "This invite is no longer valid." })).toBeInTheDocument();
  expect(screen.queryByLabelText("Password")).not.toBeInTheDocument();
  expect(POST).toHaveBeenCalledWith("/api/v1/invites/preview", { body: { token: "t1" } });
});

test("a failed check offers a retry", async () => {
  answer({ error: { error: { code: "internal_error", message: "x" } }, response: { status: 500 } });
  render(<AcceptInviteForm token="t1" />);
  expect(await screen.findByText("Could not load. Please try again.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
});

test("a valid link shows the email, and Join logs in and goes to the right page", async () => {
  answer({ data: { email: "tech@shop.in" } }, { data: { roles: ["technician"], permissions: ["see_own_bookings"] } });
  render(<AcceptInviteForm token="t1" />);
  expect(await screen.findByText("You're joining as tech@shop.in.")).toBeInTheDocument();
  join();
  await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/app/calendar"));
  expect(POST).toHaveBeenCalledWith("/api/v1/invites/accept", {
    body: { token: "t1", password: "correct horse battery" },
  });
});

test("a short password shows its field error and focuses the field", async () => {
  answer(
    { data: { email: "tech@shop.in" } },
    {
      error: {
        error: {
          code: "validation_error",
          message: "Some fields need fixing.",
          fields: [{ field: "password", message: "Use at least 12 characters." }],
        },
      },
    },
  );
  render(<AcceptInviteForm token="t1" />);
  await screen.findByLabelText("Password");
  join("short");
  expect(await screen.findByText("Use at least 12 characters.")).toBeInTheDocument();
  await vi.waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText("Password")));
});

test("an email that already has an account shows the message and a log-in link", async () => {
  const message = "An account with this email already exists.";
  answer(
    { data: { email: "tech@shop.in" } },
    { error: { error: { code: "email_taken", message, fields: [{ field: "email", message }] } } },
  );
  render(<AcceptInviteForm token="t1" />);
  await screen.findByLabelText("Password");
  join();
  expect(await screen.findByRole("alert")).toHaveTextContent(message);
  expect(screen.getByRole("link", { name: "Log in" })).toHaveAttribute("href", "/login");
});

test("an invite used meanwhile switches to the invalid state", async () => {
  answer({ data: { email: "tech@shop.in" } }, INVALID);
  render(<AcceptInviteForm token="t1" />);
  await screen.findByLabelText("Password");
  join();
  expect(await screen.findByRole("heading", { name: "This invite is no longer valid." })).toBeInTheDocument();
});

test("after a successful join the button stays off while the next page loads", async () => {
  // A second tap would post the used token again and flash "no longer valid" at a new member.
  answer({ data: { email: "tech@shop.in" } }, { data: { roles: ["technician"], permissions: ["see_own_bookings"] } });
  render(<AcceptInviteForm token="t1" />);
  await screen.findByText("You're joining as tech@shop.in.");
  join();
  await vi.waitFor(() => expect(replace).toHaveBeenCalled());
  expect(screen.getByRole("button", { name: "Joining…" })).toBeDisabled();
});
