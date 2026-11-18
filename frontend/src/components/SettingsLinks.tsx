"use client";
// Links to the settings pages, on the More page. Each one shows only if this User may open it.
// The list lives in lib/pages.ts: a new settings page = one row there (place: "settings").
import Link from "next/link";
import { settingsLinks } from "@/lib/pages";
import { usePermissions } from "@/lib/permissions";

export function SettingsLinks() {
  const permissions = usePermissions();
  const links = settingsLinks(permissions);
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
