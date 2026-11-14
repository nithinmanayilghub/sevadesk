// The app's main nav items per Role (UX-DR16). This only chooses what to SHOW;
// the backend still checks every Role on every request (AD-5).
import { CalendarDays, Ellipsis, Inbox, LayoutDashboard, type LucideIcon } from "lucide-react";

export type NavItem = { href: string; label: string; icon: LucideIcon };

const DASHBOARD: NavItem = { href: "/app", label: "Dashboard", icon: LayoutDashboard };
const INBOX: NavItem = { href: "/app/inbox", label: "Inbox", icon: Inbox };
const CALENDAR: NavItem = { href: "/app/calendar", label: "Calendar", icon: CalendarDays };
const MORE: NavItem = { href: "/app/more", label: "More", icon: Ellipsis };

export function navItems(roles: string[]): NavItem[] {
  const seesInbox = roles.includes("owner") || roles.includes("staff");
  return seesInbox ? [DASHBOARD, INBOX, CALENDAR, MORE] : [CALENDAR, MORE];
}
