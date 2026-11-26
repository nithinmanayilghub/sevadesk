// Tests for useNeedsHumanCount (story 4.3, UX-DR16): the red number on the Inbox tab.
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { useNeedsHumanCount } from "./useNeedsHumanCount";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn() } }));
const GET = vi.mocked(api.GET);
const COUNT = "/api/v1/inbox/needs-human-count";
const count = (n: number) => ({ data: { count: n } }) as never;
const failed = { data: undefined, response: new Response(null, { status: 503 }) } as never;

// Let time pass, inside act() so React applies the answers.
async function wait(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  GET.mockReset();
});
afterEach(() => vi.useRealTimers());

test("does not fetch when disabled", async () => {
  // A Technician-only User may not use the Inbox: no request, so no 403 every 5 s.
  const { result } = renderHook(() => useNeedsHumanCount(false));
  await wait(6000);
  expect(GET).not.toHaveBeenCalled();
  expect(result.current).toBe(0);
});

test("fetches at once, then every 5 s", async () => {
  GET.mockResolvedValueOnce(count(2)).mockResolvedValue(count(4));
  const { result } = renderHook(() => useNeedsHumanCount(true));
  await wait();
  expect(GET).toHaveBeenCalledWith(COUNT);
  expect(result.current).toBe(2);
  await wait(5000);
  expect(GET).toHaveBeenLastCalledWith(COUNT, { signal: expect.any(AbortSignal) });
  expect(result.current).toBe(4);
});

test("keeps the last count on a failure", async () => {
  GET.mockResolvedValueOnce(count(2)).mockResolvedValue(failed);
  const { result } = renderHook(() => useNeedsHumanCount(true));
  await wait();
  await wait(5000);
  expect(GET).toHaveBeenCalledTimes(2);
  expect(result.current).toBe(2);
});
