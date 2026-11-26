// The Inbox's right pane when no Conversation is open (desktop only; see layout.tsx).
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Inbox · SevaDesk" };

export default function Page() {
  return <p className="text-muted-foreground">Pick a conversation to read it.</p>;
}
