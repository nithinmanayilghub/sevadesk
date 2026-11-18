// The app's main nav items (UX-DR16). A User sees only the pages they may open (UX-DR27).
// This only chooses what to SHOW; the backend still checks every Role on every request (AD-5).
import { CalendarDays, Ellipsis, Inbox, LayoutDashboard, type LucideIcon } from "lucide-react";
import { canOpen, type Permission } from "@/lib/access";

// alsoActiveUnder: other pages where this item counts as the current one (e.g. More on
// /app/settings/*, because the settings pages are opened from More).
export type NavItem = { href: string; label: string; icon: LucideIcon; alsoActiveUnder?: string[] };

const ITEMS: NavItem[] = [
  { href: "/app", label: "Dashboard", icon: LayoutDashboard },
  { href: "/app/inbox", label: "Inbox", icon: Inbox },
  { href: "/app/calendar", label: "Calendar", icon: CalendarDays },
  { href: "/app/more", label: "More", icon: Ellipsis, alsoActiveUnder: ["/app/settings"] },
];

export function navItems(permissions: Permission[]): NavItem[] {
  return ITEMS.filter((item) => canOpen(item.href, permissions));
}
