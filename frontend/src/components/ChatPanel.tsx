"use client";
// ChatPanel (story 4.1, FR-15): the Customer's own chat on the Chat Page.
// - loads this browser's Messages (the visitor cookie picks the chat; we never send an id)
// - bubbles: the Customer on the right, the Business on the left (UX-DR7); a team reply shows
//   the Business name above it, the Agent "SevaDesk assistant" (story 4.4)
// - a live region, so screen readers announce new Messages (UX-DR32)
// - the DPDP notice above the composer until the first Message (NFR-8)
// - a failed send shows "Not sent · Retry" and keeps the text while the page is open (UX-DR13)
//
// - stays live (story 4.2, AD-7): polls every 5 s with the cursor, and adds new Messages.
//   It polls only once the chat exists (a cursor, or one saved send). "Reconnecting…" after
//   3 failed polls in a row.
//
// The bubbles, the composer, and the live thread are shared with the Inbox:
// ChatBubble.tsx, Composer.tsx, lib/useLiveThread.ts.
//
// Keep this light (NFR-6, 200 KB first load): plain elements, no ui/button, no icon sets.
import { useEffect } from "react";
import { api } from "@/api/client";
import { useLiveThread } from "@/lib/useLiveThread";
import { authorLabel, Bubble, SentBubble } from "./ChatBubble";
import { Composer } from "./Composer";
import { PILL_BUTTON } from "./pillButton";

export function ChatPanel({
  slug,
  businessName,
  takingRequests,
  onHasMessages,
}: {
  slug: string;
  businessName: string;
  takingRequests: boolean;
  onHasMessages: (has: boolean) => void;
}) {
  // Load, poll every 5 s, merge, and sends: all in useLiveThread (shared with the Inbox). It
  // polls only once the chat exists (a cursor, or one saved send). A slug that is gone (404)
  // shows nothing here: the page already says "Chat page not found".
  const thread = useLiveThread({
    fetch: (cursor, signal) =>
      signal
        ? api.GET("/api/v1/chat/{chat_slug}/messages", {
            params: { path: { chat_slug: slug }, query: { cursor } },
            signal,
          })
        : api.GET("/api/v1/chat/{chat_slug}/messages", { params: { path: { chat_slug: slug } } }),
    post: (body, clientMessageId) =>
      api.POST("/api/v1/chat/{chat_slug}/messages", {
        params: { path: { chat_slug: slug } },
        body: { body, client_message_id: clientMessageId },
      }),
    inputs: [slug],
  });

  // One list, sorted by seq: a reply polled after the Customer's send shows below it.
  const { items } = thread;
  const hasMessages = items.length > 0;

  // Tell the page (it folds the Services list on mobile). In an effect: never during render.
  useEffect(() => onHasMessages(hasMessages), [hasMessages, onHasMessages]);

  if (thread.status === "not_found") return null; // the page already says "Chat page not found"

  return (
    <section aria-label="Chat" className="flex flex-col gap-3">
      {/* Always in the page, empty while all is well: a live region added together with its
          text is often not announced. */}
      <p role="status" className="text-sm text-muted-foreground">
        {thread.reconnecting ? "Reconnecting…" : ""}
      </p>
      {/* Always in the page, even empty (the same reason). role="log" = new lines are added at the end. */}
      <ol role="log" aria-live="polite" className="flex flex-col gap-2">
        {items.map((entry) =>
          entry.kind === "saved" ? (
            <Bubble
              key={`seq-${entry.message.seq}`}
              authorType={entry.message.author_type}
              lang={entry.message.lang}
              body={entry.message.body}
              label={authorLabel(entry.message.author_type, businessName)}
            />
          ) : (
            <SentBubble key={entry.item.clientMessageId} item={entry.item} authorType="customer" onRetry={thread.retry} />
          ),
        )}
      </ol>

      {thread.status === "loading" && (
        <div aria-busy="true" aria-label="Loading chat" className="h-24 animate-pulse rounded-xl bg-muted" />
      )}

      {thread.status === "failed" && (
        <div className="flex flex-col items-start gap-3">
          <p role="alert">Could not load the chat.</p>
          <button type="button" className={PILL_BUTTON} onClick={thread.reload}>
            Try again
          </button>
        </div>
      )}

      {/* The composer only once the chat has loaded: that GET set the visitor cookie, so the
          first send cannot make a second cookie. */}
      {thread.status === "ready" && takingRequests && (
        <>
          {/* The DPDP notice (India's data protection law), before the first Message (NFR-8). */}
          {!hasMessages && (
            <p className="text-sm text-muted-foreground">
              We collect your name, phone, and address only to book your job. {businessName} can delete them on
              request.
            </p>
          )}
          <Composer id="chat-message" label="Message" placeholder="Type a message…" onSend={thread.send} />
        </>
      )}
    </section>
  );
}
