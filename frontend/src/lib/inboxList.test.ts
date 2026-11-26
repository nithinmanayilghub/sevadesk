// Tests for how Inbox pages and polls join the list on screen (story 4.3).
import { expect, test } from "vitest";
import type { components } from "@/api/schema";
import { appendPage, mergePoll, pollLimit, POLL_MAX } from "./inboxList";

type InboxPage = components["schemas"]["InboxPage"];

function row(id: string) {
  return { conversation_id: id, state: "agent", last_message_preview: id, last_message_at: "2026-11-25T05:00:00Z" } as const;
}

function page(ids: string[], next_cursor: string | null = null): InboxPage {
  return { conversations: ids.map(row), next_cursor, chat_slug: "ravi-k7m2qx", timezone: "Asia/Kolkata" };
}

const range = (from: number, to: number) => Array.from({ length: to - from }, (_, i) => `c${from + i}`);

test("appendPage drops rows already shown", () => {
  // A chat that moved while the User paged can come back on the next page: show it once.
  const result = appendPage(page(["a", "b"], "p2"), page(["b", "c"], null));
  expect(result.conversations.map((r) => r.conversation_id)).toEqual(["a", "b", "c"]);
  expect(result.next_cursor).toBeNull();
});

test("pollLimit asks for the rows on screen, at least one page, at most POLL_MAX", () => {
  expect(pollLimit(0)).toBe(20);
  expect(pollLimit(35)).toBe(35);
  expect(pollLimit(500)).toBe(POLL_MAX);
});

test("mergePoll replaces a short list with the poll answer", () => {
  const answer = page(["new", "a"], "p2");
  expect(mergePoll(page(["a", "b"], "p2"), answer)).toBe(answer);
});

test("mergePoll keeps rows past 100 and the old next_cursor", () => {
  // 120 on screen; the poll can only send the top 100. Keep the other 20, so the list
  // does not shrink every 5 s, and keep the cursor that loads what comes after them.
  const current = page(range(0, 120), "after-120");
  const answer = page(["new", ...range(0, 99)], "after-99");
  const result = mergePoll(current, answer);
  const ids = result.conversations.map((r) => r.conversation_id);
  expect(ids).toEqual(["new", ...range(0, 120)]);
  expect(result.next_cursor).toBe("after-120");
});
