// Tests for ChatPanel (story 4.1): the Customer's own chat on the Chat Page. Bubbles, the
// DPDP notice, the composer, "Not sent · Retry", and the keyboard.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { ChatPanel } from "./ChatPanel";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn(), POST: vi.fn() } }));
const GET = vi.mocked(api.GET);
const POST = vi.mocked(api.POST);

type MessageOut = components["schemas"]["MessageOut"];

const NOTICE =
  "We collect your name, phone, and address only to book your job. Ravi Electricals can delete them on request.";

function message(seq: number, body: string, extra: Partial<MessageOut> = {}): MessageOut {
  return {
    seq,
    author_type: "customer",
    body,
    lang: "en",
    client_message_id: `id-${seq}`,
    actions: [],
    created_at: "2026-11-22T10:00:00Z",
    ...extra,
  };
}

function loads(messages: MessageOut[]) {
  GET.mockResolvedValue({ data: { messages }, response: new Response(null, { status: 200 }) } as never);
}

function saves() {
  // The server answers with the Message it saved, echoing the body and client_message_id sent.
  POST.mockImplementation((async (_path: string, { body }: { body: { body: string; client_message_id: string } }) => ({
    data: message(1, body.body, { client_message_id: body.client_message_id }),
    response: new Response(null, { status: 201 }),
  })) as never);
}

function fails() {
  POST.mockResolvedValue({
    data: undefined,
    error: { error: { code: "internal_error", message: "x" } },
    response: new Response(null, { status: 500 }),
  } as never);
}

const onHasMessages = vi.fn();

function panel(takingRequests = true) {
  render(
    <ChatPanel
      slug="ravi-k7m2qx"
      businessName="Ravi Electricals"
      takingRequests={takingRequests}
      onHasMessages={onHasMessages}
    />,
  );
}

function type(text: string) {
  fireEvent.change(screen.getByRole("textbox", { name: "Message" }), { target: { value: text } });
}

beforeEach(() => {
  GET.mockReset();
  POST.mockReset();
  onHasMessages.mockReset();
});

afterEach(() => vi.unstubAllGlobals());

test("shows saved Messages: the Customer's on the right, others on the left", async () => {
  loads([message(1, "Fan not working"), message(2, "We can come today", { author_type: "user" })]);
  panel();
  const mine = await screen.findByText("Fan not working");
  expect(mine.closest("li")).toHaveClass("ml-auto");
  expect(screen.getByText("We can come today").closest("li")).toHaveClass("mr-auto");
  expect(GET).toHaveBeenCalledWith("/api/v1/chat/{chat_slug}/messages", {
    params: { path: { chat_slug: "ravi-k7m2qx" } },
  });
});

test('marks Hindi text with lang="hi"', async () => {
  loads([message(1, "नमस्ते", { lang: "hi" }), message(2, "Hello")]);
  panel();
  expect((await screen.findByText("नमस्ते")).closest("li")).toHaveAttribute("lang", "hi");
  expect(screen.getByText("Hello").closest("li")).not.toHaveAttribute("lang");
});

test("the live region is there even before the first Message", async () => {
  loads([]);
  panel();
  await screen.findByRole("textbox", { name: "Message" });
  expect(screen.getByRole("log")).toHaveAttribute("aria-live", "polite");
});

test("shows the DPDP notice until the first Message", async () => {
  loads([]);
  saves();
  panel();
  expect(await screen.findByText(NOTICE)).toBeInTheDocument();
  expect(onHasMessages).toHaveBeenLastCalledWith(false);
  type("Fan not working");
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(screen.queryByText(NOTICE)).not.toBeInTheDocument();
  expect(onHasMessages).toHaveBeenLastCalledWith(true);
  await screen.findByText("Fan not working");
});

test("no notice when the chat already has Messages", async () => {
  loads([message(1, "Fan not working")]);
  panel();
  await screen.findByText("Fan not working");
  expect(screen.queryByText(NOTICE)).not.toBeInTheDocument();
  expect(onHasMessages).toHaveBeenLastCalledWith(true);
});

test("no composer and no notice when the Business is not taking requests", async () => {
  loads([message(1, "Old question")]);
  panel(false);
  await screen.findByText("Old question");
  expect(screen.queryByRole("textbox", { name: "Message" })).not.toBeInTheDocument();
  expect(screen.queryByText(NOTICE)).not.toBeInTheDocument();
});

test("no composer while the chat is loading", () => {
  GET.mockReturnValue(new Promise(() => {}) as never); // never answers
  panel();
  expect(screen.queryByRole("textbox", { name: "Message" })).not.toBeInTheDocument();
});

test("a failed load shows a message, and Try again loads again", async () => {
  GET.mockResolvedValue({ data: undefined, response: new Response(null, { status: 500 }) } as never);
  panel();
  expect(await screen.findByText("Could not load the chat.")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await vi.waitFor(() => expect(GET).toHaveBeenCalledTimes(2));
});

test("Send posts the text with a new id, shows the bubble, and keeps focus in the box", async () => {
  loads([]);
  saves();
  panel();
  await screen.findByRole("textbox", { name: "Message" });
  type("  Fan not working  ");
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByText("Fan not working")).toBeInTheDocument();
  const [, options] = POST.mock.calls[0] as unknown as [string, { body: { body: string; client_message_id: string } }];
  expect(options.body.body).toBe("Fan not working");
  expect(options.body.client_message_id).toMatch(/^[0-9a-f-]{36}$/);
  const box = screen.getByRole("textbox", { name: "Message" });
  expect(box).toHaveValue("");
  expect(box).toHaveFocus();
});

test("a failed send shows Not sent · Retry, and the text stays", async () => {
  loads([]);
  fails();
  panel();
  await screen.findByRole("textbox", { name: "Message" });
  type("Fan not working");
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByText("Not sent")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
  expect(screen.getByText("Fan not working")).toBeInTheDocument();
});

test("a network failure also shows Not sent", async () => {
  loads([]);
  POST.mockRejectedValue(new TypeError("Failed to fetch"));
  panel();
  await screen.findByRole("textbox", { name: "Message" });
  type("Fan not working");
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  expect(await screen.findByText("Not sent")).toBeInTheDocument();
});

test("retry sends the same client_message_id", async () => {
  loads([]);
  fails();
  panel();
  await screen.findByRole("textbox", { name: "Message" });
  type("Fan not working");
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await screen.findByText("Not sent");
  saves();
  fireEvent.click(screen.getByRole("button", { name: "Retry" }));
  await vi.waitFor(() => expect(screen.queryByText("Not sent")).not.toBeInTheDocument());
  const ids = POST.mock.calls.map((call) => (call[1] as { body: { client_message_id: string } }).body.client_message_id);
  expect(ids).toHaveLength(2);
  expect(ids[1]).toBe(ids[0]);
});

test("Send is disabled for an empty or spaces-only text", async () => {
  loads([]);
  panel();
  await screen.findByRole("textbox", { name: "Message" });
  expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
  type("   ");
  expect(screen.getByRole("button", { name: "Send" })).toBeDisabled();
});

function stubPointer(fine: boolean) {
  vi.stubGlobal("matchMedia", (query: string) => ({ matches: fine && query === "(pointer: fine)" }));
}

test("with a mouse, Enter sends and Shift+Enter does not", async () => {
  stubPointer(true);
  loads([]);
  saves();
  panel();
  const box = await screen.findByRole("textbox", { name: "Message" });
  type("Fan not working");
  fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
  expect(POST).not.toHaveBeenCalled();
  await act(async () => {
    fireEvent.keyDown(box, { key: "Enter" });
  });
  expect(POST).toHaveBeenCalledTimes(1);
});

test("on a touch screen, Enter makes a new line instead of sending", async () => {
  stubPointer(false);
  loads([]);
  panel();
  const box = await screen.findByRole("textbox", { name: "Message" });
  type("Fan not working");
  fireEvent.keyDown(box, { key: "Enter" });
  expect(POST).not.toHaveBeenCalled();
});

test("without matchMedia, Enter does not send", async () => {
  vi.stubGlobal("matchMedia", undefined);
  loads([]);
  panel();
  const box = await screen.findByRole("textbox", { name: "Message" });
  type("Fan not working");
  fireEvent.keyDown(box, { key: "Enter" });
  expect(POST).not.toHaveBeenCalled();
});

function failsWith(status: number, error: { code: string; message: string; fields?: { field: string; message: string }[] }) {
  POST.mockResolvedValue({ data: undefined, error: { error }, response: new Response(null, { status }) } as never);
}

async function sendOne() {
  await screen.findByRole("textbox", { name: "Message" });
  type("Fan not working");
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
}

test("a send the server refuses shows its reason, and no Retry", async () => {
  // Review finding: a 422 can never pass on retry, so "Retry" forever helped no one.
  loads([]);
  failsWith(422, {
    code: "validation_error",
    message: "Some fields need fixing.",
    fields: [{ field: "body", message: "This message has characters we cannot save." }],
  });
  panel();
  await sendOne();
  expect(await screen.findByText("This message has characters we cannot save.")).toBeInTheDocument();
  expect(screen.getByText("Not sent")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
});

test("too fast shows the reason, and Retry stays", async () => {
  loads([]);
  failsWith(429, { code: "too_many_messages", message: "You are sending messages too fast. Please wait a few minutes." });
  panel();
  await sendOne();
  expect(await screen.findByText("You are sending messages too fast. Please wait a few minutes.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
});

test("the box takes at most 2000 characters, the server's limit", async () => {
  loads([]);
  panel();
  expect(await screen.findByRole("textbox", { name: "Message" })).toHaveAttribute("maxLength", "2000");
});

test("Retry is at least 44 px wide and tall, for a finger", async () => {
  loads([]);
  fails();
  panel();
  await sendOne();
  expect(await screen.findByRole("button", { name: "Retry" })).toHaveClass("min-h-11", "min-w-11");
});
