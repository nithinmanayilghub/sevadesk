// Tests for errorsForFields: the backend's field errors, kept only for the fields a form shows.
import { expect, test } from "vitest";
import { errorsForFields } from "./errorsForFields";

const FIELDS = ["email", "password"] as const;

function envelope(fields: { field: string; message: string }[] | null) {
  return { error: { code: "validation_error", message: "Some fields need fixing.", fields } };
}

test("keeps the messages for this form's fields", () => {
  const error = envelope([
    { field: "email", message: "Enter a valid email." },
    { field: "password", message: "Use at least 12 characters." },
  ]);
  expect(errorsForFields(error, FIELDS)).toEqual({
    email: "Enter a valid email.",
    password: "Use at least 12 characters.",
  });
});

test("drops fields this form does not show", () => {
  const error = envelope([{ field: "business_name", message: "Enter your business name." }]);
  expect(errorsForFields(error, FIELDS)).toEqual({});
});

test("no error, or no fields, gives an empty result", () => {
  expect(errorsForFields(undefined, FIELDS)).toEqual({});
  expect(errorsForFields(envelope(null), FIELDS)).toEqual({});
});
