"use client";
// Settings → Chat link (story 3.3, FR-14): the Owner's public chat link, to copy and share.
import { useCallback, useEffect, useState } from "react";
import { api } from "@/api/client";
import { Button } from "@/components/ui/button";
import { chatPageUrl, CopyChatLinkButton } from "@/components/CopyChatLinkButton";

export function ChatLinkSettings() {
  const [slug, setSlug] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  const load = useCallback(() => {
    api
      .GET("/api/v1/setup")
      .then(({ data }) => {
        if (!data) return setFailed(true);
        setSlug(data.chat_slug);
      })
      .catch(() => setFailed(true));
  }, []);

  useEffect(load, [load]);

  if (failed) {
    return (
      <div className="flex flex-col items-start gap-3">
        <p role="alert">Could not load. Please try again.</p>
        <Button
          onClick={() => {
            setFailed(false);
            load();
          }}
        >
          Try again
        </Button>
      </div>
    );
  }

  return (
    <section aria-label="Chat link" className="flex w-full max-w-2xl flex-col gap-4 rounded-lg border bg-card p-6">
      <p className="text-sm text-muted-foreground">Share this link with Customers. It opens your Chat Page.</p>
      {slug === null ? (
        // Skeleton while we wait (UX-DR25).
        <div aria-busy="true" aria-label="Loading" className="h-11 animate-pulse rounded-lg bg-muted" />
      ) : (
        <>
          {/* break-all: a long link wraps on a phone instead of pushing the page sideways. */}
          <p className="font-medium break-all">{chatPageUrl(slug)}</p>
          <CopyChatLinkButton slug={slug} label="Copy link" />
        </>
      )}
    </section>
  );
}
