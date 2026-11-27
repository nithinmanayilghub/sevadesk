"use client";
// The Inbox layout (stories 4.3, 4.4, UX-DR17). Below 1024px ("lg"): ONE pane. The list, or,
// with a Conversation open, that Conversation (the list is hidden then). From lg: two panes,
// the list on the left and the open Conversation (this route's page) on the right.
// A layout, not a page: the list and its poll stay alive while the User opens Conversations.
// useSelectedLayoutSegment: the [conversationId] part of the URL, or null on /app/inbox.
// min-w-0: a flex or grid child may shrink below its content's width, so a long preview is
// cut by "truncate" instead of making the page scroll sideways at 360px (NFR-6).
import { useSelectedLayoutSegment } from "next/navigation";
import type { ReactNode } from "react";
import { InboxList } from "@/components/InboxList";

export default function InboxLayout({ children }: { children: ReactNode }) {
  const open = useSelectedLayoutSegment() !== null;
  return (
    <main className="flex min-w-0 flex-1 flex-col lg:grid lg:grid-cols-[22rem_1fr]">
      <section
        aria-label="Conversations"
        className={`${open ? "hidden lg:flex" : "flex"} min-w-0 flex-col gap-4 px-page-x py-6 lg:border-r`}
      >
        <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
        <InboxList />
      </section>
      <section className={`${open ? "block" : "hidden lg:block"} min-w-0 px-page-x py-6`}>{children}</section>
    </main>
  );
}
