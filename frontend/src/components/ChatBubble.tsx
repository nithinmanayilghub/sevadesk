// Chat bubbles (UX-DR7), shared by the Chat Page and the Inbox (story 4.4; moved from ChatPanel).
// - The Customer on the right in the brand color; the Agent, a team member, or the system on
//   the left on a card with a border.
// - A label above a reply says who wrote it: the team's name, or "SevaDesk assistant".
// Keep this light (NFR-6, the Chat Page loads it): plain elements, no icon sets.
import type { ReactNode } from "react";
import type { Sent } from "@/lib/chatPoll";

// Who wrote it, shown above the bubble. teamName: the Business name on the Chat Page; "Team"
// in the Inbox. (Users have no names yet: a later story adds them.)
export function authorLabel(authorType: string, teamName: string): string | undefined {
  if (authorType === "user") return teamName;
  if (authorType === "agent") return "SevaDesk assistant";
  return undefined;
}

export function Bubble({
  authorType,
  lang,
  body,
  label,
  sending = false,
  children,
}: {
  authorType: string;
  lang?: string;
  body: string;
  label?: string;
  sending?: boolean;
  children?: ReactNode;
}) {
  const mine = authorType === "customer";
  return (
    // lang="hi" on Hindi, so screen readers and fonts treat it as Hindi (UX-DR32).
    <li lang={lang === "hi" ? "hi" : undefined} className={`flex max-w-[85%] flex-col gap-1 ${mine ? "ml-auto" : "mr-auto"}`}>
      {label && <span className="text-xs text-muted-foreground">{label}</span>}
      <p
        className={`rounded-xl px-4 py-2 break-words whitespace-pre-wrap ${
          mine ? "bg-primary text-primary-foreground" : "border bg-card"
        } ${sending ? "opacity-70" : ""}`}
      >
        {body}
      </p>
      {children}
    </li>
  );
}

// One of this screen's own sends. A failed one shows "Not sent", and Retry if a retry can work.
export function SentBubble({
  item,
  authorType,
  label,
  onRetry,
}: {
  item: Sent;
  authorType: string;
  label?: string;
  onRetry: (clientMessageId: string, body: string) => void;
}) {
  return (
    <Bubble authorType={authorType} lang={item.message?.lang} body={item.body} label={label} sending={item.status === "sending"}>
      {item.status === "failed" && (
        <span className={`flex flex-col text-sm text-muted-foreground ${authorType === "customer" ? "items-end" : "items-start"}`}>
          <span className="flex items-center gap-1">
            <span>Not sent</span>
            {item.canRetry && (
              <>
                <span aria-hidden="true">·</span>
                {/* min-h-11 min-w-11: a 44 × 44 px target for a finger (UX-DR31). */}
                <button
                  type="button"
                  className="min-h-11 min-w-11 px-1 font-medium text-foreground underline focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
                  onClick={() => onRetry(item.clientMessageId, item.body)}
                >
                  Retry
                </button>
              </>
            )}
          </span>
          {item.reason && <span>{item.reason}</span>}
        </span>
      )}
    </Bubble>
  );
}
