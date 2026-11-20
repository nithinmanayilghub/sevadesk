// Tests for CopyChatLinkButton: it copies the full chat URL, and has a way out when copy fails.
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { CopyChatLinkButton } from "./CopyChatLinkButton";

const SLUG = "ravi-k7m2qx";
const FALLBACK = "Could not copy. Select the link and copy it.";

afterEach(() => {
  Object.assign(navigator, { clipboard: undefined });
});

test("copies the full chat URL", async () => {
  const writeText = vi.fn().mockResolvedValue(undefined);
  Object.assign(navigator, { clipboard: { writeText } });
  render(<CopyChatLinkButton slug={SLUG} label="Copy link" />);
  fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
  expect(await screen.findByRole("button", { name: "Copied" })).toBeInTheDocument();
  expect(writeText).toHaveBeenCalledWith(`${window.location.origin}/c/${SLUG}`);
});

test("a screen reader hears that the link was copied", async () => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockResolvedValue(undefined) } });
  render(<CopyChatLinkButton slug={SLUG} label="Copy link" />);
  fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
  const message = await screen.findByText("Link copied");
  expect(message.closest("[aria-live]")).not.toBeNull();
});

test("shows a fallback when copy fails", async () => {
  Object.assign(navigator, { clipboard: { writeText: vi.fn().mockRejectedValue(new Error("denied")) } });
  render(<CopyChatLinkButton slug={SLUG} label="Copy link" />);
  fireEvent.click(screen.getByRole("button", { name: "Copy link" }));
  expect(await screen.findByText(FALLBACK)).toBeInTheDocument();
  const input = screen.getByRole("textbox", { name: "Chat link" });
  expect(input).toHaveAttribute("readonly");
  expect(input).toHaveValue(`${window.location.origin}/c/${SLUG}`);
});

test("shows a fallback when there is no clipboard", async () => {
  Object.assign(navigator, { clipboard: undefined });
  render(<CopyChatLinkButton slug={SLUG} label="Copy chat link" />);
  fireEvent.click(screen.getByRole("button", { name: "Copy chat link" }));
  expect(await screen.findByText(FALLBACK)).toBeInTheDocument();
});
