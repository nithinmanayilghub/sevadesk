// Tests for useLoad: the one request lifecycle for screens that load data (loading, ready,
// failed, not found), with reload, the 401 rule, and "the latest request wins".
import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { useLoad } from "./useLoad";

type Result = { data?: string; response: Response };

function ok(data: string): Result {
  return { data, response: new Response(null, { status: 200 }) };
}
function status(code: number): Result {
  return { data: undefined, response: new Response(null, { status: code }) };
}

// A request we answer by hand, so a test decides when (and in which order) answers arrive.
function deferred() {
  let resolve!: (value: Result) => void;
  const promise = new Promise<Result>((r) => (resolve = r));
  return { promise, resolve };
}

test("starts loading, then is ready with the data", async () => {
  const { result } = renderHook(() => useLoad(() => Promise.resolve(ok("hello")), []));
  expect(result.current.status).toBe("loading");
  await waitFor(() => expect(result.current).toMatchObject({ status: "ready", data: "hello" }));
});

test("an error answer is failed", async () => {
  const { result } = renderHook(() => useLoad(() => Promise.resolve(status(500)), []));
  await waitFor(() => expect(result.current.status).toBe("failed"));
});

test("a network error is failed", async () => {
  const { result } = renderHook(() => useLoad(() => Promise.reject(new Error("offline")), []));
  await waitFor(() => expect(result.current.status).toBe("failed"));
});

test("a 404 is not_found", async () => {
  const { result } = renderHook(() => useLoad(() => Promise.resolve(status(404)), []));
  await waitFor(() => expect(result.current.status).toBe("not_found"));
});

test("a 401 stays loading: the API client is already going to /login", async () => {
  const fetch = vi.fn(() => Promise.resolve(status(401)));
  const { result } = renderHook(() => useLoad(fetch, []));
  await waitFor(() => expect(fetch).toHaveBeenCalled());
  await act(async () => {}); // let the answer arrive
  expect(result.current.status).toBe("loading");
});

test("reload after a failure shows loading, then the data", async () => {
  const answers = [deferred(), deferred()];
  let call = 0;
  const { result } = renderHook(() => useLoad(() => answers[call++].promise, []));
  await act(async () => answers[0].resolve(status(500)));
  expect(result.current.status).toBe("failed");

  act(() => result.current.reload());
  expect(result.current.status).toBe("loading");
  await act(async () => answers[1].resolve(ok("second")));
  expect(result.current).toMatchObject({ status: "ready", data: "second" });
});

test("reload when ready keeps the old data until the new data arrives", async () => {
  const answers = [deferred(), deferred()];
  let call = 0;
  const { result } = renderHook(() => useLoad(() => answers[call++].promise, []));
  await act(async () => answers[0].resolve(ok("old")));

  act(() => result.current.reload());
  expect(result.current).toMatchObject({ status: "ready", data: "old" });
  await act(async () => answers[1].resolve(ok("new")));
  expect(result.current).toMatchObject({ status: "ready", data: "new" });
});

test("the latest request wins, even when an older answer arrives last", async () => {
  const answers = [deferred(), deferred(), deferred()];
  let call = 0;
  const { result } = renderHook(() => useLoad(() => answers[call++].promise, []));
  await act(async () => answers[0].resolve(ok("first")));

  act(() => result.current.reload()); // request 2
  act(() => result.current.reload()); // request 3
  await act(async () => answers[2].resolve(ok("newest")));
  await act(async () => answers[1].resolve(ok("stale")));
  expect(result.current).toMatchObject({ status: "ready", data: "newest" });
});

test("a new input loads again and shows loading, not the old data", async () => {
  const answers: Record<string, ReturnType<typeof deferred>> = { a: deferred(), b: deferred() };
  const { result, rerender } = renderHook(({ slug }) => useLoad(() => answers[slug].promise, [slug]), {
    initialProps: { slug: "a" },
  });
  await act(async () => answers.a.resolve(ok("shop a")));
  expect(result.current).toMatchObject({ status: "ready", data: "shop a" });

  rerender({ slug: "b" });
  expect(result.current.status).toBe("loading");
  await act(async () => answers.b.resolve(ok("shop b")));
  expect(result.current).toMatchObject({ status: "ready", data: "shop b" });
});

test("replace shows new data at once, and an older load cannot overwrite it", async () => {
  const answers = [deferred(), deferred()];
  let call = 0;
  const { result } = renderHook(() => useLoad(() => answers[call++].promise, []));
  await act(async () => answers[0].resolve(ok("loaded")));

  act(() => result.current.reload()); // a load is still running...
  act(() => result.current.replace("saved")); // ...when a save answers with newer data
  expect(result.current).toMatchObject({ status: "ready", data: "saved" });
  await act(async () => answers[1].resolve(ok("stale")));
  expect(result.current).toMatchObject({ status: "ready", data: "saved" });
});
