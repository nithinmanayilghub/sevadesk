"use client";
// Settings → Chat link (story 3.3, FR-14): the Owner's public chat link, to copy and share.
import { api } from "@/api/client";
import { LoadFailed } from "@/components/LoadFailed";
import { chatPageUrl, CopyChatLinkButton } from "@/components/CopyChatLinkButton";
import { useLoad } from "@/lib/useLoad";

export function ChatLinkSettings() {
  const setup = useLoad(() => api.GET("/api/v1/setup"), []);

  if (setup.status === "failed" || setup.status === "not_found") return <LoadFailed onRetry={setup.reload} />;

  return (
    <section aria-label="Chat link" className="flex w-full max-w-2xl flex-col gap-4 rounded-lg border bg-card p-6">
      <p className="text-sm text-muted-foreground">Share this link with Customers. It opens your Chat Page.</p>
      {setup.status === "loading" ? (
        // Skeleton while we wait (UX-DR25).
        <div aria-busy="true" aria-label="Loading" className="h-11 animate-pulse rounded-lg bg-muted" />
      ) : (
        <>
          {/* break-all: a long link wraps on a phone instead of pushing the page sideways. */}
          <p className="font-medium break-all">{chatPageUrl(setup.data.chat_slug)}</p>
          <CopyChatLinkButton slug={setup.data.chat_slug} label="Copy link" />
        </>
      )}
    </section>
  );
}
