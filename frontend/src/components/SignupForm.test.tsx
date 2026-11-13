// Tests for SignupForm: labels, the request it sends, success, field errors, general errors,
// and the busy state while the request runs.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { SignupForm } from "./SignupForm";

vi.mock("@/api/client", () => ({ api: { POST: vi.fn() } }));
const POST = vi.mocked(api.POST);
beforeEach(() => {
  POST.mockReset();
});

function fillAndSubmit() {
  fireEvent.change(screen.getByLabelText("Business name"), { target: { value: "Sharma Plumbing" } });
  fireEvent.change(screen.getByLabelText("Email"), { target: { value: "owner@shop.in" } });
  fireEvent.change(screen.getByLabelText("Password"), { target: { value: "correct horse battery" } });
  fireEvent.click(screen.getByRole("button", { name: "Create my Business" }));
}

function errorReply(code: string, fields?: { field: string; message: string }[]) {
  return { error: { error: { code, message: "Some fields need fixing.", fields } } } as never;
}

test("every control has a text label", () => {
  render(<SignupForm />);
  expect(screen.getByLabelText("Business name")).toBeInTheDocument();
  expect(screen.getByLabelText("Email")).toHaveAttribute("type", "email");
  expect(screen.getByLabelText("Password")).toHaveAttribute("type", "password");
  expect(screen.getByText("At least 12 characters.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Create my Business" })).toBeInTheDocument();
});

test("sends the three fields to the sign-up endpoint", async () => {
  POST.mockResolvedValue({ data: { business_id: "b1", business_name: "Sharma Plumbing" } } as never);
  render(<SignupForm />);
  fillAndSubmit();
  await screen.findByRole("status");
  expect(POST).toHaveBeenCalledWith("/api/v1/signup", {
    body: { business_name: "Sharma Plumbing", email: "owner@shop.in", password: "correct horse battery" },
  });
});

test("shows the success message", async () => {
  POST.mockResolvedValue({ data: { business_id: "b1", business_name: "Sharma Plumbing" } } as never);
  render(<SignupForm />);
  fillAndSubmit();
  expect(await screen.findByRole("status")).toHaveTextContent("Your Business “Sharma Plumbing” is ready.");
});

test("shows field errors next to fields and focuses the first one", async () => {
  POST.mockResolvedValue(
    errorReply("validation_error", [
      { field: "password", message: "Use at least 12 characters." },
      { field: "email", message: "Enter a valid email address." },
    ]),
  );
  render(<SignupForm />);
  fillAndSubmit();
  const email = screen.getByLabelText("Email");
  expect(await screen.findByText("Enter a valid email address.")).toBeInTheDocument();
  expect(email).toHaveAttribute("aria-invalid", "true");
  expect(email).toHaveAccessibleDescription("Enter a valid email address.");
  expect(screen.getByLabelText("Password")).toHaveAccessibleDescription(
    "At least 12 characters. Use at least 12 characters.",
  );
  // Email comes before password on the form, so focus goes to email.
  expect(document.activeElement).toBe(email);
});

test("shows a taken email next to the email field", async () => {
  POST.mockResolvedValue(
    errorReply("email_taken", [{ field: "email", message: "An account with this email already exists." }]),
  );
  render(<SignupForm />);
  fillAndSubmit();
  expect(await screen.findByText("An account with this email already exists.")).toBeInTheDocument();
  expect(screen.getByLabelText("Email")).toHaveAttribute("aria-invalid", "true");
});

test("shows the server message when there are no field errors", async () => {
  POST.mockResolvedValue({
    error: { error: { code: "internal_error", message: "Something went wrong. Please try again." } },
  } as never);
  render(<SignupForm />);
  fillAndSubmit();
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Please try again.");
});

test("shows a general error when the network fails", async () => {
  POST.mockRejectedValue(new Error("network down"));
  render(<SignupForm />);
  fillAndSubmit();
  expect(await screen.findByRole("alert")).toHaveTextContent("Something went wrong. Please try again.");
});

test("disables the button while the request runs", async () => {
  POST.mockReturnValue(new Promise(() => {}) as never); // never answers
  render(<SignupForm />);
  fillAndSubmit();
  const button = await screen.findByRole("button", { name: "Creating…" });
  expect(button).toBeDisabled();
});
