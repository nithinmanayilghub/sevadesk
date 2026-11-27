// Tests for useLiveThread, through its own interface (no screen): the poll merge, the
// stale-poll guard, and the "gone" case (a 404 on poll ends the thread).
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { components } from "@/api/schema";
import { type FetchThread, useLiveThread } from "./useLiveThread";

type ChatPollOut = components["schemas"]["ChatPollOut"];

function answer(seqs: number[], state = "agent", cursor: string | null = "c1") {
  const data: ChatPollOut = {
    changed: true,
    messages: seqs.map((seq) => ({
      seq,
      author_type: "customer",
      body: `m${seq}`,
      lang: "en",
      client_message_id: null,
      actions: [],
      created_at: "2026-11-27T10:00:00Z",
    })),
    snapshot: { conversation_state: state },
    cursor,
  };
  return { data, response: new Response(null, { status: 200 }) };
}

const post = vi.fn();

function thread(fetch: FetchThread, inputs: unknown[] = ["chat-1"]) {
  return renderHook(({ ins }) => useLiveThread({ fetch, post, inputs: ins }), { initialProps: { ins: inputs } });
}

async function wait(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

test("a poll adds only the new Messages and keeps the newest cursor", async () => {
  const fetch = vi.fn<FetchThread>().mockResolvedValueOnce(answer([1])).mockResolvedValue(answer([1, 2], "agent", "c2"));
  const { result } = thread(fetch);
  await wait();
  await wait(5000);
  expect(result.current.items.map((item) => (item.kind === "saved" ? item.message.seq : -1))).toEqual([1, 2]);
  expect(result.current.data?.cursor).toBe("c2");
  expect(fetch).toHaveBeenLastCalledWith("c1", expect.any(AbortSignal));
});

test("a 404 on poll ends the thread: not_found, no more polls, no Reconnecting", async () => {
  const fetch = vi
    .fn<FetchThread>()
    .mockResolvedValueOnce(answer([1]))
    .mockResolvedValue({ response: new Response(null, { status: 404 }) });
  const { result } = thread(fetch);
  await wait();
  await wait(5000);
  expect(result.current.status).toBe("not_found");
  await wait(20000);
  expect(fetch).toHaveBeenCalledTimes(2);
  expect(result.current.reconnecting).toBe(false);
});

test("another chat after a gone one loads normally", async () => {
  const fetch = vi
    .fn<FetchThread>()
    .mockResolvedValueOnce(answer([1]))
    .mockResolvedValueOnce({ response: new Response(null, { status: 404 }) })
    .mockResolvedValue(answer([7]));
  const { result, rerender } = thread(fetch);
  await wait();
  await wait(5000);
  expect(result.current.status).toBe("not_found");
  rerender({ ins: ["chat-2"] });
  await wait();
  expect(result.current.status).toBe("ready");
});

test("a poll asked before a local state change keeps its Messages but not its state", async () => {
  let release: (value: ReturnType<typeof answer>) => void = () => {};
  const fetch = vi
    .fn<FetchThread>()
    .mockResolvedValueOnce(answer([1]))
    .mockImplementationOnce(() => new Promise((resolve) => (release = resolve)))
    .mockResolvedValue(answer([1, 2], "handoff", "c3"));
  const { result } = thread(fetch);
  await wait();
  await wait(5000); // the poll is out
  act(() => result.current.setConversationState("handoff")); // a click answers first
  await act(async () => release(answer([1, 2], "agent", "c2"))); // the old poll comes back
  expect(result.current.data?.snapshot?.conversation_state).toBe("handoff");
  expect(result.current.items).toHaveLength(2);
  expect(result.current.data?.cursor).toBe("c1"); // the old cursor: the next poll reads again
});
