// Tests for LoginForm: labels, the request it sends, where it goes after success,
// the error messages, and the busy state.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { LoginForm } from "./LoginForm";

vi.mock("@/api/client", () => ({ api: { POST: vi.fn() } }));
const { replace } = vi.hoisted(() => ({ replace: vi.fn() }));
vi.mock("next/navigation", () => ({ useRouter: () => ({ replace }) }));
const POST = vi.mocked(api.POST);
beforeEach(() => {
  POST.mockReset();
  replace.mockReset();
});

function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "owner@shop.in" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct horse battery" } });
  fireEvent.click(screen.getByRole("button", { name: "Log in" }));
}

function errorReply(code: string, message: string, fields?: { field: string; message: string }[]) {
  return { error: { error: { code, message, fields } } } as never;
}

test("every control has a text label, and there is a sign-up link", () => {
  render(<LoginForm />);
  expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
  expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  expect(screen.getByRole("link", { name: "Create your Business" })).toHaveAttribute("href", "/signup");
});

test("sends email and password, then goes to the landing page for the Roles", async () => {
  POST.mockResolvedValue({ data: { roles: ["technician"] } } as never);
  render(<LoginForm />);
  fillAndSubmit();
  await vi.waitFor(() => expect(replace).toHaveBeenCalledWith("/app/calendar"));
  expect(POST).toHaveBeenCalledWith("/api/v1/login", {
    body: { email: "owner@shop.in", password: "correct horse battery" },
  });
});

test("shows a wrong password as a general error", async () => {
  POST.mockResolvedValue(errorReply("invalid_credentials", "Wrong email or password."));
  render(<LoginForm />);
  fillAndSubmit();
  expect(await screen.findByRole("alert")).toHaveTextContent("Wrong email or password.");
});

test("shows the lock message after too many tries", async () => {
  POST.mockResolvedValue(errorReply("too_many_attempts", "Too many tries. Please wait 15 minutes and try again."));
  render(<LoginForm />);
  fillAndSubmit();
  expect(await screen.findByRole("alert")).toHaveTextContent("Too many tries. Please wait 15 minutes and try again.");
});

test("shows a field error next to its field and focuses it", async () => {
  POST.mockResolvedValue(
    errorReply("validation_error", "Some fields need fixing.", [{ field: "password", message: "Enter your password." }]),
  );
  render(<LoginForm />);
  fillAndSubmit();
  expect(await screen.findByText("Enter your password.")).toBeInTheDocument();
  await vi.waitFor(() => expect(document.activeElement).toBe(screen.getByLabelText("Password")));
});

test("disables the button while the request runs", async () => {
  POST.mockReturnValue(new Promise(() => {}) as never); // never answers
  render(<LoginForm />);
  fillAndSubmit();
  expect(await screen.findByRole("button", { name: "Logging in…" })).toBeDisabled();
});
