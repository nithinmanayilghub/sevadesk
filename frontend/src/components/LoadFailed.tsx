// What a settings section shows when its first load fails: one alert and a Try again button.
// One place for this copy, so every page says the same thing (UX-DR25).
import { Button } from "@/components/ui/button";

export function LoadFailed({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="flex flex-col items-start gap-3">
      <p role="alert">Could not load. Please try again.</p>
      <Button onClick={onRetry}>Try again</Button>
    </div>
  );
}
