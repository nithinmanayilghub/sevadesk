"use client";
// ConversationView (story 4.4, FR-21, FR-24): one open Conversation in the Inbox.
// - the full history, with the same bubble sides as the Chat Page (UX-DR7); team replies say "Team"
// - the Handoff bar (UX-DR12): who replies now, and ONE button that flips it
//   (Take over <-> Give back to Agent), so keyboard focus stays on it after a click
// - the composer (UX-DR13): a reply starts a Handoff; the first time, a hint says so
// - stays live (AD-7): polls every 5 s with the cursor, like the Chat Page
//
// The state shown comes from the poll snapshot. A click (or a reply) sets it at once from the
// server's answer. A poll that was ASKED before that click can come back after it with the
// old state; such an answer keeps its Messages but not its state (the next poll brings the truth).
import Link from "next/link";
import { useRef, useState } from "react";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { usePoll } from "@/api/usePoll";
import { chatItems, mergePoll } from "@/lib/chatPoll";
import { useLoad } from "@/lib/useLoad";
import { useSends } from "@/lib/useSends";
import { authorLabel, Bubble, SentBubble } from "./ChatBubble";
import { Composer } from "./Composer";
import { LoadFailed } from "./LoadFailed";
import { PILL_BUTTON } from "./pillButton";

type ChatPollOut = components["schemas"]["ChatPollOut"];

// Team replies in the Inbox are labeled "Team": Users have no names yet (a later story).
const TEAM = "Team";
// Set after the User's first reply in this browser: the hint is not shown again (UX-DR13).
export const HINT_KEY = "sevadesk:reply-hint-seen";

// localStorage can throw (a private window, blocked site data): then the hint just shows again.
function hintSeen(): boolean {
  try {
    return localStorage.getItem(HINT_KEY) === "1";
  } catch {
    return false;
  }
}

function rememberHintSeen(): void {
  try {
    localStorage.setItem(HINT_KEY, "1");
  } catch {
    // nothing to do: see hintSeen
  }
}

function withState(data: ChatPollOut, state: string): ChatPollOut {
  return { ...data, snapshot: { ...data.snapshot, conversation_state: state } };
}

export function ConversationNotFound() {
  return (
    <div className="flex flex-col items-start gap-3">
      <p>This conversation was not found.</p>
      <Link href="/app/inbox" className="inline-flex min-h-11 items-center font-medium underline">
        Back to Inbox
      </Link>
    </div>
  );
}

export function ConversationView({ conversationId }: { conversationId: string }) {
  const path = { conversation_id: conversationId };
  const state = useLoad(() => api.GET("/api/v1/inbox/conversations/{conversation_id}/messages", { params: { path } }), [
    conversationId,
  ]);
  // Goes up on every local state change (a click or a reply): see the header comment.
  const localChanges = useRef(0);
  const [showHint, setShowHint] = useState(() => !hintSeen()); // the composer only shows after load
  const [busy, setBusy] = useState(false);
  const [barFailed, setBarFailed] = useState(false);

  function setLocalState(next: string) {
    localChanges.current += 1;
    state.replace((current) => withState(current, next));
  }

  const { sent, send, retry } = useSends(
    (body, clientMessageId) =>
      api.POST("/api/v1/inbox/conversations/{conversation_id}/messages", {
        params: { path },
        body: { body, client_message_id: clientMessageId },
      }),
    {
      onSent: () => {
        setLocalState("handoff"); // the server started the Handoff with this reply
        rememberHintSeen();
        setShowHint(false);
      },
    },
  );

  const ready = state.status === "ready";
  const cursor = ready ? state.data.cursor : null;

  const { reconnecting } = usePoll(
    async (signal) => {
      const askedAt = localChanges.current;
      const { data } = await api.GET("/api/v1/inbox/conversations/{conversation_id}/messages", {
        params: { path, query: { cursor: cursor ?? undefined } },
        signal,
      });
      if (data === undefined) return false; // 429 and 5xx count as failures
      if (data.changed) {
        state.replace((current) => {
          const merged = mergePoll(current, data);
          // A click happened while this poll was out: its state may be older than the click's.
          return localChanges.current === askedAt ? merged : { ...merged, snapshot: current.snapshot };
        });
      }
      return true;
    },
    { enabled: ready },
  );

  async function flip(to: "take-over" | "give-back") {
    if (busy) return;
    setBusy(true);
    setBarFailed(false);
    try {
      const { data } =
        to === "take-over"
          ? await api.POST("/api/v1/inbox/conversations/{conversation_id}/take-over", { params: { path } })
          : await api.POST("/api/v1/inbox/conversations/{conversation_id}/give-back", { params: { path } });
      if (data) setLocalState(data.state);
      else setBarFailed(true);
    } catch {
      setBarFailed(true); // network down
    } finally {
      setBusy(false);
    }
  }

  if (state.status === "not_found") return <ConversationNotFound />;
  if (state.status === "failed") return <LoadFailed onRetry={state.reload} />;

  const conversationState = ready ? state.data.snapshot?.conversation_state : undefined;
  const items = chatItems(ready ? state.data.messages : [], sent);

  return (
    <section aria-labelledby="conversation-heading" className="flex flex-col gap-4">
      <h2 id="conversation-heading" className="text-lg font-semibold">
        Conversation
      </h2>

      {/* The Handoff bar (UX-DR12). No bar for a closed chat. The status region is always in
          the page, so a screen reader hears each change. */}
      <div className="flex flex-wrap items-center justify-between gap-2 rounded-xl border bg-card px-4 py-2">
        <p role="status" aria-label="Who replies" className="text-sm">
          {conversationState === "agent" && "Agent is replying"}
          {conversationState === "handoff" && "You are replying. The Agent is paused."}
        </p>
        {(conversationState === "agent" || conversationState === "handoff") && (
          // aria-disabled, not disabled: a disabled button loses keyboard focus.
          <button
            type="button"
            className={`${PILL_BUTTON} min-h-11`}
            aria-disabled={busy}
            onClick={() => void flip(conversationState === "agent" ? "take-over" : "give-back")}
          >
            {conversationState === "agent" ? "Take over" : "Give back to Agent"}
          </button>
        )}
      </div>
      {barFailed && <p role="alert">Could not change who replies. Try again.</p>}

      <p role="status" className="text-sm text-muted-foreground">
        {reconnecting ? "Reconnecting…" : ""}
      </p>
      <ol role="log" aria-live="polite" className="flex flex-col gap-2">
        {items.map((entry) =>
          entry.kind === "saved" ? (
            <Bubble
              key={`seq-${entry.message.seq}`}
              authorType={entry.message.author_type}
              lang={entry.message.lang}
              body={entry.message.body}
              label={authorLabel(entry.message.author_type, TEAM)}
            />
          ) : (
            <SentBubble key={entry.item.clientMessageId} item={entry.item} authorType="user" label={TEAM} onRetry={retry} />
          ),
        )}
      </ol>

      {state.status === "loading" && (
        <div aria-busy="true" aria-label="Loading conversation" className="h-24 animate-pulse rounded-xl bg-muted" />
      )}

      {ready && (
        <Composer
          id="inbox-reply"
          label="Reply"
          placeholder="Type a reply…"
          onSend={send}
          hint={showHint && conversationState === "agent" ? "Your reply pauses the Agent." : undefined}
        />
      )}
    </section>
  );
}
