// Tests for the Inbox layout (stories 4.3, 4.4): below 1024px ("lg") it shows ONE pane: the
// list, or the open Conversation. From lg it shows both side by side.
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import InboxLayout from "./layout";

const segment = vi.hoisted(() => ({ value: null as string | null }));
vi.mock("next/navigation", () => ({ useSelectedLayoutSegment: () => segment.value }));
vi.mock("@/components/InboxList", () => ({ InboxList: () => <p>the list</p> }));

function layout() {
  render(
    <InboxLayout>
      <p>the thread</p>
    </InboxLayout>,
  );
}

test("no open conversation: the list shows, the thread pane is hidden on mobile", () => {
  segment.value = null;
  layout();
  expect(screen.getByRole("region", { name: "Conversations" })).not.toHaveClass("hidden");
  expect(screen.getByText("the thread").closest("section")).toHaveClass("hidden", "lg:block");
});

test("open conversation: the list is hidden on mobile, the thread shows", () => {
  segment.value = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b";
  layout();
  expect(screen.getByRole("region", { name: "Conversations" })).toHaveClass("hidden", "lg:flex");
  expect(screen.getByText("the thread").closest("section")).not.toHaveClass("hidden");
});
