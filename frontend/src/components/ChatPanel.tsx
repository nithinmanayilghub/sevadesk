"use client";
// ChatPanel (story 4.1, FR-15): the Customer's own chat on the Chat Page.
// - loads this browser's Messages (the visitor cookie picks the chat; we never send an id)
// - bubbles: the Customer on the right, the Business on the left (UX-DR7)
// - a live region, so screen readers announce new Messages (UX-DR32)
// - the DPDP notice above the composer until the first Message (NFR-8)
// - a failed send shows "Not sent · Retry" and keeps the text while the page is open (UX-DR13)
//
// Each send gets a client_message_id made here. A retry sends the SAME id, so the server
// saves the Message once even if the first try did arrive (idempotent send).
//
// Keep this light (NFR-6, 200 KB first load): plain elements, no ui/button, no icon sets.
import { useEffect, useRef, useState } from "react";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { useLoad } from "@/lib/useLoad";
import { PILL_BUTTON } from "./pillButton";

type MessageOut = components["schemas"]["MessageOut"];

type ErrorBody = components["schemas"]["ErrorBody"];

// One Message this page sent. "sent" holds the Message the server saved.
// "failed" holds the server's reason (if it gave one), and whether a retry can work.
type Sent = {
  clientMessageId: string;
  body: string;
  status: "sending" | "sent" | "failed";
  message?: MessageOut;
  reason?: string;
  canRetry?: boolean;
};

// Same as the server's MAX_BODY (inbox/schemas.py): the box stops at the limit.
const MAX_BODY = 2000;

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

// Enter sends only with a mouse or trackpad. On a phone, Enter in the keyboard is a new line
// and the Send button sends (UX-DR13). Old browsers and tests may have no matchMedia.
function hasFinePointer(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(pointer: fine)").matches;
}

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
  const state = useLoad(
    () => api.GET("/api/v1/chat/{chat_slug}/messages", { params: { path: { chat_slug: slug } } }),
    [slug],
  );
  const [sent, setSent] = useState<Sent[]>([]);
  const [text, setText] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);

  // Saved Messages first (server order), then this page's sends in the order they were made.
  const sentIds = new Set(sent.map((item) => item.clientMessageId));
  const saved = state.status === "ready" ? state.data.messages.filter((m) => !sentIds.has(m.client_message_id ?? "")) : [];
  const hasMessages = saved.length + sent.length > 0;

  // Tell the page (it folds the Services list on mobile). In an effect: never during render.
  useEffect(() => onHasMessages(hasMessages), [hasMessages, onHasMessages]);

  function update(clientMessageId: string, change: Partial<Sent>) {
    setSent((current) => current.map((item) => (item.clientMessageId === clientMessageId ? { ...item, ...change } : item)));
  }

  async function deliver(clientMessageId: string, body: string) {
    update(clientMessageId, { status: "sending" });
    try {
      const { data, error, response } = await api.POST("/api/v1/chat/{chat_slug}/messages", {
        params: { path: { chat_slug: slug } },
        body: { body, client_message_id: clientMessageId },
      });
      update(
        clientMessageId,
        data
          ? { status: "sent", message: data }
          : { status: "failed", reason: reasonOf(error), canRetry: retryable(response.status) },
      );
    } catch {
      update(clientMessageId, { status: "failed", reason: undefined, canRetry: true }); // network down
    }
  }

  function send() {
    const body = text.trim();
    if (!body) return;
    const clientMessageId = crypto.randomUUID();
    setSent((current) => [...current, { clientMessageId, body, status: "sending" }]);
    setText("");
    box.current?.focus(); // keep typing without tapping the box again
    void deliver(clientMessageId, body);
  }

  if (state.status === "not_found") return null; // the page already says "Chat page not found"

  return (
    <section aria-label="Chat" className="flex flex-col gap-3">
      {/* Always in the page, even empty: a live region added together with its first
          Message is often not announced. role="log" = new lines are added at the end. */}
      <ol role="log" aria-live="polite" className="flex flex-col gap-2">
        {saved.map((m) => (
          <Bubble key={m.seq} authorType={m.author_type} lang={m.lang} body={m.body} />
        ))}
        {sent.map((item) => (
          <Bubble
            key={item.clientMessageId}
            authorType="customer"
            lang={item.message?.lang}
            body={item.body}
            sending={item.status === "sending"}
          >
            {item.status === "failed" && (
              <span className="flex flex-col items-end text-sm text-muted-foreground">
                <span className="flex items-center gap-1">
                  <span>Not sent</span>
                  {item.canRetry && (
                    <>
                      <span aria-hidden="true">·</span>
                      {/* min-h-11 min-w-11: a 44 × 44 px target for a finger (UX-DR31). */}
                      <button
                        type="button"
                        className="min-h-11 min-w-11 px-1 font-medium text-foreground underline focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                        onClick={() => void deliver(item.clientMessageId, item.body)}
                      >
                        Retry
                      </button>
                    </>
                  )}
                </span>
                {item.reason && <span>{item.reason}</span>}
              </span>
            )}
          </Bubble>
        ))}
      </ol>

      {state.status === "loading" && (
        <div aria-busy="true" aria-label="Loading chat" className="h-24 animate-pulse rounded-xl bg-muted" />
      )}

      {state.status === "failed" && (
        <div className="flex flex-col items-start gap-3">
          <p role="alert">Could not load the chat.</p>
          <button type="button" className={PILL_BUTTON} onClick={state.reload}>
            Try again
          </button>
        </div>
      )}

      {/* The composer only once the chat has loaded: that GET set the visitor cookie, so the
          first send cannot make a second cookie. */}
      {state.status === "ready" && takingRequests && (
        <>
          {/* The DPDP notice (India's data protection law), before the first Message (NFR-8). */}
          {!hasMessages && (
            <p className="text-sm text-muted-foreground">
              We collect your name, phone, and address only to book your job. {businessName} can delete them on
              request.
            </p>
          )}
          <form
            className="flex items-end gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              send();
            }}
          >
            <label htmlFor="chat-message" className="sr-only">
              Message
            </label>
            <textarea
              id="chat-message"
              ref={box}
              rows={2}
              maxLength={MAX_BODY}
              value={text}
              placeholder="Type a message…"
              className="min-h-11 flex-1 resize-none rounded-xl border bg-background px-3 py-2 text-base focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
              onChange={(event) => setText(event.target.value)}
              onKeyDown={(event) => {
                if (event.key === "Enter" && !event.shiftKey && hasFinePointer()) {
                  event.preventDefault();
                  send();
                }
              }}
            />
            <button type="submit" className={PILL_BUTTON} disabled={!text.trim()}>
              Send
            </button>
          </form>
        </>
      )}
    </section>
  );
}

function Bubble({
  authorType,
  lang,
  body,
  sending = false,
  children,
}: {
  authorType: string;
  lang?: string;
  body: string;
  sending?: boolean;
  children?: React.ReactNode;
}) {
  const mine = authorType === "customer";
  return (
    // lang="hi" on Hindi, so screen readers and fonts treat it as Hindi (UX-DR32).
    <li lang={lang === "hi" ? "hi" : undefined} className={`flex max-w-[85%] flex-col gap-1 ${mine ? "ml-auto" : "mr-auto"}`}>
      <p
        className={`rounded-xl px-4 py-2 break-words whitespace-pre-wrap ${
          mine ? "bg-primary text-primary-foreground" : "border bg-card"
        } ${sending ? "opacity-70" : ""}`}
      >
        {body}
      </p>
      {children}
    </li>
  );
}
