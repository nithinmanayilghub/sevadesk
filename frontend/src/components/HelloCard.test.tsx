// Tests for HelloCard: success, network failure, and API error responses.
import { render, screen } from "@testing-library/react";
import { vi, test, expect, beforeEach } from "vitest";
import { api } from "@/api/client";
import { HelloCard } from "./HelloCard";

vi.mock("@/api/client", () => ({ api: { GET: vi.fn() } }));
const GET = vi.mocked(api.GET);
beforeEach(() => {
  GET.mockReset();
});

test("shows the hello value and backend version", async () => {
  GET.mockResolvedValue({ data: { message: "Hello from SevaDesk", version: "test-1" } } as never);
  render(<HelloCard />);
  expect(await screen.findByText("Hello from SevaDesk")).toBeInTheDocument();
  expect(screen.getByText("Backend version: test-1")).toBeInTheDocument();
  expect(GET).toHaveBeenCalledWith("/api/v1/hello");
});

test("shows an error when the API fails", async () => {
  GET.mockRejectedValue(new Error("network down"));
  render(<HelloCard />);
  expect(await screen.findByText("Could not reach the backend.")).toBeInTheDocument();
});

test("shows an error when the API returns an error", async () => {
  GET.mockResolvedValue({ error: { detail: "boom" } } as never);
  render(<HelloCard />);
  expect(await screen.findByText("Could not reach the backend.")).toBeInTheDocument();
});
