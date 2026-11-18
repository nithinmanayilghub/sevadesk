// Settings → Team (/app/settings/team): Owner only (access.ts; the backend checks again).
import type { Metadata } from "next";
import { TeamSettings } from "@/components/TeamSettings";

export const metadata: Metadata = { title: "Team · SevaDesk" };

export default function TeamPage() {
  return (
    <main className="flex flex-col items-start gap-4 px-page-x py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Team</h1>
      <TeamSettings />
    </main>
  );
}
