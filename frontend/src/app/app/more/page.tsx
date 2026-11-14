// The More page (/app/more): settings links come in later stories; log out lives here now.
import type { Metadata } from "next";
import { LogoutButton } from "@/components/LogoutButton";

export const metadata: Metadata = { title: "More · SevaDesk" };

export default function MorePage() {
  return (
    <main className="flex flex-col items-start gap-4 px-page-x py-6">
      <h1 className="text-2xl font-semibold tracking-tight">More</h1>
      <LogoutButton />
    </main>
  );
}
