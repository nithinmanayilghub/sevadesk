// Tests for StatusBadge (UX-DR6): a pill with a label AND an icon, never color alone.
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { StatusBadge } from "./StatusBadge";

test.each([
  ["agent", "Agent"],
  ["handoff", "Needs Human"],
  ["closed", "Closed"],
] as const)("state %s shows the label %s with a hidden icon", (state, label) => {
  const { container } = render(<StatusBadge state={state} />);
  expect(screen.getByText(label)).toBeInTheDocument();
  // The icon is decoration: the text already says it, so screen readers skip the icon.
  expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
});
