// Tests for the open-Conversation page (story 4.4): a bad id never reaches the server.
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import Page from "./page";

vi.mock("@/components/ConversationView", async (original) => ({
  ...(await original<typeof import("@/components/ConversationView")>()),
  ConversationView: ({ conversationId }: { conversationId: string }) => <p>view {conversationId}</p>,
}));

async function open(conversationId: string) {
  render(await Page({ params: Promise.resolve({ conversationId }) } as never));
}

test("a bad id shows not found", async () => {
  // Behaviour: /app/inbox/abc shows "not found", not a load error (the API would answer 422).
  await open("abc");
  expect(screen.getByText("This conversation was not found.")).toBeInTheDocument();
  expect(screen.queryByText(/^view/)).not.toBeInTheDocument();
});

test("a good id opens the conversation, with a back link for mobile", async () => {
  await open("0190A1B2-c3d4-7e5f-8a9b-0c1d2e3f4a5b");
  expect(screen.getByText("view 0190A1B2-c3d4-7e5f-8a9b-0c1d2e3f4a5b")).toBeInTheDocument();
  const back = screen.getByRole("link", { name: "← Inbox" });
  expect(back).toHaveAttribute("href", "/app/inbox");
  expect(back).toHaveClass("min-h-11", "lg:hidden");
});
