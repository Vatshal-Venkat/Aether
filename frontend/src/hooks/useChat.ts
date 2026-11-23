// The conversation's brain: who is asking (clinician, or which patient), the messages so far, and
// whether we're waiting for the backend — and, while waiting, which step it reports it is on.
//
// Two safety rules live here:
//  * Switching role or patient wipes the conversation and starts a new session id, so answers
//    from one view never appear in another.
//  * A question still in flight when you switch is cancelled, and if its answer arrives anyway it
//    is thrown away (each send remembers the "generation" it belongs to).

import { useCallback, useRef, useState } from "react";
import { ApiError, askChatStream, getConversation } from "../api/client";
import type { ChatResult, PastTurn, Patient, Progress, Role } from "../api/types";

export interface Message {
  id: string;
  type: "user" | "assistant" | "error";
  text?: string;
  result?: ChatResult;
}

/** A saved turn as an answer card: the answer text only (tables and SQL are never stored). */
function pastResult(t: PastTurn): ChatResult {
  return { answer: t.answer, kind: t.kind, sql: [], sources: [], table: null, unverified_numbers: [], documents: [],
    timings: {}, standalone_question: t.standalone !== t.question ? t.standalone : null, from_history: true };
}

const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);

export function useChat() {
  const [role, setRoleState] = useState<Role>("clinician");
  const [patient, setPatient] = useState<Patient | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState(false);
  const [progress, setProgress] = useState<Progress | null>(null); // the step the backend is on
  const session = useRef(newId());
  const [sessionId, setSessionId] = useState(session.current); // shown as "current" in Past conversations
  const generation = useRef(0);
  const inflight = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    inflight.current?.abort();
    inflight.current = null;
    generation.current += 1;
    session.current = newId();
    setSessionId(session.current);
    setMessages([]);
    setPending(false);
    setProgress(null);
  }, []);

  const setRole = useCallback(
    (next: Role, nextPatient: Patient | null = null) => {
      reset();
      setRoleState(next);
      setPatient(next === "patient" ? nextPatient : null);
    },
    [reset],
  );

  const canSend = !pending && (role === "clinician" || patient !== null);

  const send = useCallback(
    async (raw: string) => {
      const text = raw.trim();
      if (!text || !canSend) return;
      const gen = generation.current;
      const controller = new AbortController();
      inflight.current = controller;
      setMessages((m) => [...m, { id: newId(), type: "user", text }]);
      setPending(true);
      setProgress(null);
      try {
        const result = await askChatStream(
          { message: text, role, session_id: session.current, ...(role === "patient" && patient ? { patient_id: patient.id } : {}) },
          // Live progress: ignored if the user has since switched role/patient.
          (p) => gen === generation.current && setProgress(p),
          controller.signal,
        );
        if (gen !== generation.current) return;
        setMessages((m) => [...m, { id: newId(), type: "assistant", result }]);
      } catch (err) {
        if (gen !== generation.current || (err instanceof DOMException && err.name === "AbortError")) return;
        const text = err instanceof ApiError ? err.userMessage : "Something went wrong.";
        setMessages((m) => [...m, { id: newId(), type: "error", text }]);
      } finally {
        if (gen === generation.current) {
          setPending(false);
          inflight.current = null;
        }
      }
    },
    [canSend, role, patient],
  );

  /** Reopen a past conversation: show its saved questions and answers, and keep its session id so the next
   *  question is a follow-up the backend remembers. Only this person's own conversations can be opened. */
  const openConversation = useCallback(
    async (id: string) => {
      reset();
      const gen = generation.current;
      setPending(true);
      try {
        const turns = await getConversation(id, role, role === "patient" ? patient?.id ?? null : null);
        if (gen !== generation.current) return;
        session.current = id;
        setSessionId(id);
        setMessages(turns.flatMap((t) => [
          { id: newId(), type: "user" as const, text: t.question },
          { id: newId(), type: "assistant" as const, result: pastResult(t) },
        ]));
      } catch (err) {
        if (gen !== generation.current) return;
        const text = err instanceof ApiError ? err.userMessage : "Couldn't open that conversation.";
        setMessages([{ id: newId(), type: "error", text }]);
      } finally {
        if (gen === generation.current) setPending(false);
      }
    },
    [reset, role, patient],
  );

  return { role, patient, messages, pending, progress, canSend, setRole, send, reset, sessionId, openConversation };
}
