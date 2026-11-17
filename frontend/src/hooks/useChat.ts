// The conversation's brain: who is asking (clinician, or which patient), the messages so far, and
// whether we're waiting for the backend.
//
// Two safety rules live here:
//  * Switching role or patient wipes the conversation and starts a new session id, so answers
//    from one view never appear in another.
//  * A question still in flight when you switch is cancelled, and if its answer arrives anyway it
//    is thrown away (each send remembers the "generation" it belongs to).

import { useCallback, useRef, useState } from "react";
import { ApiError, askChat } from "../api/client";
import type { ChatResult, Patient, Role } from "../api/types";

export interface Message {
  id: string;
  type: "user" | "assistant" | "error";
  text?: string;
  result?: ChatResult;
}

const newId = () => (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`);

export function useChat() {
  const [role, setRoleState] = useState<Role>("clinician");
  const [patient, setPatient] = useState<Patient | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pending, setPending] = useState(false);
  const session = useRef(newId());
  const generation = useRef(0);
  const inflight = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    inflight.current?.abort();
    inflight.current = null;
    generation.current += 1;
    session.current = newId();
    setMessages([]);
    setPending(false);
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
      try {
        const result = await askChat(
          { message: text, role, session_id: session.current, ...(role === "patient" && patient ? { patient_id: patient.id } : {}) },
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

  return { role, patient, messages, pending, canSend, setRole, send, reset };
}
