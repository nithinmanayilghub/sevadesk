// The pill button look of the default ui/button, for the public Chat Page (/c/{slug}).
// Plain <button> + these classes, because ui/button pulls in radix-ui (~10 KB) and the
// Chat Page must stay under 200 KB on first load (NFR-6).
export const PILL_BUTTON =
  "inline-flex h-11 items-center justify-center rounded-full bg-primary px-5 text-sm font-medium text-primary-foreground hover:bg-primary/80 focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none disabled:opacity-50";
