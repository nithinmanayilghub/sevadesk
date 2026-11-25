// chatPoll: how one poll answer joins what the Chat Page already shows (story 4.2, AD-7).
// - mergePoll: add a poll's new Messages to the ones on screen, and keep the newest cursor.
// - chatItems: the ONE list the page draws, sorted by seq. The server's Messages and this
//   page's own sends sit in one list, so a reply polled after a send shows below it.
import type { components } from "@/api/schema";

type MessageOut = components["schemas"]["MessageOut"];
type ChatPollOut = components["schemas"]["ChatPollOut"];

// One Message this page sent. "sent" holds the Message the server saved.
// "failed" holds the server's reason (if it gave one), and whether a retry can work.
export type Sent = {
  clientMessageId: string;
  body: string;
  status: "sending" | "sent" | "failed";
  message?: MessageOut;
  reason?: string;
  canRetry?: boolean;
};

export type ChatItem = { kind: "saved"; message: MessageOut } | { kind: "sent"; item: Sent };

export function mergePoll(current: ChatPollOut, next: ChatPollOut): ChatPollOut {
  if (!next.changed) return current; // nothing new: keep the same object, so nothing redraws
  const last = current.messages.at(-1)?.seq ?? 0;
  return {
    changed: true,
    // Only seqs after the last one we have: a poll that repeats one never draws it twice.
    messages: [...current.messages, ...next.messages.filter((m) => m.seq > last)],
    snapshot: next.snapshot ?? current.snapshot,
    cursor: next.cursor,
  };
}

export function chatItems(saved: MessageOut[], sent: Sent[]): ChatItem[] {
  // A Message this page sent shows as its own send (it may carry "Not sent · Retry"), never twice.
  const sentIds = new Set(sent.map((item) => item.clientMessageId));
  const done: { seq: number; entry: ChatItem }[] = [];
  for (const m of saved) {
    if (!sentIds.has(m.client_message_id ?? "")) done.push({ seq: m.seq, entry: { kind: "saved", message: m } });
  }
  for (const item of sent) {
    if (item.status === "sent" && item.message) done.push({ seq: item.message.seq, entry: { kind: "sent", item } });
  }
  done.sort((a, b) => a.seq - b.seq);
  // Not saved yet (no seq): at the end, in the order they were sent.
  const waiting: ChatItem[] = sent.filter((item) => item.status !== "sent").map((item) => ({ kind: "sent", item }));
  return [...done.map((d) => d.entry), ...waiting];
}
