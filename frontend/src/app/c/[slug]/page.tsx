// The public Chat Page (/c/{slug}): a Customer sees the Business and its Services (FR-14).
import type { Metadata } from "next";
import { ChatPage } from "@/components/ChatPage";

export const metadata: Metadata = { title: "Chat · SevaDesk" };

// In Next.js 16, params is a Promise: await it to read the slug from the URL.
export default async function Page({ params }: PageProps<"/c/[slug]">) {
  const { slug } = await params;
  return <ChatPage slug={slug} />;
}
