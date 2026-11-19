// Settings → Working Hours (/app/settings/hours): Owner only (lib/pages.ts; the backend checks again).
import type { Metadata } from "next";
import { ClosedDaysSettings } from "@/components/ClosedDaysSettings";
import { WorkingHoursForm } from "@/components/WorkingHoursForm";

export const metadata: Metadata = { title: "Working Hours · SevaDesk" };

export default function WorkingHoursPage() {
  return (
    <main className="flex flex-col items-start gap-4 px-page-x py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Working Hours</h1>
      <WorkingHoursForm />
      <ClosedDaysSettings />
    </main>
  );
}
