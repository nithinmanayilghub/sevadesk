// The /invite/{token} page: an invited person sets a password and joins the Business (FR-9).
// referrer "no-referrer": links clicked here never send this URL (with its secret token)
// to another site in the Referer header.
import type { Metadata } from "next";
import { AcceptInviteForm } from "@/components/AcceptInviteForm";

export const metadata: Metadata = { title: "Join · SevaDesk", referrer: "no-referrer" };

// In Next.js 16, params is a Promise: await it to read the token from the URL.
export default async function InvitePage({ params }: PageProps<"/invite/[token]">) {
  const { token } = await params;
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 px-page-x py-10">
      <AcceptInviteForm token={token} />
    </main>
  );
}
