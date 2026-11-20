// Tests for LoadFailed: the one "Could not load" message with a Try again button.
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { LoadFailed } from "./LoadFailed";

test("says the load failed, as an alert", () => {
  render(<LoadFailed onRetry={() => {}} />);
  expect(screen.getByRole("alert")).toHaveTextContent("Could not load. Please try again.");
});

test("Try again calls onRetry", () => {
  const onRetry = vi.fn();
  render(<LoadFailed onRetry={onRetry} />);
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  expect(onRetry).toHaveBeenCalledOnce();
});
