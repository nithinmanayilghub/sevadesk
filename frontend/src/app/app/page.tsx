// The Dashboard (/app): Owner and Staff land here (UX-DR18). For now it holds only the
// setup checklist (story 3.3); other Users see "Coming soon." until the Dashboard story.
import type { Metadata } from "next";
import { SetupChecklist } from "@/components/SetupChecklist";

export const metadata: Metadata = { title: "Dashboard · SevaDesk" };

export default function Page() {
  return (
    <main className="flex flex-col gap-4 px-page-x py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Dashboard</h1>
      <SetupChecklist />
    </main>
  );
}
