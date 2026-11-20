"use client";
// The Copy button for the public chat link (story 3.3, FR-14). Used on Settings → Chat link
// and on the Dashboard checklist. It owns its fallback: when the browser cannot copy, it
// shows the link in a box that selects itself on tap, so the Owner can copy it by hand.
import { useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

// The full link a Customer opens, e.g. https://sevadesk.in/c/ravi-k7m2qx.
export function chatPageUrl(slug: string): string {
  return `${window.location.origin}/c/${slug}`;
}

export function CopyChatLinkButton({ slug, label }: { slug: string; label: string }) {
  const id = useId();
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");

  async function copy() {
    try {
      // Inside the try: with no clipboard at all (old browser, http page), this line throws too.
      await navigator.clipboard.writeText(chatPageUrl(slug));
      setState("copied");
    } catch {
      setState("failed");
    }
  }

  return (
    <div className="flex flex-col items-start gap-2">
      <Button type="button" onClick={copy}>
        {state === "copied" ? "Copied" : label}
      </Button>
      {/* aria-live: a screen reader reads out "Link copied" or the fallback when it appears.
          The new button text alone is usually not read out. */}
      <div aria-live="polite" className="w-full">
        {state === "copied" && <span className="sr-only">Link copied</span>}
        {state === "failed" && (
          <div className="flex flex-col gap-2">
            <p className="text-sm text-muted-foreground">Could not copy. Select the link and copy it.</p>
            <Label htmlFor={`${id}-link`} className="sr-only">
              Chat link
            </Label>
            <Input id={`${id}-link`} readOnly value={chatPageUrl(slug)} onFocus={(e) => e.target.select()} />
          </div>
        )}
      </div>
    </div>
  );
}
