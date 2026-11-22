// Tests for ChatPage (/c/{slug}): the Business name, Services with "from ₹" Prices,
// "Not taking requests yet", an unknown link, other load errors, and the mobile Services toggle.
// The chat itself (ChatPanel, with the DPDP notice) has its own tests: here it is a stub.
import { fireEvent, render, screen, within } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { api } from "@/api/client";
import { ChatPage } from "./ChatPage";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn() } }));
// A stub panel: it shows what the page passed in, and a button that plays "the first Message".
vi.mock("./ChatPanel", () => ({
  ChatPanel: ({ takingRequests, onHasMessages }: { takingRequests: boolean; onHasMessages: (has: boolean) => void }) => (
    <button type="button" data-taking={String(takingRequests)} onClick={() => onHasMessages(true)}>
      stub: first Message
    </button>
  ),
}));
const GET = vi.mocked(api.GET);

beforeEach(() => GET.mockReset());

const FAN = { name: "Fan repair", duration_minutes: 60, price_paise: 49900 };
const AC = { name: "AC service", duration_minutes: 90, price_paise: 149900 };

function page(taking_requests: boolean, services = [FAN, AC]) {
  GET.mockResolvedValue({
    data: { business_name: "Ravi Electricals", taking_requests, services },
    response: new Response(null, { status: 200 }),
  } as never);
  render(<ChatPage slug="ravi-k7m2qx" />);
}

function failWith(status: number) {
  GET.mockResolvedValue({
    data: undefined,
    error: { error: { code: "x", message: "x" } },
    response: new Response(null, { status }),
  } as never);
  render(<ChatPage slug="ravi-k7m2qx" />);
}

test("shows the Business name, Services and the price note", async () => {
  page(true);
  expect(await screen.findByRole("heading", { level: 1, name: "Ravi Electricals" })).toBeInTheDocument();
  const list = within(screen.getByRole("region", { name: "Services & prices" }));
  const [fan, ac] = list.getAllByRole("listitem");
  expect(fan).toHaveTextContent("Fan repair");
  expect(fan).toHaveTextContent("from ₹499");
  expect(fan).toHaveTextContent("1 h");
  expect(ac).toHaveTextContent("from ₹1,499");
  expect(ac).toHaveTextContent("1 h 30 min");
  expect(screen.getAllByText("Final price after inspection. Parts extra.")).toHaveLength(1);
  expect(GET).toHaveBeenCalledWith("/api/v1/chat/{chat_slug}", { params: { path: { chat_slug: "ravi-k7m2qx" } } });
});

test("shows Not taking requests yet, and the Services still show", async () => {
  page(false);
  expect(await screen.findByText("Not taking requests yet")).toBeInTheDocument();
  expect(screen.getByText("Fan repair")).toBeInTheDocument();
});

test("hides Not taking requests yet when the Business is taking requests", async () => {
  page(true);
  await screen.findByText("Fan repair");
  expect(screen.queryByText("Not taking requests yet")).not.toBeInTheDocument();
});

test("hides the Services box when there are no Services", async () => {
  page(false, []);
  expect(await screen.findByText("Not taking requests yet")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Services & prices" })).not.toBeInTheDocument();
  expect(screen.queryByText("Final price after inspection. Parts extra.")).not.toBeInTheDocument();
});

test("two Services with the same name both show", async () => {
  page(true, [FAN, { ...FAN, price_paise: 59900 }]);
  expect(await screen.findAllByText("Fan repair")).toHaveLength(2);
});

test("shows not found for an unknown slug", async () => {
  failWith(404);
  expect(await screen.findByRole("heading", { name: "Chat page not found" })).toBeInTheDocument();
  expect(screen.getByText("Check the link and try again.")).toBeInTheDocument();
  expect(screen.queryByRole("region", { name: "Services & prices" })).not.toBeInTheDocument();
});

test("shows an error with retry on other failures", async () => {
  failWith(500);
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  fireEvent.click(screen.getByRole("button", { name: "Try again" }));
  await vi.waitFor(() => expect(GET).toHaveBeenCalledTimes(2));
});

test("passes taking_requests to the chat panel", async () => {
  page(false);
  expect(await screen.findByRole("button", { name: "stub: first Message" })).toHaveAttribute("data-taking", "false");
});

test("no Services toggle before the first Message", async () => {
  page(true);
  await screen.findByText("Fan repair");
  expect(screen.queryByRole("button", { name: "Services & prices" })).not.toBeInTheDocument();
});

test("after the first Message, a Services & prices button folds the list on mobile", async () => {
  page(true);
  fireEvent.click(await screen.findByRole("button", { name: "stub: first Message" }));
  const toggle = screen.getByRole("button", { name: "Services & prices" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  // Folded = hidden below the md breakpoint only; desktop always shows the list.
  expect(screen.getByRole("region", { name: "Services & prices", hidden: true })).toHaveClass("hidden", "md:flex");
  fireEvent.click(toggle);
  expect(toggle).toHaveAttribute("aria-expanded", "true");
  expect(screen.getByRole("region", { name: "Services & prices" })).not.toHaveClass("hidden");
});
