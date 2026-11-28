// The Calendar (/app/calendar): Technician-only Users land here (UX-DR18). The day and week
// views come in story 5.4. Story 5.2 adds "New booking" for a Customer who phoned (FR-27);
// it shows only for Owner and Staff (BookingSheet checks the permission).
import type { Metadata } from "next";
import { BookingSheet } from "@/components/BookingSheet";

export const metadata: Metadata = { title: "Calendar · SevaDesk" };

export default function Page() {
  return (
    <main className="flex flex-col gap-2 px-page-x py-6">
      <div className="flex items-center justify-between gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">Calendar</h1>
        <BookingSheet />
      </div>
      <p className="text-muted-foreground">The day and week views are coming soon.</p>
    </main>
  );
}
