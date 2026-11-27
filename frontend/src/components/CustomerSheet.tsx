"use client";
// CustomerSheet (story 4.5, NFR-8, UX-DR28): the Customer detail sheet, opened from the
// Conversation header. Owner only: the button shows only with "manage_customer_data". The
// backend checks the Role again on every request (AD-5); hiding the button is only for show.
// - the sheet: when this Customer first wrote, and how many chats and Messages they have
// - "Delete customer": a confirm dialog that names what goes and says it cannot be undone.
//   After the delete, back to the Inbox: this chat no longer exists.
// No Bookings yet: Epic 5 adds them to the dialog text.
import { useRouter } from "next/navigation";
import { useState } from "react";
import { api } from "@/api/client";
import {
  AlertDialog,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { usePermissions } from "@/lib/permissions";
import { useLoad } from "@/lib/useLoad";
import { LoadFailed } from "./LoadFailed";

// "1 conversation", "3 messages"
function count(n: number, word: string): string {
  return `${n} ${word}${n === 1 ? "" : "s"}`;
}

// "20 Nov 2026", in the viewer's own time zone.
function day(iso: string): string {
  return new Intl.DateTimeFormat("en-IN", { day: "numeric", month: "short", year: "numeric" }).format(new Date(iso));
}

export function CustomerSheet({ conversationId }: { conversationId: string }) {
  const mayManage = usePermissions().includes("manage_customer_data");
  if (!mayManage) return null;
  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" className="min-h-11">
          Customer
        </Button>
      </SheetTrigger>
      <SheetContent>
        <SheetHeader>
          <SheetTitle>Customer</SheetTitle>
          <SheetDescription>Details and data deletion for this customer.</SheetDescription>
        </SheetHeader>
        {/* Only rendered while the sheet is open, so the data loads when the Owner opens it. */}
        <CustomerDetails conversationId={conversationId} />
      </SheetContent>
    </Sheet>
  );
}

function CustomerDetails({ conversationId }: { conversationId: string }) {
  const router = useRouter();
  const state = useLoad(
    () =>
      api.GET("/api/v1/inbox/conversations/{conversation_id}/customer", {
        params: { path: { conversation_id: conversationId } },
      }),
    [conversationId],
  );
  const [busy, setBusy] = useState(false);
  const [failed, setFailed] = useState(false);

  if (state.status === "loading") {
    return <div aria-busy="true" aria-label="Loading customer" className="mx-4 h-24 animate-pulse rounded-xl bg-muted" />;
  }
  if (state.status === "not_found") return <p className="px-4">This customer was not found.</p>;
  if (state.status === "failed") return <LoadFailed onRetry={state.reload} />;

  const customer = state.data;

  async function remove() {
    if (busy) return;
    setBusy(true);
    setFailed(false);
    try {
      const { response } = await api.DELETE("/api/v1/inbox/customers/{customer_id}", {
        params: { path: { customer_id: customer.customer_id } },
      });
      if (response.ok) {
        router.push("/app/inbox"); // the Inbox list drops this row on its next poll
        return;
      }
      setFailed(true);
    } catch {
      setFailed(true); // network down
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="flex flex-col gap-4 px-4">
      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Customer since</dt>
        <dd>{day(customer.created_at)}</dd>
        <dt className="text-muted-foreground">Conversations</dt>
        <dd>{customer.conversation_count}</dd>
        <dt className="text-muted-foreground">Messages</dt>
        <dd>{customer.message_count}</dd>
      </dl>

      <AlertDialog>
        <AlertDialogTrigger asChild>
          <Button variant="destructive" className="min-h-11 self-start">
            Delete customer
          </Button>
        </AlertDialogTrigger>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete this customer?</AlertDialogTitle>
            <AlertDialogDescription>
              This deletes their {count(customer.conversation_count, "conversation")} and{" "}
              {count(customer.message_count, "message")}. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          {failed && <p role="alert">Could not delete the customer. Try again.</p>}
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            {/* A plain button, not AlertDialogAction: that one closes the dialog at once,
                and after a failed delete the Owner must still see the alert. */}
            <Button variant="destructive" aria-disabled={busy} onClick={() => void remove()}>
              Delete customer
            </Button>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
