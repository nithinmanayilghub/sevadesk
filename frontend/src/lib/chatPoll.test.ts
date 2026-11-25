// Tests for chatPoll: how one poll answer joins what the Chat Page already shows (story 4.2).
import { expect, test } from "vitest";
import type { components } from "@/api/schema";
import { chatItems, mergePoll, type Sent } from "./chatPoll";

type MessageOut = components["schemas"]["MessageOut"];
type ChatPollOut = components["schemas"]["ChatPollOut"];

function message(seq: number, extra: Partial<MessageOut> = {}): MessageOut {
  return {
    seq,
    author_type: "agent",
    body: `m${seq}`,
    lang: "en",
    client_message_id: null,
    actions: [],
    created_at: "2026-11-25T10:00:00Z",
    ...extra,
  };
}

const current: ChatPollOut = {
  changed: true,
  messages: [message(1), message(2)],
  snapshot: { conversation_state: "agent" },
  cursor: "c2",
};

test("no change keeps the current answer, the same object", () => {
  expect(mergePoll(current, { changed: false, messages: [], snapshot: null, cursor: "c2" })).toBe(current);
});

test("new Messages are added at the end", () => {
  const next = mergePoll(current, { changed: true, messages: [message(3)], snapshot: null, cursor: "c3" });
  expect(next.messages.map((m) => m.seq)).toEqual([1, 2, 3]);
});

test("a repeated seq is not added twice", () => {
  const next = mergePoll(current, { changed: true, messages: [message(2), message(3)], snapshot: null, cursor: "c3" });
  expect(next.messages.map((m) => m.seq)).toEqual([1, 2, 3]);
});

test("the cursor and the snapshot take the new values", () => {
  const next = mergePoll(current, {
    changed: true,
    messages: [],
    snapshot: { conversation_state: "handoff" },
    cursor: "c9",
  });
  expect(next.cursor).toBe("c9");
  expect(next.snapshot).toEqual({ conversation_state: "handoff" });
});

test("no new snapshot keeps the old one", () => {
  const next = mergePoll(current, { changed: true, messages: [], snapshot: null, cursor: "c3" });
  expect(next.snapshot).toEqual({ conversation_state: "agent" });
});

function sent(id: string, status: Sent["status"], seq?: number): Sent {
  const saved = seq === undefined ? undefined : message(seq, { author_type: "customer", client_message_id: id });
  return { clientMessageId: id, body: id, status, message: saved };
}

test("chatItems sorts by seq and puts sending and failed items last, in send order", () => {
  const items = chatItems(
    [message(1, { author_type: "customer", client_message_id: "a" }), message(2), message(4)],
    [sent("a", "sent", 1), sent("b", "failed"), sent("c", "sent", 3), sent("d", "sending")],
  );
  const names = items.map((i) => (i.kind === "saved" ? `saved ${i.message.seq}` : `sent ${i.item.clientMessageId}`));
  expect(names).toEqual([
    "sent a", // seq 1: this page's own send, shown once
    "saved 2",
    "sent c", // seq 3
    "saved 4",
    "sent b",
    "sent d",
  ]);
});
