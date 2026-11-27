// useLiveThread: one live chat thread, for both chat screens (AD-7). The Chat Page (the
// Customer, ChatPanel) and the Inbox thread (the team, ConversationView) give it two fetchers
// and draw what it returns. Everything else lives here, once:
// - load the thread, then poll every 5 s with the newest cursor (usePoll)
// - merge each poll answer into what is on screen (mergePoll), and this screen's own sends (useSends)
// - ONE sorted list to draw (chatItems)
// - the stale-poll guard: a poll asked BEFORE a local state change (a click) can answer
//   after it with the old state. Such an answer keeps its Messages but not its state, and
//   keeps the old cursor, so the next poll reads again (story 4.4).
// - "gone": a poll that gets a 404 (the chat was deleted, story 4.5) ends the thread. The
//   status becomes "not_found" and the polling stops. A 404 is not a network problem, so
//   it must never show "Reconnecting…".
//
// No data-fetching library on purpose (AR-3): useLoad, usePoll and useSends are small parts.
import { useRef, useState } from "react";
import type { components } from "@/api/schema";
import { usePoll } from "@/api/usePoll";
import { type ChatItem, chatItems, mergePoll, type Sent } from "./chatPoll";
import { useLoad } from "./useLoad";
import { type Post, useSends } from "./useSends";

type ChatPollOut = components["schemas"]["ChatPollOut"];
type MessageOut = components["schemas"]["MessageOut"];

// One GET of the thread. No cursor = the first load (everything); a cursor = only what changed.
export type FetchThread = (
  cursor: string | undefined,
  signal?: AbortSignal,
) => Promise<{ data?: ChatPollOut; response: Response }>;

export type LiveThread = {
  status: "loading" | "ready" | "failed" | "not_found";
  data: ChatPollOut | null; // the newest answer (Messages, snapshot, cursor) once ready
  items: ChatItem[]; // what to draw, sorted by seq
  sent: Sent[];
  send: (body: string) => void;
  retry: (clientMessageId: string, body: string) => void;
  reconnecting: boolean; // 3 failed polls in a row
  reload: () => void;
  // Show a state the server already answered with (a click, a reply). Arms the stale-poll guard.
  setConversationState: (state: string) => void;
};

export function useLiveThread({
  fetch,
  post,
  inputs,
  onSent,
}: {
  fetch: FetchThread;
  post: Post;
  inputs: readonly unknown[]; // when these change (another chat), the thread loads again
  onSent?: (message: MessageOut) => void;
}): LiveThread {
  const key = JSON.stringify(inputs);
  const state = useLoad(() => fetch(undefined), inputs);
  // Which inputs' thread was found gone. Keyed, so another chat does not start out "gone".
  const [goneKey, setGoneKey] = useState<string | null>(null);
  const gone = goneKey === key;
  // Goes up on every local state change: see the stale-poll guard above.
  const localChanges = useRef(0);
  const { sent, send, retry } = useSends(post, { onSent });

  const ready = state.status === "ready" && !gone;
  const cursor = state.status === "ready" ? state.data.cursor : null;

  const { reconnecting } = usePoll(
    async (signal) => {
      const askedAt = localChanges.current;
      const { data, response } = await fetch(cursor ?? undefined, signal);
      if (response.status === 404) {
        setGoneKey(key); // deleted meanwhile: stop, and say so
        return true; // not a failure: no "Reconnecting…"
      }
      if (data === undefined) return false; // 429 and 5xx count as failures
      if (data.changed) {
        state.replace((current) => {
          const merged = mergePoll(current, data);
          if (localChanges.current === askedAt) return merged;
          // A click happened while this poll was out: keep our state AND our old cursor.
          return { ...merged, snapshot: current.snapshot, cursor: current.cursor };
        });
      }
      return true;
    },
    // Before the chat exists there is nothing to poll for (the first send makes it).
    { enabled: ready && (cursor !== null || sent.some((item) => item.status === "sent")) },
  );

  function setConversationState(next: string) {
    localChanges.current += 1;
    state.replace((current) => ({ ...current, snapshot: { ...current.snapshot, conversation_state: next } }));
  }

  return {
    status: gone ? "not_found" : state.status,
    data: ready ? state.data : null,
    items: chatItems(ready ? state.data.messages : [], sent),
    sent,
    send,
    retry,
    reconnecting: gone ? false : reconnecting,
    reload: state.reload,
    setConversationState,
  };
}
