// One open Conversation (/app/inbox/{id}, story 4.4). On mobile it fills the screen, so it has
// a back link to the list; from lg the list is beside it (see ../layout.tsx).
import type { Metadata } from "next";
import Link from "next/link";
import { ConversationNotFound, ConversationView } from "@/components/ConversationView";

export const metadata: Metadata = { title: "Conversation · SevaDesk" };

// The shape of a UUID. Anything else is not one of our ids: show "not found" here, because the
// API would answer 422 (bad input), and that would show as a load error.
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// In Next.js 16, params is a Promise: await it to read the id from the URL.
export default async function Page({ params }: PageProps<"/app/inbox/[conversationId]">) {
  const { conversationId } = await params;
  return (
    <div className="flex flex-col gap-2">
      <Link href="/app/inbox" className="inline-flex min-h-11 items-center font-medium lg:hidden">
        ← Inbox
      </Link>
      {/* key: a new id starts a fresh view (no cursor or sends carried over from the last one). */}
      {UUID.test(conversationId) ? (
        <ConversationView key={conversationId} conversationId={conversationId} />
      ) : (
        <ConversationNotFound />
      )}
    </div>
  );
}
