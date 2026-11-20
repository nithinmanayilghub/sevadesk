// The backend owns every validation rule (UX-DR33). When it refuses a form, its error lists
// one message per field. This keeps only the fields this form shows, so each message can sit
// under its own box. An empty result means "nothing to show under a field": the form then
// shows the backend's general message instead.
import type { components } from "@/api/schema";

type ErrorEnvelope = components["schemas"]["ErrorEnvelope"];

export function errorsForFields<F extends string>(
  error: ErrorEnvelope | undefined,
  fields: readonly F[],
): Partial<Record<F, string>> {
  const found: Partial<Record<F, string>> = {};
  for (const item of error?.error.fields ?? []) {
    if ((fields as readonly string[]).includes(item.field)) found[item.field as F] = item.message;
  }
  return found;
}
