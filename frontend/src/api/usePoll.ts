// usePoll: the one shared poll loop (story 4.2, AD-7, AR-3). Every screen that must stay live
// uses this hook, not its own setInterval. No data-fetching library.
//
// The rules:
// - One poll every intervalMs (5 s) while the tab is visible. Never two at once: the next
//   poll starts max(0, intervalMs - elapsed) after the previous one ENDS.
// - Each poll gets its own AbortController. A poll still running after intervalMs is aborted
//   and counts as a failure (a hung request on a bad network must not stop the loop).
//   A plain setTimeout aborts it, not AbortSignal.timeout: tests' fake timers cannot move that one.
// - Hidden tab: no new polls. Visible again: one poll at once.
// - enabled turns false, or the screen unmounts: abort the running poll and ignore its answer.
// - FAILS_BEFORE_BANNER failures in a row -> reconnecting = true. One success -> false.
import { useEffect, useRef, useState } from "react";

export const FAILS_BEFORE_BANNER = 3;

type Poll = (signal: AbortSignal) => Promise<boolean>; // true = it worked

export function usePoll(
  poll: Poll,
  { enabled, intervalMs = 5000 }: { enabled: boolean; intervalMs?: number },
): { reconnecting: boolean } {
  const [reconnecting, setReconnecting] = useState(false);
  // The newest poll function (it holds the newest cursor). A ref, so a new function does not
  // restart the loop.
  const pollRef = useRef(poll);
  useEffect(() => {
    pollRef.current = poll;
  });

  useEffect(() => {
    if (!enabled) return;
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined; // the wait before the next poll
    let running: AbortController | null = null; // the poll in flight, if any
    let fails = 0;

    // One poll, as a promise that always ends by intervalMs: true or false, never a throw.
    function runOne(controller: AbortController): Promise<boolean> {
      return new Promise((resolve) => {
        const limit = setTimeout(() => {
          controller.abort();
          resolve(false);
        }, intervalMs);
        const done = (ok: boolean) => {
          clearTimeout(limit);
          resolve(ok);
        };
        pollRef.current(controller.signal).then(done, () => done(false));
      });
    }

    async function tick() {
      timer = undefined;
      if (document.visibilityState === "hidden") return; // "visible" starts it again
      const started = Date.now();
      running = new AbortController();
      const ok = await runOne(running);
      if (stopped) return; // disabled or unmounted meanwhile: drop the answer
      running = null;
      fails = ok ? 0 : fails + 1;
      setReconnecting(fails >= FAILS_BEFORE_BANNER);
      timer = setTimeout(
        tick,
        Math.max(0, intervalMs - (Date.now() - started)),
      );
    }

    function onVisibilityChange() {
      if (document.visibilityState !== "visible" || running !== null) return;
      clearTimeout(timer); // poll at once, not at the end of the old wait
      void tick();
    }

    timer = setTimeout(tick, intervalMs); // the first load already got the data: wait first
    document.addEventListener("visibilitychange", onVisibilityChange);
    return () => {
      stopped = true;
      clearTimeout(timer);
      running?.abort();
      document.removeEventListener("visibilitychange", onVisibilityChange);
    };
  }, [enabled, intervalMs]);

  return { reconnecting };
}
