// The /login page: a User starts a session here (FR-8).
import type { Metadata } from "next";
import { LoginForm } from "@/components/LoginForm";

export const metadata: Metadata = { title: "Log in · SevaDesk" };

export default function LoginPage() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 px-page-x py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Log in to SevaDesk</h1>
      <LoginForm />
    </main>
  );
}
