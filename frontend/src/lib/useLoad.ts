// useLoad: the one request lifecycle for every screen that loads data (UX-DR25).
// A screen says WHAT to fetch and HOW to show each state; this hook owns the rest:
// - states: loading → ready (with data) | failed | not_found (a 404)
// - a 401 stays "loading": the API client (api/client.ts) is already going to /login
// - reload(): from failed/not_found it shows loading again; from ready the old data stays
//   on screen until the new data arrives (no skeleton flash after a save)
// - replace(data): show data a save already answered with, so no extra request is needed.
//   Pass an updater, replace((current) => ...), to change the newest data, not a copy from
//   an older render.
// - reload and replace are for event handlers (clicks, saves, pageshow), not for a child's
//   effect: the newest fetch function is stored in an effect, after children's effects run.
// - the latest request wins: an older answer, or one that arrives after the screen
//   closed, is ignored, so a slow old list can never overwrite a newer one
// - when an input changes (e.g. the Chat Page slug), it loads again and shows loading
//
// No data-fetching library on purpose (AR-3): this is the small part of one we need.
import { useCallback, useEffect, useRef, useState } from "react";

type State<T> = { status: "loading" } | { status: "ready"; data: T } | { status: "failed" } | { status: "not_found" };
export type Loaded<T> = State<T> & { reload: () => void; replace: (next: T | ((current: T) => T)) => void };

// The shape openapi-fetch returns: data on success, and always the raw response.
type Answer<T> = { data?: T; response: Response };

export function useLoad<T>(fetch: () => Promise<Answer<T>>, inputs: readonly unknown[]): Loaded<T> {
  // The inputs as one text key, so a change in any of them is easy to see.
  const key = JSON.stringify(inputs);
  // Each stored state remembers which inputs it belongs to: state for old inputs is never shown.
  const [stored, setStored] = useState<{ key: string; state: State<T> }>({ key, state: { status: "loading" } });
  // The number of the newest request. An answer from any other request is dropped.
  const latest = useRef(0);
  // Always call the newest fetch function, without loading again on every render.
  const fetchRef = useRef(fetch);
  useEffect(() => {
    fetchRef.current = fetch;
  });

  const start = useCallback((forKey: string) => {
    const id = ++latest.current;
    const settle = (state: State<T>) => {
      if (id === latest.current) setStored({ key: forKey, state });
    };
    fetchRef
      .current()
      .then(({ data, response }) => {
        // Every GET here answers with a JSON body. A reply with no body (e.g. 204) would count as failed.
        if (data !== undefined) settle({ status: "ready", data });
        else if (response.status === 404) settle({ status: "not_found" });
        // 401: keep what is on screen; the browser is on its way to /login.
        else if (response.status !== 401) settle({ status: "failed" });
      })
      .catch(() => settle({ status: "failed" })); // network down
  }, []);

  useEffect(() => {
    start(key);
    // The screen closed, or the inputs changed: drop the answer of this request.
    return () => {
      latest.current += 1;
    };
  }, [start, key]);

  const reload = useCallback(() => {
    setStored((current) =>
      current.state.status === "ready" ? current : { key: current.key, state: { status: "loading" } },
    );
    start(key);
  }, [start, key]);

  const replace = useCallback(
    (next: T | ((current: T) => T)) => {
      latest.current += 1; // a load still running must not overwrite this newer data
      setStored((current) => {
        if (typeof next !== "function") return { key, state: { status: "ready", data: next } };
        // An updater needs data to update: with nothing loaded, keep the state as it is.
        if (current.key !== key || current.state.status !== "ready") return current;
        return { key, state: { status: "ready", data: (next as (current: T) => T)(current.state.data) } };
      });
    },
    [key],
  );

  const state: State<T> = stored.key === key ? stored.state : { status: "loading" };
  return { ...state, reload, replace };
}
