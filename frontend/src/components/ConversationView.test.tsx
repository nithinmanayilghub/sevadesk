// Tests for ConversationView (story 4.4): one open Conversation in the Inbox. The history, the
// Handoff bar (Take over / Give back to Agent), replies, the one-time hint, and polling.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { ConversationView, HINT_KEY } from "./ConversationView";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn(), POST: vi.fn() } }));
const GET = vi.mocked(api.GET);
const POST = vi.mocked(api.POST);

type MessageOut = components["schemas"]["MessageOut"];
const ID = "0190a1b2-c3d4-7e5f-8a9b-0c1d2e3f4a5b";
const AGENT_BAR = "Agent is replying";
const HANDOFF_BAR = "You are replying. The Agent is paused.";
const HINT = "Your reply pauses the Agent.";

function message(seq: number, body: string, author_type = "customer"): MessageOut {
  return { seq, author_type, body, lang: "en", client_message_id: null, actions: [], created_at: "2026-11-27T10:00:00Z" };
}

function poll(messages: MessageOut[], state = "agent", cursor = "c1") {
  return {
    data: { changed: true, messages, snapshot: { conversation_state: state }, cursor },
    response: new Response(null, { status: 200 }),
  } as never;
}

function stateAnswer(state: string) {
  return { data: { state }, response: new Response(null, { status: 200 }) } as never;
}

function view() {
  render(<ConversationView conversationId={ID} />);
}

// Let time pass, inside act() so React applies the answers.
async function wait(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

beforeEach(() => {
  GET.mockReset();
  POST.mockReset();
  localStorage.clear();
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
});

test("shows the full history, Customer on the right, team on the left with a label", async () => {
  // Behaviour: the User reads every Message in order, with the same sides as the Chat Page (UX-DR7).
  GET.mockResolvedValue(poll([message(1, "Fan not working"), message(2, "On my way", "user")]));
  view();
  await wait();
  expect(screen.getAllByRole("listitem").map((li) => li.textContent)).toEqual(["Fan not working", "TeamOn my way"]);
  expect(screen.getByText("Fan not working").closest("li")).toHaveClass("ml-auto");
  expect(screen.getByText("On my way").closest("li")).toHaveClass("mr-auto");
  expect(GET).toHaveBeenCalledWith("/api/v1/inbox/conversations/{conversation_id}/messages", {
    params: { path: { conversation_id: ID } },
  });
  expect(screen.getByRole("log")).toHaveAttribute("aria-live", "polite");
  expect(screen.getByRole("heading", { name: "Conversation" })).toBeInTheDocument();
});

test('agent state shows "Agent is replying" and Take over', async () => {
  GET.mockResolvedValue(poll([message(1, "Hi")]));
  view();
  await wait();
  expect(screen.getByRole("status", { name: "Who replies" })).toHaveTextContent(AGENT_BAR);
  expect(screen.getByRole("button", { name: "Take over" })).toHaveClass("min-h-11");
});

test("Take over posts and switches the bar; the button keeps focus", async () => {
  // Behaviour: a person takes the chat; the bar says so, and keyboard focus stays on its button.
  GET.mockResolvedValue(poll([message(1, "Hi")]));
  POST.mockResolvedValue(stateAnswer("handoff"));
  view();
  await wait();
  const button = screen.getByRole("button", { name: "Take over" });
  button.focus();
  fireEvent.click(button);
  await wait();
  expect(POST).toHaveBeenCalledWith("/api/v1/inbox/conversations/{conversation_id}/take-over", {
    params: { path: { conversation_id: ID } },
  });
  expect(screen.getByRole("status", { name: "Who replies" })).toHaveTextContent(HANDOFF_BAR);
  expect(screen.getByRole("button", { name: "Give back to Agent" })).toHaveFocus();
});

test("Give back to Agent posts and switches the bar back", async () => {
  GET.mockResolvedValue(poll([message(1, "Hi")], "handoff"));
  POST.mockResolvedValue(stateAnswer("agent"));
  view();
  await wait();
  fireEvent.click(screen.getByRole("button", { name: "Give back to Agent" }));
  await wait();
  expect(POST).toHaveBeenCalledWith("/api/v1/inbox/conversations/{conversation_id}/give-back", {
    params: { path: { conversation_id: ID } },
  });
  expect(screen.getByRole("status", { name: "Who replies" })).toHaveTextContent(AGENT_BAR);
});

test("a failed take over shows an alert", async () => {
  GET.mockResolvedValue(poll([message(1, "Hi")]));
  POST.mockResolvedValue({ data: undefined, error: {}, response: new Response(null, { status: 500 }) } as never);
  view();
  await wait();
  fireEvent.click(screen.getByRole("button", { name: "Take over" }));
  await wait();
  expect(screen.getByRole("alert")).toHaveTextContent("Could not change who replies. Try again.");
  expect(screen.getByRole("status", { name: "Who replies" })).toHaveTextContent(AGENT_BAR);
});

test("a reply switches to handoff and the hint is gone for good", async () => {
  // Behaviour: the first reply shows the hint before it; after it the Agent is paused, and the
  // hint never shows again in this browser (UX-DR13).
  GET.mockResolvedValue(poll([message(1, "Hi")]));
  POST.mockImplementation((async (_path: string, { body }: { body: { body: string; client_message_id: string } }) => ({
    data: { ...message(2, body.body, "user"), client_message_id: body.client_message_id },
    response: new Response(null, { status: 201 }),
  })) as never);
  view();
  await wait();
  expect(screen.getByText(HINT)).toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Reply" })).toHaveAccessibleDescription(HINT);
  fireEvent.change(screen.getByRole("textbox", { name: "Reply" }), { target: { value: "On my way" } });
  fireEvent.click(screen.getByRole("button", { name: "Send" }));
  await wait();
  expect(POST).toHaveBeenCalledWith("/api/v1/inbox/conversations/{conversation_id}/messages", {
    params: { path: { conversation_id: ID } },
    body: { body: "On my way", client_message_id: expect.any(String) },
  });
  expect(screen.getByRole("status", { name: "Who replies" })).toHaveTextContent(HANDOFF_BAR);
  expect(screen.queryByText(HINT)).not.toBeInTheDocument();
  expect(localStorage.getItem(HINT_KEY)).toBe("1");
});

test("the hint stays hidden once seen", async () => {
  localStorage.setItem(HINT_KEY, "1");
  GET.mockResolvedValue(poll([message(1, "Hi")]));
  view();
  await wait();
  expect(screen.queryByText(HINT)).not.toBeInTheDocument();
});

test("Enter sends with a fine pointer; Shift+Enter does not", async () => {
  vi.stubGlobal("matchMedia", () => ({ matches: true }));
  GET.mockResolvedValue(poll([message(1, "Hi")]));
  POST.mockResolvedValue({ data: message(2, "x", "user"), response: new Response(null, { status: 201 }) } as never);
  view();
  await wait();
  const box = screen.getByRole("textbox", { name: "Reply" });
  fireEvent.change(box, { target: { value: "line one" } });
  fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
  expect(POST).not.toHaveBeenCalled();
  fireEvent.keyDown(box, { key: "Enter" });
  await wait();
  expect(POST).toHaveBeenCalledTimes(1);
});

test("a 404 shows not found with a link back", async () => {
  GET.mockResolvedValue({ data: undefined, response: new Response(null, { status: 404 }) } as never);
  view();
  await wait();
  expect(screen.getByText("This conversation was not found.")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Back to Inbox" })).toHaveAttribute("href", "/app/inbox");
});

test("a poll adds a new Customer Message", async () => {
  GET.mockResolvedValueOnce(poll([message(1, "Hi"), message(2, "Hello", "user")]));
  GET.mockResolvedValueOnce(poll([message(3, "Thanks")], "handoff", "c2"));
  view();
  await wait();
  await wait(5000);
  expect(screen.getByText("Thanks")).toBeInTheDocument();
  expect(GET).toHaveBeenLastCalledWith("/api/v1/inbox/conversations/{conversation_id}/messages", {
    params: { path: { conversation_id: ID }, query: { cursor: "c1" } },
    signal: expect.any(AbortSignal),
  });
});

test("a poll that started before a click does not undo it", async () => {
  // Behaviour: an old poll answer (asked before Take over) must not put the old state back.
  let finishPoll: (value: unknown) => void = () => {};
  GET.mockResolvedValueOnce(poll([message(1, "Hi")]));
  GET.mockImplementationOnce((() => new Promise((resolve) => (finishPoll = resolve))) as never);
  POST.mockResolvedValue(stateAnswer("handoff"));
  view();
  await wait();
  await wait(5000); // the poll starts and hangs
  fireEvent.click(screen.getByRole("button", { name: "Take over" }));
  await wait();
  await act(async () => finishPoll(poll([message(2, "Still there?")], "agent", "c2")));
  expect(screen.getByText("Still there?")).toBeInTheDocument(); // its Messages still count
  expect(screen.getByRole("status", { name: "Who replies" })).toHaveTextContent(HANDOFF_BAR);
});

test("a closed chat shows no bar but shows the composer", async () => {
  GET.mockResolvedValue(poll([message(1, "Hi")], "closed"));
  view();
  await wait();
  expect(screen.queryByRole("button", { name: /Take over|Give back/ })).not.toBeInTheDocument();
  expect(screen.getByRole("textbox", { name: "Reply" })).toBeInTheDocument();
});
