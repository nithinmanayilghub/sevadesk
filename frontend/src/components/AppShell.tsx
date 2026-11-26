"use client";
// The app shell (UX-DR16, UX-DR19): a bottom tab bar on mobile, a left sidebar from 1024px
// (Tailwind "lg"). Both hold the same items; CSS shows one of them. Solid surfaces only.
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { isUnder, tabs, type Permission, type Tab } from "@/lib/pages";
import { cn } from "@/lib/utils";

// The red Needs Human count on the Inbox tab (story 4.3, UX-DR16). The visible number is
// hidden from screen readers; they read one sentence instead: "Inbox, 3 need a human".
function CountPill({ count, vertical }: { count: number; vertical: boolean }) {
  return (
    <>
      <span
        aria-hidden="true"
        className={cn(
          "min-w-5 rounded-full bg-status-handoff px-1.5 text-center text-xs font-semibold text-status-handoff-foreground",
          vertical ? "ml-auto" : "absolute top-0.5 left-1/2 ml-2",
        )}
      >
        {count > 99 ? "99+" : count}
      </span>
      <span className="sr-only">, {count} need a human</span>
    </>
  );
}

function NavLinks({
  items,
  pathname,
  vertical,
  inboxCount,
}: {
  items: Tab[];
  pathname: string;
  vertical: boolean;
  inboxCount: number;
}) {
  return items.map(({ href, label, icon: Icon, alsoActiveUnder = [] }) => {
    const current = [href, ...alsoActiveUnder].some((path) => isUnder(pathname, path));
    return (
      <Link
        key={href}
        href={href}
        aria-current={current ? "page" : undefined}
        className={cn(
          // min-h-11 = 44px: a tap target big enough for a thumb.
          "relative flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium",
          vertical ? "w-full" : "flex-1 flex-col justify-center gap-1 text-xs",
          current ? "text-primary" : "text-muted-foreground hover:text-foreground",
        )}
      >
        <Icon className="size-5" aria-hidden="true" />
        {label}
        {href === "/app/inbox" && inboxCount > 0 && <CountPill count={inboxCount} vertical={vertical} />}
      </Link>
    );
  });
}

export function AppShell({
  permissions,
  inboxCount = 0,
  children,
}: {
  permissions: Permission[];
  inboxCount?: number; // Needs Human Conversations: a red number on the Inbox tab when > 0
  children: ReactNode;
}) {
  const pathname = usePathname();
  const items = tabs(permissions);
  return (
    <div className="flex min-h-full flex-1">
      <nav aria-label="Sidebar" className="hidden w-60 shrink-0 flex-col gap-1 border-r bg-card p-4 lg:flex">
        <NavLinks items={items} pathname={pathname} vertical inboxCount={inboxCount} />
      </nav>
      {/* pb-20: room at the bottom so the fixed tab bar hides nothing on mobile.
          min-w-0: lets the page shrink to the screen, so long text never scrolls sideways. */}
      <div className="flex min-w-0 flex-1 flex-col pb-20 lg:pb-0">{children}</div>
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 flex border-t bg-card px-2 py-1 lg:hidden">
        <NavLinks items={items} pathname={pathname} vertical={false} inboxCount={inboxCount} />
      </nav>
    </div>
  );
}
