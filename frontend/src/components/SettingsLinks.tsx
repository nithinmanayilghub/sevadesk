"use client";
// Links to the settings pages, on the More page. Each one shows only if this User may open it.
// More settings pages (Services, Working Hours, Chat link) add a row in their story.
// Appearance has no rule in access.ts, so every Role sees it.
import Link from "next/link";
import { canOpen } from "@/lib/access";
import { usePermissions } from "@/lib/permissions";

const SETTINGS = [
  { href: "/app/settings/team", label: "Team" },
  { href: "/app/settings/appearance", label: "Appearance" },
];

export function SettingsLinks() {
  const permissions = usePermissions();
  const links = SETTINGS.filter(({ href }) => canOpen(href, permissions));
  if (links.length === 0) return null;
  return (
    <nav aria-label="Settings" className="flex w-full max-w-md flex-col gap-1">
      {links.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          // min-h-11 = 44px: a tap target big enough for a thumb.
          className="flex min-h-11 items-center rounded-md border bg-card px-4 text-sm font-medium hover:bg-muted"
        >
          {label}
        </Link>
      ))}
    </nav>
  );
}
