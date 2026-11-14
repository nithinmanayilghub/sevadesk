// The /signup page: a new Owner creates their Business here (FR-7).
import type { Metadata } from "next";
import Link from "next/link";
import { SignupForm } from "@/components/SignupForm";

export const metadata: Metadata = { title: "Sign up · SevaDesk" };

export default function SignupPage() {
  return (
    <main className="mx-auto flex w-full max-w-md flex-1 flex-col justify-center gap-6 px-page-x py-10">
      <h1 className="text-2xl font-semibold tracking-tight">Create your SevaDesk Business</h1>
      <SignupForm />
      <p className="text-sm text-muted-foreground">
        Already have an account?{" "}
        <Link href="/login" className="font-medium text-foreground underline underline-offset-4">
          Log in
        </Link>
      </p>
    </main>
  );
}
