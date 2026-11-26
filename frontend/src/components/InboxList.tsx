"use client";
// The Inbox list (story 4.3, FR-23): every Conversation, Needs Human first, then newest first.
// - First load: skeleton rows; a failure shows "Try again" (UX-DR25).
// - Empty: the share message and a Copy link button (UX-DR24).
// - Load more: the next page below (UX-DR25: pages, not infinite scroll, for slow networks).
// - Polling (FR-24): every 5 s it asks again for the top rows on screen and redraws them.
//   No poll while Load more runs: an older answer would wipe the page just added.
// The server sorts; this file never re-sorts.
import Link from "next/link";
import { useState } from "react";
import { api } from "@/api/client";
import { usePoll } from "@/api/usePoll";
import { CopyChatLinkButton } from "@/components/CopyChatLinkButton";
import { LoadFailed } from "@/components/LoadFailed";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { appendPage, mergePoll, pollLimit } from "@/lib/inboxList";
import { formatListTime } from "@/lib/time";
import { useLoad } from "@/lib/useLoad";

const PATH = "/api/v1/inbox/conversations";

export function InboxList() {
  const state = useLoad(() => api.GET(PATH), []);
  const [loadingMore, setLoadingMore] = useState(false);
  const [moreFailed, setMoreFailed] = useState(false);
  const ready = state.status === "ready";
  const shown = ready ? state.data.conversations.length : 0;

  // replace() here is fine: a timer callback, not a child's effect (see useLoad).
  const { reconnecting } = usePoll(
    async (signal) => {
      const { data } = await api.GET(PATH, { params: { query: { limit: pollLimit(shown) } }, signal });
      // Stopped meanwhile (Load more started, or the screen closed): this answer is older than
      // what is on screen, so drop it. Checked here, not left to fetch: the abort stops the
      // data only if every layer passes the signal on.
      if (signal.aborted) return false;
      if (data === undefined) return false; // 429 and 5xx count as failures
      state.replace((current) => mergePoll(current, data));
      return true;
    },
    { enabled: ready && !loadingMore },
  );

  async function loadMore(cursor: string) {
    setLoadingMore(true);
    setMoreFailed(false);
    try {
      const { data } = await api.GET(PATH, { params: { query: { cursor } } });
      if (data === undefined) setMoreFailed(true);
      else state.replace((current) => appendPage(current, data));
    } catch {
      setMoreFailed(true); // network down
    } finally {
      setLoadingMore(false);
    }
  }

  if (state.status === "failed" || state.status === "not_found") return <LoadFailed onRetry={state.reload} />;
  if (state.status === "loading") {
    return (
      <div aria-busy="true" aria-label="Loading" className="flex flex-col gap-2">
        {[0, 1, 2, 3, 4].map((n) => (
          <div key={n} className="h-16 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>
    );
  }

  const { conversations, next_cursor, chat_slug, timezone } = state.data;
  if (conversations.length === 0) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p className="text-muted-foreground">No conversations yet. Share your chat link to get your first customer.</p>
        <CopyChatLinkButton slug={chat_slug} label="Copy link" />
      </div>
    );
  }

  const now = new Date();
  return (
    <div className="flex min-w-0 flex-col gap-3">
      <p aria-live="polite" className="text-sm text-muted-foreground empty:hidden">
        {reconnecting ? "Reconnecting…" : ""}
      </p>
      <ul className="flex min-w-0 flex-col divide-y">
        {conversations.map((row) => (
          <li key={row.conversation_id} className="min-w-0">
            <Link
              href={`/app/inbox/${row.conversation_id}`}
              className="flex min-h-11 min-w-0 flex-col gap-1 rounded-lg px-2 py-3 hover:bg-muted"
            >
              <span className="flex items-center justify-between gap-2">
                <span className="truncate font-medium">New visitor</span>
                <time dateTime={row.last_message_at} className="shrink-0 text-xs text-muted-foreground">
                  {formatListTime(row.last_message_at, now, timezone)}
                </time>
              </span>
              <span className="flex min-w-0 items-center gap-2">
                <StatusBadge state={row.state} />
                <span className="truncate text-sm text-muted-foreground">{row.last_message_preview}</span>
              </span>
            </Link>
          </li>
        ))}
      </ul>
      {next_cursor !== null && (
        <div className="flex flex-col items-start gap-2">
          <Button variant="outline" disabled={loadingMore} onClick={() => loadMore(next_cursor)}>
            {loadingMore ? "Loading…" : "Load more"}
          </Button>
          {moreFailed && <p role="alert">Could not load more. Try again.</p>}
        </div>
      )}
    </div>
  );
}
