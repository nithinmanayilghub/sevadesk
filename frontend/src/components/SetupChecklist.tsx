"use client";
// The setup checklist on the Dashboard (story 3.3, FR-14): Add Services -> Set Working Hours
// -> Copy chat link. When both setup steps are done, the card turns emerald and the last
// step becomes a Copy button. Owners only (manage_setup); other Users see "Coming soon."
// until the Dashboard story builds the rest.
import { Check, Circle } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { CopyChatLinkButton } from "@/components/CopyChatLinkButton";
import { usePermissions } from "@/lib/permissions";

type SetupOut = components["schemas"]["SetupOut"];

function StepIcon({ done }: { done: boolean }) {
  return done ? (
    <Check aria-hidden className="size-5 text-brand" />
  ) : (
    <Circle aria-hidden className="size-5 text-muted-foreground" />
  );
}

function LinkStep({ href, label, done }: { href: string; label: string; done: boolean }) {
  return (
    <li className="flex min-h-11 items-center gap-3">
      <StepIcon done={done} />
      {/* The aria-label says "done" too: the check mark alone is only a picture. */}
      <Link
        href={href}
        aria-label={done ? `${label}, done` : label}
        className="font-medium underline-offset-4 hover:underline"
      >
        {label}
      </Link>
    </li>
  );
}

export function SetupChecklist() {
  const isOwner = usePermissions().includes("manage_setup");
  const [setup, setSetup] = useState<SetupOut | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    if (!isOwner) return;
    api
      .GET("/api/v1/setup")
      .then(({ data }) => (data ? setSetup(data) : setFailed(true)))
      .catch(() => setFailed(true));
  }, [isOwner]);

  if (!isOwner) return <p className="text-muted-foreground">Coming soon.</p>;
  // A load error hides the checklist without a message: the Dashboard is still useful without it.
  if (failed) return null;
  if (setup === null) {
    return (
      <div aria-busy="true" aria-label="Loading" className="h-40 w-full max-w-md animate-pulse rounded-lg bg-muted" />
    );
  }

  const ready = setup.has_services && setup.has_working_hours;
  return (
    <section
      aria-label="Set up your chat link"
      className={`flex w-full max-w-md flex-col gap-3 rounded-lg border p-6 ${ready ? "border-brand bg-brand-soft" : "bg-card"}`}
    >
      <h2 className="text-lg font-semibold">Set up your chat link</h2>
      <ol className="flex flex-col gap-1">
        <LinkStep href="/app/settings/services" label="Add Services" done={setup.has_services} />
        <LinkStep href="/app/settings/hours" label="Set Working Hours" done={setup.has_working_hours} />
        <li className="flex min-h-11 items-center gap-3">
          <StepIcon done={false} />
          {ready ? (
            <CopyChatLinkButton slug={setup.chat_slug} label="Copy chat link" />
          ) : (
            <span className="text-muted-foreground">Copy chat link</span>
          )}
        </li>
      </ol>
    </section>
  );
}
