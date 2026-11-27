// useSends (story 4.4): the Messages THIS screen sent, and their state: sending, sent, failed.
// Shared by the Chat Page (the Customer) and the Inbox (a team member). Moved from ChatPanel.
//
// Each send gets a client_message_id made here. A retry sends the SAME id, so the server
// saves the Message once even if the first try did arrive (idempotent send).
import { useState } from "react";
import type { components } from "@/api/schema";
import type { Sent } from "./chatPoll";

type MessageOut = components["schemas"]["MessageOut"];
type ErrorBody = components["schemas"]["ErrorBody"];

// One POST of one Message, as openapi-fetch answers it. The caller picks the route.
export type Post = (
  body: string,
  clientMessageId: string,
) => Promise<{ data?: MessageOut; error?: unknown; response: Response }>;

// A 4xx (except 429 "too fast") fails the same way every time: Retry would not help.
// 429, 5xx, and a lost network can work on a later try.
function retryable(status: number): boolean {
  return status === 429 || status >= 500;
}

// The most useful words in an error answer: a field's message ("A message can be at most
// 2000 characters.") before the general one ("Some fields need fixing.").
function reasonOf(error: unknown): string | undefined {
  const body = (error as { error?: ErrorBody } | undefined)?.error;
  return body?.fields?.[0]?.message ?? body?.message;
}

export function useSends(
  post: Post,
  { onSent }: { onSent?: (message: MessageOut) => void } = {},
): { sent: Sent[]; send: (body: string) => void; retry: (clientMessageId: string, body: string) => void } {
  const [sent, setSent] = useState<Sent[]>([]);

  function update(clientMessageId: string, change: Partial<Sent>) {
    setSent((current) => current.map((item) => (item.clientMessageId === clientMessageId ? { ...item, ...change } : item)));
  }

  async function deliver(clientMessageId: string, body: string) {
    update(clientMessageId, { status: "sending" });
    try {
      const { data, error, response } = await post(body, clientMessageId);
      if (data) {
        update(clientMessageId, { status: "sent", message: data });
        onSent?.(data);
      } else {
        update(clientMessageId, { status: "failed", reason: reasonOf(error), canRetry: retryable(response.status) });
      }
    } catch {
      update(clientMessageId, { status: "failed", reason: undefined, canRetry: true }); // network down
    }
  }

  function send(body: string) {
    const clientMessageId = crypto.randomUUID();
    setSent((current) => [...current, { clientMessageId, body, status: "sending" }]);
    void deliver(clientMessageId, body);
  }

  return { sent, send, retry: (clientMessageId, body) => void deliver(clientMessageId, body) };
}
