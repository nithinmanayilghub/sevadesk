// Tests for useSends (story 4.4): this screen's own sends, shared by the Chat Page and the Inbox.
import { act, renderHook, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { components } from "@/api/schema";
import { useSends, type Post } from "./useSends";

type MessageOut = components["schemas"]["MessageOut"];

function saved(body: string, clientMessageId: string): MessageOut {
  return { seq: 1, author_type: "user", body, lang: "en", client_message_id: clientMessageId, actions: [], created_at: "" };
}

const ok: Post = async (body, id) => ({ data: saved(body, id), response: new Response(null, { status: 201 }) });

function failsWith(status: number, error: unknown = undefined): Post {
  return async () => ({ data: undefined, error, response: new Response(null, { status }) });
}

test("send marks a saved Message sent", async () => {
  const { result } = renderHook(() => useSends(ok));
  act(() => result.current.send("On my way"));
  expect(result.current.sent[0]).toMatchObject({ body: "On my way", status: "sending" });
  await waitFor(() => expect(result.current.sent[0].status).toBe("sent"));
  expect(result.current.sent[0].message?.body).toBe("On my way");
});

test("a 422 fails with the server's reason and no Retry", async () => {
  const error = { error: { code: "validation_error", message: "Some fields need fixing.", fields: [{ field: "body", message: "Write a message first." }] } };
  const { result } = renderHook(() => useSends(failsWith(422, error)));
  act(() => result.current.send("x"));
  await waitFor(() => expect(result.current.sent[0].status).toBe("failed"));
  expect(result.current.sent[0]).toMatchObject({ reason: "Write a message first.", canRetry: false });
});

test("a network error fails with Retry", async () => {
  const { result } = renderHook(() => useSends(() => Promise.reject(new TypeError("offline"))));
  act(() => result.current.send("x"));
  await waitFor(() => expect(result.current.sent[0].status).toBe("failed"));
  expect(result.current.sent[0].canRetry).toBe(true);
});

test("retry sends the same client_message_id", async () => {
  const post = vi.fn<Post>(failsWith(500));
  const { result } = renderHook(() => useSends(post));
  act(() => result.current.send("x"));
  await waitFor(() => expect(result.current.sent[0].status).toBe("failed"));
  const { clientMessageId } = result.current.sent[0];
  post.mockImplementation(ok);
  act(() => result.current.retry(clientMessageId, "x"));
  await waitFor(() => expect(result.current.sent[0].status).toBe("sent"));
  expect(post.mock.calls.map(([, id]) => id)).toEqual([clientMessageId, clientMessageId]);
});

test("onSent gets the saved Message", async () => {
  const onSent = vi.fn();
  const { result } = renderHook(() => useSends(ok, { onSent }));
  act(() => result.current.send("On my way"));
  await waitFor(() => expect(onSent).toHaveBeenCalledWith(expect.objectContaining({ body: "On my way" })));
});
