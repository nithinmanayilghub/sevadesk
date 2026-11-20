// Tests for ChatLinkSettings: the full chat link with a Copy link button, and a failed load.
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { ChatLinkSettings } from "./ChatLinkSettings";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn() } }));
const GET = vi.mocked(api.GET);

beforeEach(() => GET.mockReset());

test("shows the link and a Copy link button", async () => {
  GET.mockResolvedValue({ data: { chat_slug: "ravi-k7m2qx", has_services: true, has_working_hours: true } } as never);
  render(<ChatLinkSettings />);
  expect(await screen.findByText(`${window.location.origin}/c/ravi-k7m2qx`)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
  expect(GET).toHaveBeenCalledWith("/api/v1/setup");
});

test("shows an error with retry when loading fails", async () => {
  GET.mockResolvedValue({ data: undefined } as never);
  render(<ChatLinkSettings />);
  fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
  await vi.waitFor(() => expect(GET).toHaveBeenCalledTimes(2));
});
