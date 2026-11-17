// Where you type. A single hairline box that grows with your text. Enter sends, Shift+Enter makes
// a new line. While Aether is thinking you can keep typing, but sending waits until it answers.
// In patient mode it stays locked until a patient is chosen.

import { useEffect, useRef, useState, type FormEvent } from "react";
import type { Role } from "../api/types";

interface Props {
  role: Role;
  locked: boolean;       // patient mode without a patient
  pending: boolean;
  onSend: (text: string) => void;
}

export function Composer({ role, locked, pending, onSend }: Props) {
  const [text, setText] = useState("");
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    const el = area.current;
    if (!el) return;
    if (!text) {
      el.style.height = ""; // empty: one line, even if the placeholder is longer than the box
      return;
    }
    el.style.height = "0px";
    el.style.height = `${Math.min(el.scrollHeight, 180)}px`;
  }, [text]);

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (!text.trim() || pending || locked) return;
    onSend(text);
    setText("");
  };

  const placeholder = locked
    ? "Choose a patient to view as…"
    : role === "patient"
      ? "Ask about your records or your medicines…"
      : "Ask about patients, billing or medicines…";

  return (
    <>
    <form className={`composer ${pending ? "composer--pending" : ""}`} onSubmit={submit}>
      <textarea
        ref={area}
        className="composer__input"
        name="message"
        aria-label="Message"
        rows={1}
        placeholder={placeholder}
        disabled={locked}
        value={text}
        onChange={(e) => setText(e.target.value)}
        maxLength={1000}
        onKeyDown={(e) => {
          // Enter that confirms a Japanese/Chinese/Korean character (IME composition) must not send.
          if (e.nativeEvent.isComposing || e.keyCode === 229) return;
          if (e.key === "Enter" && !e.shiftKey) {
            e.preventDefault();
            submit();
          }
        }}
      />
      <button type="submit" className="composer__send" aria-label="Send" disabled={pending || locked || !text.trim()}>
        <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden>
          <path d="M4 10h11M11 5l5 5-5 5" fill="none" stroke="currentColor" strokeWidth="1.2" />
        </svg>
      </button>
    </form>
    {locked && <p className="composer__hint">Pick someone above — Aether will answer as if you were them.</p>}
    </>
  );
}
