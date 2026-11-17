// The small orb beside each reply — where the thinking orbs "land". Filled for a normal answer,
// outlined for a refusal or out-of-scope reply, dashed for an error.

import { motion } from "motion/react";
import type { AnswerKind } from "../../api/types";
import "./orbs.css";

export function AnswerOrb({ kind }: { kind: AnswerKind }) {
  return (
    <motion.span
      className="answer-orb"
      data-testid="answer-orb"
      data-kind={kind}
      initial={{ scale: 2.4, opacity: 0, filter: "blur(6px)" }}
      animate={{ scale: 1, opacity: 1, filter: "blur(0px)" }}
      transition={{ duration: 0.7, ease: [0.22, 1, 0.36, 1] }}
      aria-hidden
    />
  );
}
