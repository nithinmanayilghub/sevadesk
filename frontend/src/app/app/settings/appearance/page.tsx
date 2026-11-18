// Settings → Appearance (/app/settings/appearance): open to every Role, so no row in access.ts.
import type { Metadata } from "next";
import { AppearanceSettings } from "@/components/AppearanceSettings";

export const metadata: Metadata = { title: "Appearance · SevaDesk" };

export default function AppearancePage() {
  return (
    <main className="flex flex-col items-start gap-4 px-page-x py-6">
      <h1 className="text-2xl font-semibold tracking-tight">Appearance</h1>
      <AppearanceSettings />
    </main>
  );
}
