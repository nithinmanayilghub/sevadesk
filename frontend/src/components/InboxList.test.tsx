// Tests for InboxList (story 4.3): first load, rows, empty Inbox, Load more, and polling.
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { InboxList } from "./InboxList";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn() } }));
const GET = vi.mocked(api.GET);
const PATH = "/api/v1/inbox/conversations";

function row(id: string, overrides: object = {}) {
  return {
    conversation_id: id,
    state: "agent",
    last_message_preview: `message ${id}`,
    last_message_at: "2020-01-01T06:00:00Z", // Wed, 1 Jan 2020 in IST
    ...overrides,
  };
}

function answer(rows: object[], next_cursor: string | null = null) {
  return { data: { conversations: rows, next_cursor, chat_slug: "ravi-k7m2qx", timezone: "Asia/Kolkata" } } as never;
}

const failed = { data: undefined, response: new Response(null, { status: 503 }) } as never;
const rows = (from: number, to: number) => Array.from({ length: to - from }, (_, i) => row(`c${from + i}`));

// Braces: a function returned from beforeEach runs as cleanup after the test, and GET is one.
beforeEach(() => {
  GET.mockReset();
});

test("shows skeleton rows while the first page loads", () => {
  GET.mockReturnValue(new Promise(() => {}));
  render(<InboxList />);
  expect(screen.getByLabelText("Loading")).toHaveAttribute("aria-busy", "true");
});

test("first load fails, Try again shows the rows", async () => {
  GET.mockResolvedValueOnce(failed).mockResolvedValueOnce(answer([row("c1")]));
  render(<InboxList />);
  fireEvent.click(await screen.findByRole("button", { name: "Try again" }));
  expect(await screen.findByText("message c1")).toBeInTheDocument();
});

test("shows a row: badge, New visitor, one-line preview, Business time, link", async () => {
  GET.mockResolvedValue(answer([row("c1", { state: "handoff" })]));
  render(<InboxList />);
  const link = await screen.findByRole("link", { name: /New visitor/ });
  expect(link).toHaveAttribute("href", "/app/inbox/c1");
  expect(link).toHaveTextContent("Needs Human");
  expect(screen.getByText("message c1")).toHaveClass("truncate");
  expect(screen.getByText("Wed, 1 Jan 2020")).toBeInTheDocument();
  expect(GET).toHaveBeenCalledWith(PATH);
});

test("empty inbox shows the share message and a Copy link button", async () => {
  GET.mockResolvedValue(answer([]));
  render(<InboxList />);
  expect(
    await screen.findByText("No conversations yet. Share your chat link to get your first customer."),
  ).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Copy link" })).toBeInTheDocument();
});

test("Load more adds the next page and hides when there is none", async () => {
  GET.mockResolvedValueOnce(answer([row("c1")], "p2")).mockResolvedValueOnce(answer([row("c2")]));
  render(<InboxList />);
  fireEvent.click(await screen.findByRole("button", { name: "Load more" }));
  expect(await screen.findByText("message c2")).toBeInTheDocument();
  expect(screen.getByText("message c1")).toBeInTheDocument();
  expect(GET).toHaveBeenLastCalledWith(PATH, { params: { query: { cursor: "p2" } } });
  expect(screen.queryByRole("button", { name: "Load more" })).not.toBeInTheDocument();
});

test('Load more failure shows "Could not load more. Try again."', async () => {
  GET.mockResolvedValueOnce(answer([row("c1")], "p2")).mockResolvedValueOnce(failed);
  render(<InboxList />);
  fireEvent.click(await screen.findByRole("button", { name: "Load more" }));
  expect(await screen.findByText("Could not load more. Try again.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Load more" })).toBeEnabled();
});

describe("polling", () => {
  // Let time pass, inside act() so React applies the answers.
  async function wait(ms = 0) {
    await act(async () => {
      await vi.advanceTimersByTimeAsync(ms);
    });
  }

  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  test("a poll replaces the list with the newest top rows", async () => {
    GET.mockResolvedValueOnce(answer([row("c1")])).mockResolvedValueOnce(answer([row("c2"), row("c1")]));
    render(<InboxList />);
    await wait();
    expect(screen.queryByText("message c2")).not.toBeInTheDocument();
    await wait(5000);
    expect(GET).toHaveBeenLastCalledWith(PATH, { params: { query: { limit: 20 } }, signal: expect.any(AbortSignal) });
    expect(screen.getByText("message c2")).toBeInTheDocument();
  });

  test("a poll does not wipe a page Load more just added", async () => {
    let finishLoadMore: (value: never) => void = () => {};
    GET.mockResolvedValueOnce(answer(rows(0, 20), "p2"));
    GET.mockImplementationOnce((() => new Promise((resolve) => (finishLoadMore = resolve))) as never);
    GET.mockResolvedValue(answer(rows(0, 25)));
    render(<InboxList />);
    await wait();
    fireEvent.click(screen.getByRole("button", { name: "Load more" }));
    await wait(6000); // Load more still running: no poll may start
    expect(GET).toHaveBeenCalledTimes(2);
    finishLoadMore(answer(rows(20, 25)));
    await wait();
    expect(screen.getByText("message c24")).toBeInTheDocument();
    await wait(5000); // the next poll asks for all 25 rows on screen
    expect(GET).toHaveBeenLastCalledWith(PATH, { params: { query: { limit: 25 } }, signal: expect.any(AbortSignal) });
    expect(screen.getByText("message c24")).toBeInTheDocument();
  });
});
