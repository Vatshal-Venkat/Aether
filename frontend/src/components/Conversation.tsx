// The conversation: your questions (right, quiet), Aether's answers (left, with the orb), and —
// while the backend is working — the thinking orbs, moving in the rhythm of the step the backend
// reports, with a caption naming that step. New
// messages slide up softly; the view scrolls to the newest one.

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef } from "react";
import type { Progress, Role } from "../api/types";
import type { Owner } from "./answer/details";
import type { Message } from "../hooks/useChat";
import { useReducedMotion } from "../hooks/useReducedMotion";
import { AnswerCard } from "./answer/AnswerCard";
import { EmptyState } from "./EmptyState";
import { AnswerOrb } from "./orbs/AnswerOrb";
import { moodFor, phaseLabel } from "./orbs/moods";
import { ThinkingOrbs } from "./orbs/ThinkingOrbs";

interface Props {
  messages: Message[];
  pending: boolean;
  progress: Progress | null;
  role: Role;
  owner: Owner; // who is asking — big tables can only be paged by them
  locked: boolean;
  onExample: (q: string) => void;
}

const rise = {
  initial: { opacity: 0, y: 14, filter: "blur(6px)" },
  animate: { opacity: 1, y: 0, filter: "blur(0px)" },
  exit: { opacity: 0, y: -8, filter: "blur(6px)" },
  transition: { duration: 0.5, ease: [0.22, 1, 0.36, 1] as const },
};

export function Conversation({ messages, pending, progress, role, owner, locked, onExample }: Props) {
  const reduced = useReducedMotion();
  const end = useRef<HTMLDivElement>(null);

  useEffect(() => {
    end.current?.scrollIntoView({ behavior: reduced ? "auto" : "smooth", block: "end" });
  }, [messages.length, pending, reduced]);

  if (!messages.length && !pending) return <EmptyState role={role} locked={locked} onExample={onExample} />;

  return (
    <div className="conversation" aria-live="polite">
      <AnimatePresence initial={false}>
        {messages.map((m) => (
          <motion.div key={m.id} {...rise} layout="position">
            {m.type === "user" && (
              <div className="question">
                <span className="question__label">You</span>
                <p className="question__text">{m.text}</p>
              </div>
            )}
            {m.type === "assistant" && m.result && (
              <AnswerCard result={m.result} onOption={pending ? undefined : onExample} owner={owner} />
            )}
            {m.type === "error" && (
              <article className="answer" data-kind="error">
                <AnswerOrb kind="error" />
                <div className="answer__body">
                  <p className="answer__kind">{/rate-limited|allowance/i.test(m.text ?? "") ?"AI limit reached" : "Connection problem"}</p>
                  <p className="answer__text">{m.text}</p>
                </div>
              </article>
            )}
          </motion.div>
        ))}
        {pending && (
          <motion.div key="thinking" className="thinking" {...rise} exit={{ opacity: 0, scale: 0.6, filter: "blur(8px)" }}>
            <ThinkingOrbs active size="medium" mood={moodFor(progress)} caption={phaseLabel(progress)} />
          </motion.div>
        )}
      </AnimatePresence>
      <div ref={end} />
    </div>
  );
}
