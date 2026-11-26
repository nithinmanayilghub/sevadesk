// A Conversation's status badge (UX-DR6): a pill with a label AND an icon, so the meaning
// never depends on color alone. One row per Conversation state (AD-10); a new state that is
// not in this table is a type error. "Booking Request" and "Expired" come with Epic 5.
import { Bot, CircleCheck, Hand, type LucideIcon } from "lucide-react";
import type { components } from "@/api/schema";
import { cn } from "@/lib/utils";

type State = components["schemas"]["InboxRow"]["state"];

const BADGES: Record<State, { label: string; icon: LucideIcon; className: string }> = {
  agent: { label: "Agent", icon: Bot, className: "bg-brand-soft text-brand" },
  handoff: { label: "Needs Human", icon: Hand, className: "bg-status-handoff/10 text-status-handoff" },
  closed: { label: "Closed", icon: CircleCheck, className: "bg-muted text-muted-foreground" },
};

export function StatusBadge({ state }: { state: State }) {
  const { label, icon: Icon, className } = BADGES[state];
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-xs font-medium", className)}>
      <Icon className="size-3.5" aria-hidden="true" />
      {label}
    </span>
  );
}
