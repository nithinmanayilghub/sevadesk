// Shown instead of a page the User's Role may not open, e.g. a Technician who types
// /app/inbox (UX-DR27). The nav stays around it, so they can go to a page they may use.
export function NoAccess() {
  return (
    <main className="flex flex-col gap-2 px-page-x py-6">
      <h1 className="text-2xl font-semibold tracking-tight">You don&apos;t have access to this page.</h1>
    </main>
  );
}
