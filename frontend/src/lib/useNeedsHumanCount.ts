// useNeedsHumanCount: the red number on the Inbox tab (story 4.3, UX-DR16). The /app layout
// uses it, so the number shows on every app page, not only on the Inbox.
// - enabled = false (a User who may not use the Inbox): no request at all, the number is 0.
// - enabled: one request at once, then the shared poll every 5 s (usePoll; it stops while
//   the tab is hidden). A failed poll keeps the last good number on screen.
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { usePoll } from "@/api/usePoll";

const PATH = "/api/v1/inbox/needs-human-count";

export function useNeedsHumanCount(enabled: boolean): number {
  const [count, setCount] = useState(0);

  // The first number at once: usePoll waits 5 s before its first poll.
  useEffect(() => {
    if (!enabled) return;
    let current = true; // false once disabled or unmounted: drop a late answer
    api.GET(PATH).then(
      ({ data }) => {
        if (current && data !== undefined) setCount(data.count);
      },
      () => {}, // network down: keep 0; the poll tries again in 5 s
    );
    return () => {
      current = false;
    };
  }, [enabled]);

  usePoll(
    async (signal) => {
      const { data } = await api.GET(PATH, { signal });
      if (signal.aborted || data === undefined) return false; // stopped meanwhile, or 429/5xx
      setCount(data.count);
      return true;
    },
    { enabled },
  );

  return enabled ? count : 0;
}
