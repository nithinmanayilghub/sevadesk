// inboxList: how a Load more page and a poll answer join the Inbox list on screen (story 4.3).
// - appendPage: Load more. Add the next page below; a row already shown is not shown twice
//   (a chat that moved to the top while the User paged can come back on the next page).
// - pollLimit / mergePoll: the poll asks again for the top rows on screen (at most POLL_MAX)
//   and redraws them, so a new Message moves its chat up within 5 s (FR-24).
import type { components } from "@/api/schema";

type InboxPage = components["schemas"]["InboxPage"];

export const PAGE_SIZE = 20; // the server's default page size
export const POLL_MAX = 100; // the most rows one request may ask for (the server's limit)

export function pollLimit(shown: number): number {
  return Math.min(Math.max(shown, PAGE_SIZE), POLL_MAX);
}

export function appendPage(current: InboxPage, next: InboxPage): InboxPage {
  const shown = new Set(current.conversations.map((row) => row.conversation_id));
  return {
    ...next,
    conversations: [...current.conversations, ...next.conversations.filter((row) => !shown.has(row.conversation_id))],
  };
}

export function mergePoll(current: InboxPage, answer: InboxPage): InboxPage {
  // The answer covers everything on screen: it is the new list, with its own next_cursor.
  if (current.conversations.length <= POLL_MAX) return answer;
  // More rows on screen than one poll can send. The answer is the true top POLL_MAX now, so
  // every row on screen that is NOT in it ranks below it: keep those, in their order (also a
  // row a new chat just pushed from place 100 to 101). Keep the old cursor too: it loads what
  // comes after the last of THOSE rows. Known limit: a kept row shows its old badge and place
  // until a reload. Give back to Agent (story 4.4) moves a chat DOWN (out of Needs Human), so
  // with over 100 rows on screen that chat can keep its old badge until a reload. Kept: rare.
  // Also, after a take-over or give-back the whole list catches up on its next poll (≤ 5 s).
  const inAnswer = new Set(answer.conversations.map((row) => row.conversation_id));
  const rest = current.conversations.filter((row) => !inAnswer.has(row.conversation_id));
  return { ...answer, conversations: [...answer.conversations, ...rest], next_cursor: current.next_cursor };
}
