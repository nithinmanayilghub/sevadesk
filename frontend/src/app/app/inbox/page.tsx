// The Inbox (/app/inbox). Placeholder until its story builds it.
import type { Metadata } from "next";

export const metadata: Metadata = { title: "Inbox · SevaDesk" };

export default function Page() {
  return (
    <main className="flex flex-col gap-2 px-page-x py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
      <p className="text-muted-foreground">Coming soon.</p>
    </main>
  );
}
