"use client";
// Composer (UX-DR13), shared by the Chat Page and the Inbox (story 4.4; moved from ChatPanel).
// A multi-line box and Send. It owns the text: on send it hands the trimmed text to onSend,
// empties the box, and puts focus back in it (keep typing without tapping the box again).
// Keep this light (NFR-6): plain elements, no ui/button.
import { useRef, useState } from "react";
import { PILL_BUTTON } from "./pillButton";

// Same as the server's MAX_BODY (inbox/schemas.py): the box stops at the limit.
const MAX_BODY = 2000;

// Enter sends only with a mouse or trackpad. On a phone, Enter in the keyboard is a new line
// and the Send button sends (UX-DR13). Old browsers and tests may have no matchMedia.
function hasFinePointer(): boolean {
  return typeof window.matchMedia === "function" && window.matchMedia("(pointer: fine)").matches;
}

export function Composer({
  id,
  label,
  placeholder,
  onSend,
  hint,
}: {
  id: string;
  label: string;
  placeholder: string;
  onSend: (body: string) => void;
  hint?: string;
}) {
  const [text, setText] = useState("");
  const box = useRef<HTMLTextAreaElement>(null);

  function send() {
    const body = text.trim();
    if (!body) return;
    onSend(body);
    setText("");
    box.current?.focus();
  }

  return (
    <form
      className="flex flex-col gap-1"
      onSubmit={(event) => {
        event.preventDefault();
        send();
      }}
    >
      {/* The hint is tied to the box, so a screen reader reads it with the box. */}
      {hint && (
        <p id={`${id}-hint`} className="text-sm text-muted-foreground">
          {hint}
        </p>
      )}
      <div className="flex items-end gap-2">
        <label htmlFor={id} className="sr-only">
          {label}
        </label>
        <textarea
          id={id}
          ref={box}
          rows={2}
          maxLength={MAX_BODY}
          value={text}
          placeholder={placeholder}
          aria-describedby={hint ? `${id}-hint` : undefined}
          className="min-h-11 flex-1 resize-none rounded-xl border bg-background px-3 py-2 text-base focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:outline-none"
          onChange={(event) => setText(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey && hasFinePointer()) {
              event.preventDefault();
              send();
            }
          }}
        />
        <button type="submit" className={PILL_BUTTON} disabled={!text.trim()}>
          Send
        </button>
      </div>
    </form>
  );
}
