// "Past conversations", next to the model-limits button. One round button opens a small menu: "New conversation"
// and this person's own past conversations, newest first — the clinician's in clinician mode, only the chosen
// patient's in patient mode, never anyone else's (there is no login yet, so no "everyone's history" view).
// Opening one shows its saved questions and answers and continues it: the next question is a follow-up.

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { ApiError, getConversations } from "../api/client";
import type { Conversation, Role } from "../api/types";
import { cleanNames } from "../lib/names";

interface Props {
  role: Role;
  patientId: string | null;
  current: string;                    // the conversation on screen
  onOpen: (sessionId: string) => void;
  onNew: () => void;
}

const when = (iso: string) =>
  new Date(iso).toLocaleString("en-US", { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });

export function HistoryMenu({ role, patientId, current, onOpen, onNew }: Props) {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState<Conversation[] | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);
  const needsPatient = role === "patient" && !patientId;

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => root.current && !root.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  useEffect(() => {
    if (!open || needsPatient) return;
    let live = true;  // a late reply for another person (role switched meanwhile) is ignored
    setItems(null);
    setProblem(null);
    getConversations(role, patientId)
      .then((list) => live && setItems(list))
      .catch((err) => live && setProblem(err instanceof ApiError ? err.userMessage : "Couldn't load past conversations."));
    return () => {
      live = false;
    };
  }, [open, role, patientId, needsPatient]);

  const choose = (id: string) => {
    setOpen(false);
    onOpen(id);
  };

  return (
    <div className="history" ref={root}>
      <button type="button" className="icon-button" aria-label="Past conversations" title="Past conversations"
        aria-expanded={open} onClick={() => setOpen(!open)}>
        {/* a clock face with a back-turning arrow: history */}
        <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden>
          <path d="M4.2 7.2 A6.5 6.5 0 1 1 3.5 10" fill="none" stroke="currentColor" strokeWidth="1" />
          <path d="M3.2 4.6 L4.2 7.4 L7 6.6" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" />
          <path d="M10 6.2 V10 L12.6 11.6" fill="none" stroke="currentColor" strokeWidth="1.1" strokeLinecap="round" />
        </svg>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div className="history__panel"
            initial={{ opacity: 0, y: -6, filter: "blur(4px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -4, filter: "blur(4px)" }} transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}>
            <div className="history__head">
              <span className="history__title">Past conversations</span>
              <button type="button" className="chip history__new" onClick={() => { setOpen(false); onNew(); }}>
                New conversation
              </button>
            </div>
            {needsPatient && <p className="history__empty">Pick a patient to see their conversations.</p>}
            {!needsPatient && items === null && !problem && <p className="history__empty">Loading…</p>}
            {problem && <p className="history__problem">{problem}</p>}
            {items !== null && items.length === 0 && <p className="history__empty">No past conversations yet.</p>}
            {items !== null && items.length > 0 && (
              <ul className="history__list" aria-label="Past conversations">
                {items.map((c) => (
                  <li key={c.session_id}>
                    <button type="button" className="history__item" aria-current={c.session_id === current ? "true" : undefined}
                      onClick={() => choose(c.session_id)}>
                      <span className="history__q">{cleanNames(c.title)}</span>
                      <span className="history__meta">
                        {c.questions} question{c.questions === 1 ? "" : "s"} · {when(c.updated_at)}
                        {c.session_id === current && <span className="history__now">on screen</span>}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
            <p className="history__note">Only {role === "patient" ? "this patient's" : "the clinician view's"} own
              conversations are listed. Answers are saved as text; tables are not kept.</p>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
