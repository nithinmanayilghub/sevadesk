// Settings → Chat link (/app/settings/chat-link): Owner only (lib/pages.ts; the backend checks again).
import type { Metadata } from "next";
import { ChatLinkSettings } from "@/components/ChatLinkSettings";

export const metadata: Metadata = { title: "Chat link · SevaDesk" };

export default function ChatLinkPage() {
  return (
    <main className="flex flex-col items-start gap-4 px-page-x py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Chat link</h1>
      <ChatLinkSettings />
    </main>
  );
}
