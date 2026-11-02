"use client";
// Card that asks the backend for the hello value and shows it (or an error).
import { useEffect, useState } from "react";
import { api } from "@/api/client";

type HelloState =
  | { status: "loading" }
  | { status: "ready"; message: string; version: string }
  | { status: "error" };

export function HelloCard() {
  const [state, setState] = useState<HelloState>({ status: "loading" });

  // Runs once when the card appears on screen.
  useEffect(() => {
    async function loadHello() {
      try {
        const { data } = await api.GET("/api/v1/hello");
        if (data) {
          setState({ status: "ready", message: data.message, version: data.version });
        } else {
          setState({ status: "error" });
        }
      } catch {
        setState({ status: "error" });
      }
    }
    loadHello();
  }, []);

  return (
    <section className="rounded-lg border border-zinc-300 p-6 shadow-sm">
      {state.status === "loading" && <p>Loading…</p>}
      {state.status === "error" && <p>Could not reach the backend.</p>}
      {state.status === "ready" && (
        <>
          <p className="text-2xl font-semibold">{state.message}</p>
          <p className="mt-2 text-sm text-zinc-500">Backend version: {state.version}</p>
        </>
      )}
    </section>
  );
}
