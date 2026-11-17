// The welcome screen: the orbs drifting slowly, a one-line greeting, and a few example questions
// (different for clinicians and patients). Clicking an example asks it.

import { motion } from "motion/react";
import type { Role } from "../api/types";
import { ThinkingOrbs } from "./orbs/ThinkingOrbs";

const EXAMPLES: Record<Role, string[]> = {
  clinician: [
    "How many patients have diabetes?",
    "Which doctor has seen the most patients?",
    "Which insurance company has the most customers?",
    "What are the side effects of metformin?",
  ],
  patient: [
    "What medications am I taking?",
    "When was my last visit?",
    "How much do I still owe?",
    "What are the side effects of my medications?",
  ],
};

interface Props {
  role: Role;
  locked: boolean;
  onExample: (q: string) => void;
}

export function EmptyState({ role, locked, onExample }: Props) {
  return (
    <div className="empty">
      <motion.div initial={{ opacity: 0, scale: 0.85 }} animate={{ opacity: 1, scale: 1 }} transition={{ duration: 1.2, ease: [0.22, 1, 0.36, 1] }}>
        <ThinkingOrbs active={false} size="large" />
      </motion.div>
      <motion.h1 className="empty__title" initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} transition={{ delay: 0.25, duration: 0.8, ease: [0.22, 1, 0.36, 1] }}>
        Ask Aether
      </motion.h1>
      <motion.p className="empty__subtitle" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.45, duration: 0.8 }}>
        {role === "clinician"
          ? "Medical records, billing and FDA drug labels — answered from the data, with every query shown."
          : "Your own records and your medicines — nothing about anyone else."}
      </motion.p>
      <div className="empty__examples">
        {EXAMPLES[role].map((q, i) => (
          <motion.button
            key={q}
            type="button"
            className="chip"
            disabled={locked}
            onClick={() => onExample(q)}
            initial={{ opacity: 0, y: 8 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.6 + i * 0.08, duration: 0.6, ease: [0.22, 1, 0.36, 1] }}
          >
            {q}
          </motion.button>
        ))}
      </div>
    </div>
  );
}
