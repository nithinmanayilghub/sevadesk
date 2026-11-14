"use client";
// The app shell (UX-DR16, UX-DR19): a bottom tab bar on mobile, a left sidebar from 1024px
// (Tailwind "lg"). Both hold the same items; CSS shows one of them. Solid surfaces only.
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { navItems, type NavItem } from "@/lib/nav";
import { cn } from "@/lib/utils";

function isCurrent(pathname: string, href: string): boolean {
  // "/app" is the Dashboard only; the others also match their sub-pages (e.g. /app/inbox/123).
  return href === "/app" ? pathname === "/app" : pathname === href || pathname.startsWith(`${href}/`);
}

function NavLinks({ items, pathname, vertical }: { items: NavItem[]; pathname: string; vertical: boolean }) {
  return items.map(({ href, label, icon: Icon }) => {
    const current = isCurrent(pathname, href);
    return (
      <Link
        key={href}
        href={href}
        aria-current={current ? "page" : undefined}
        className={cn(
          // min-h-11 = 44px: a tap target big enough for a thumb.
          "flex min-h-11 items-center gap-3 rounded-md px-3 text-sm font-medium",
          vertical ? "w-full" : "flex-1 flex-col justify-center gap-1 text-xs",
          current ? "text-primary" : "text-muted-foreground hover:text-foreground",
        )}
      >
        <Icon className="size-5" aria-hidden="true" />
        {label}
      </Link>
    );
  });
}

export function AppShell({ roles, children }: { roles: string[]; children: ReactNode }) {
  const pathname = usePathname();
  const items = navItems(roles);
  return (
    <div className="flex min-h-full flex-1">
      <nav aria-label="Sidebar" className="hidden w-60 shrink-0 flex-col gap-1 border-r bg-card p-4 lg:flex">
        <NavLinks items={items} pathname={pathname} vertical />
      </nav>
      {/* pb-20: room at the bottom so the fixed tab bar hides nothing on mobile. */}
      <div className="flex flex-1 flex-col pb-20 lg:pb-0">{children}</div>
      <nav aria-label="Main" className="fixed inset-x-0 bottom-0 flex border-t bg-card px-2 py-1 lg:hidden">
        <NavLinks items={items} pathname={pathname} vertical={false} />
      </nav>
    </div>
  );
}
