// The Inbox layout (story 4.3, UX-DR17). Below 1024px: the list only. From 1024px ("lg"):
// two panes, the list on the left and the open Conversation (this route's page) on the right.
// A layout, not a page: the list and its poll stay alive while the User opens Conversations.
// min-w-0: a flex or grid child may shrink below its content's width, so a long preview is
// cut by "truncate" instead of making the page scroll sideways at 360px (NFR-6).
import type { ReactNode } from "react";
import { InboxList } from "@/components/InboxList";

export default function InboxLayout({ children }: { children: ReactNode }) {
  return (
    <main className="flex min-w-0 flex-1 flex-col lg:grid lg:grid-cols-[22rem_1fr]">
      <section aria-label="Conversations" className="flex min-w-0 flex-col gap-4 px-page-x py-6 lg:border-r">
        <h1 className="text-2xl font-semibold tracking-tight">Inbox</h1>
        <InboxList />
      </section>
      {/* Story 4.4 shows this pane on mobile too, when a Conversation is open. */}
      <section className="hidden min-w-0 px-page-x py-6 lg:block">{children}</section>
    </main>
  );
}
