// Tests for the money helpers: paise (the API's whole numbers) <-> rupees on screen (UX-DR4).
import { expect, test } from "vitest";
import { formatRupees, paiseToRupeesText, rupeesToPaise } from "./money";

test("formatRupees uses Indian grouping and drops .00", () => {
  expect(formatRupees(149900)).toBe("₹1,499");
  expect(formatRupees(10000000)).toBe("₹1,00,000");
  expect(formatRupees(100)).toBe("₹1");
});

test("formatRupees shows two decimals when there are paise", () => {
  expect(formatRupees(49950)).toBe("₹499.50");
});

test("paiseToRupeesText gives plain text for an input box", () => {
  expect(paiseToRupeesText(149900)).toBe("1499");
  expect(paiseToRupeesText(49950)).toBe("499.50");
});

test("rupeesToPaise reads what an Owner types", () => {
  expect(rupeesToPaise("499")).toBe(49900);
  expect(rupeesToPaise("1,499")).toBe(149900);
  expect(rupeesToPaise("₹1,499")).toBe(149900);
  expect(rupeesToPaise(" 499.50 ")).toBe(49950);
  expect(rupeesToPaise("0.1")).toBe(10);
});

test("rupeesToPaise gives null for anything that is not a Price", () => {
  for (const text of ["", "abc", "4.999", "-5"]) expect(rupeesToPaise(text)).toBeNull();
});

test("an edit form round trip keeps the same paise", () => {
  for (const paise of [149900, 49950]) expect(rupeesToPaise(paiseToRupeesText(paise))).toBe(paise);
});
