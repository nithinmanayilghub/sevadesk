"use client";
// The public Chat Page (/c/{slug}, story 3.3, FR-14). A Customer opens the Owner's link and
// sees the Business name, its active Services with "from ₹" Prices, and the DPDP notice.
// No login. The chat itself comes in Epic 4.
//
// Keep this page light (NFR-6: first load at most 200 KB gzip, checked in CI): Customers use
// cheap phones on slow data. Do not import icon sets or other big libraries here.
import { api } from "@/api/client";
import type { components } from "@/api/schema";
import { formatRupees } from "@/lib/money";
import { formatDuration } from "@/lib/time";
import { useLoad } from "@/lib/useLoad";

type ChatPageOut = components["schemas"]["ChatPageOut"];

export function ChatPage({ slug }: { slug: string }) {
  // A new slug loads again (useLoad's inputs). A 404 means no Business has this slug.
  const state = useLoad(() => api.GET("/api/v1/chat/{chat_slug}", { params: { path: { chat_slug: slug } } }), [slug]);

  return (
    // max-w-md + px-page-x: one narrow column that fits a 360 px phone.
    <main className="mx-auto flex w-full max-w-md flex-col gap-6 px-page-x py-8">
      {state.status === "loading" && (
        // Skeleton while we wait (UX-DR25).
        <div aria-busy="true" aria-label="Loading" className="flex flex-col gap-3">
          <div className="h-8 w-2/3 animate-pulse rounded-lg bg-muted" />
          <div className="h-24 animate-pulse rounded-lg bg-muted" />
        </div>
      )}

      {state.status === "not_found" && (
        <div className="flex flex-col gap-2">
          <h1 className="text-2xl font-semibold tracking-tight">Chat page not found</h1>
          <p className="text-muted-foreground">Check the link and try again.</p>
        </div>
      )}

      {state.status === "failed" && (
        <div className="flex flex-col items-start gap-3">
          <p role="alert">Could not load. Please try again.</p>
          {/* A plain <button>, not ui/button: that one pulls in radix-ui and costs ~10 KB here.
              Same look as the default ui/button. */}
          <button
            type="button"
            className="inline-flex h-11 items-center justify-center rounded-full bg-primary px-5 text-sm font-medium text-primary-foreground hover:bg-primary/80 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
            onClick={state.reload}
          >
            Try again
          </button>
        </div>
      )}

      {state.status === "ready" && <Ready page={state.data} />}
    </main>
  );
}

function Ready({ page }: { page: ChatPageOut }) {
  return (
    <>
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-semibold tracking-tight">{page.business_name}</h1>
        {!page.taking_requests && <p className="text-muted-foreground">Not taking requests yet</p>}
      </div>

      {/* No Services yet: no empty box. "Not taking requests yet" above already says why. */}
      {page.services.length > 0 && (
        <section aria-label="Services & prices" className="flex flex-col gap-3 rounded-lg border bg-card p-4">
          <h2 className="text-lg font-semibold">Services & prices</h2>
          <ul className="flex flex-col divide-y">
            {/* Keyed by position: two Services may share a name, and the page gets no ids. */}
            {page.services.map((service, index) => (
              <li key={index} className="flex min-h-11 items-center justify-between gap-3 py-2">
                <span className="flex flex-col">
                  <span className="font-medium">{service.name}</span>
                  <span className="text-sm text-muted-foreground">{formatDuration(service.duration_minutes)}</span>
                </span>
                <span className="font-medium whitespace-nowrap">from {formatRupees(service.price_paise)}</span>
              </li>
            ))}
          </ul>
          <p className="text-sm text-muted-foreground">Final price after inspection. Parts extra.</p>
        </section>
      )}

      {/* The DPDP notice (India's data protection law): always shown, before any chat. */}
      <p className="text-sm text-muted-foreground">
        We collect your name, phone, and address only to book your job. {page.business_name} can delete them on
        request.
      </p>
    </>
  );
}
