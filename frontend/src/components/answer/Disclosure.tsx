// A row of hairline buttons under each answer ("SQL 2", "Table 8 rows", "Labels 3", "Timeline").
// Clicking one slides its panel open (height + fade); clicking it again, or another, closes it.
// Only one panel is open at a time, so the conversation stays calm.

import { AnimatePresence, motion } from "motion/react";
import { useId, useState, type ReactNode } from "react";

export interface Panel {
  id: string;
  title: string;
  count?: string;
  content: ReactNode;
}

export function Disclosures({ panels }: { panels: Panel[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const baseId = useId();
  if (!panels.length) return null;
  const current = panels.find((p) => p.id === open);
  return (
    <div className="disclosures">
      <div className="disclosures__bar">
        {panels.map((p) => (
          <button
            key={p.id}
            type="button"
            className="disclosure"
            aria-expanded={open === p.id}
            aria-controls={`${baseId}-${p.id}`}
            onClick={() => setOpen(open === p.id ? null : p.id)}
          >
            <span className="disclosure__chevron" aria-hidden>
              ›
            </span>
            {p.title}
            {p.count && <> <span className="disclosure__count">{p.count}</span></>}
          </button>
        ))}
      </div>
      <AnimatePresence initial={false} mode="wait">
        {current && (
          <motion.div
            key={current.id}
            id={`${baseId}-${current.id}`}
            className="disclosure__panel"
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.38, ease: [0.22, 1, 0.36, 1] }}
          >
            <div className="disclosure__inner">{current.content}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
