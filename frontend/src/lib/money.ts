// Money helpers (UX-DR4, AR-5). The API sends and takes whole paise (₹1 = 100 paise), never
// floats. These turn paise into text for the screen, and an Owner's typed text into paise.

// "₹1,499" or "₹1,00,000": the en-IN locale groups digits the Indian way (lakh, crore).
export function formatRupees(paise: number): string {
  const digits = paise % 100 === 0 ? 0 : 2; // no ".00" for whole rupees
  return new Intl.NumberFormat("en-IN", {
    style: "currency",
    currency: "INR",
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(paise / 100);
}

// The text for an input box: no ₹ sign and no commas, e.g. "1499" or "499.50".
// It fills the edit form, so rupeesToPaise reads it back to the same paise.
export function paiseToRupeesText(paise: number): string {
  const rupees = Math.trunc(paise / 100);
  const rest = paise % 100;
  return rest === 0 ? String(rupees) : `${rupees}.${String(rest).padStart(2, "0")}`;
}

// What the Owner typed -> paise. "1,499" -> 149900, "499.50" -> 49950.
// Anything that is not a Price (empty, letters, 3 decimals, minus) -> null. The form sends
// null, and the backend answers with its own message next to the field: it owns the rules.
export function rupeesToPaise(text: string): number | null {
  const clean = text.replace(/[,\s]/g, "").replace(/^₹/, "");
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return null;
  const paise = Math.round(Number(clean) * 100); // round: 0.1 * 100 is 10.000000000000002 in floats
  // A huge entry (20+ digits) cannot be held exactly, and JSON would send it as "1e+22".
  return Number.isSafeInteger(paise) ? paise : null;
}
