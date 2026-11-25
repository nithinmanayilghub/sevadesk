// Tests for usePoll: the one shared poll loop (story 4.2, AD-7). Fake timers, so a test
// decides when time passes; a mock poll, so a test decides when (and how) each poll ends.
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { usePoll } from "./usePoll";

type Poll = (signal: AbortSignal) => Promise<boolean>;

function setVisibility(state: "visible" | "hidden", notify = true) {
  Object.defineProperty(document, "visibilityState", {
    configurable: true,
    value: state,
  });
  if (notify) document.dispatchEvent(new Event("visibilitychange"));
}

// Let time pass, inside act() so React applies any state change.
async function advance(ms: number) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  setVisibility("visible", false);
});

afterEach(() => {
  vi.useRealTimers();
  setVisibility("visible", false);
});

test("polls every 5 s while visible", async () => {
  const poll = vi.fn().mockResolvedValue(true);
  renderHook(() => usePoll(poll, { enabled: true }));
  expect(poll).toHaveBeenCalledTimes(0);
  await advance(5000);
  expect(poll).toHaveBeenCalledTimes(1);
  await advance(5000);
  expect(poll).toHaveBeenCalledTimes(2);
});

test("never runs two polls at once", async () => {
  // Each poll takes 3 s. The next one starts 5 s after the previous one STARTED, never sooner.
  const poll = vi.fn(
    () =>
      new Promise<boolean>((resolve) => setTimeout(() => resolve(true), 3000)),
  );
  renderHook(() => usePoll(poll, { enabled: true }));
  await advance(5000); // poll 1 starts
  await advance(4999); // poll 1 ended at 8000; 9999 now
  expect(poll).toHaveBeenCalledTimes(1);
  await advance(1); // 10 000
  expect(poll).toHaveBeenCalledTimes(2);
});

test("aborts a slow poll and starts the next within 5 s", async () => {
  const poll = vi.fn<Poll>(() => new Promise<boolean>(() => {})); // never answers
  renderHook(() => usePoll(poll, { enabled: true }));
  await advance(5000); // poll 1 starts
  const signal = poll.mock.calls[0][0];
  await advance(4999);
  expect(signal.aborted).toBe(false);
  await advance(1); // 5 s after it started
  expect(signal.aborted).toBe(true);
  // The next poll waits max(0, 5000 - 5000) = 0 ms. The fake clock runs a timer set during
  // its own run only at its next move, so move it by 1 ms.
  await advance(1);
  expect(poll).toHaveBeenCalledTimes(2); // about 10 000 ms total
});

test("stops while hidden and polls at once when visible", async () => {
  const poll = vi.fn().mockResolvedValue(true);
  renderHook(() => usePoll(poll, { enabled: true }));
  act(() => setVisibility("hidden"));
  await advance(20_000);
  expect(poll).toHaveBeenCalledTimes(0);
  await act(async () => setVisibility("visible"));
  expect(poll).toHaveBeenCalledTimes(1);
});

test("shows reconnecting after 3 failures and hides it after a success", async () => {
  const poll = vi
    .fn()
    .mockResolvedValueOnce(false)
    .mockRejectedValueOnce(new Error("network"))
    .mockResolvedValueOnce(false)
    .mockResolvedValue(true);
  const { result } = renderHook(() => usePoll(poll, { enabled: true }));
  await advance(10_000); // 2 failures
  expect(result.current.reconnecting).toBe(false);
  await advance(5000); // 3 failures
  expect(result.current.reconnecting).toBe(true);
  await advance(5000); // a success
  expect(result.current.reconnecting).toBe(false);
});

test("disable while in flight aborts and drops the answer", async () => {
  let answer: (ok: boolean) => void = () => {};
  const poll = vi.fn<Poll>(
    () => new Promise<boolean>((resolve) => (answer = resolve)),
  );
  const { rerender } = renderHook(({ enabled }) => usePoll(poll, { enabled }), {
    initialProps: { enabled: true },
  });
  await advance(5000);
  rerender({ enabled: false });
  expect(poll.mock.calls[0][0].aborted).toBe(true);
  await act(async () => answer(true));
  await advance(20_000);
  expect(poll).toHaveBeenCalledTimes(1);
});

test("does nothing while disabled", async () => {
  const poll = vi.fn().mockResolvedValue(true);
  renderHook(() => usePoll(poll, { enabled: false }));
  await advance(20_000);
  expect(poll).toHaveBeenCalledTimes(0);
});

test("stops after unmount", async () => {
  const poll = vi.fn().mockResolvedValue(true);
  const { unmount } = renderHook(() => usePoll(poll, { enabled: true }));
  await advance(5000);
  unmount();
  await advance(20_000);
  expect(poll).toHaveBeenCalledTimes(1);
});

test("uses the newest poll function", async () => {
  const first = vi.fn().mockResolvedValue(true);
  const second = vi.fn().mockResolvedValue(true);
  const { rerender } = renderHook(
    ({ poll }) => usePoll(poll, { enabled: true }),
    {
      initialProps: { poll: first },
    },
  );
  rerender({ poll: second }); // a new cursor gives the page a new function; the loop goes on
  await advance(5000);
  expect(first).toHaveBeenCalledTimes(0);
  expect(second).toHaveBeenCalledTimes(1);
});
