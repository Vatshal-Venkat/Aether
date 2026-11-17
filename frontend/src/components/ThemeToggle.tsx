// Dark / light switch: a half-filled circle that turns over when clicked.

import { motion } from "motion/react";
import type { Theme } from "../hooks/useTheme";

export function ThemeToggle({ theme, onToggle }: { theme: Theme; onToggle: () => void }) {
  const next = theme === "dark" ? "light" : "dark";
  return (
    <button type="button" className="icon-button" aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`} onClick={onToggle}>
      <motion.svg viewBox="0 0 20 20" width="16" height="16" animate={{ rotate: theme === "dark" ? 0 : 180 }}
        transition={{ duration: 0.6, ease: [0.22, 1, 0.36, 1] }}>
        <circle cx="10" cy="10" r="8.5" fill="none" stroke="currentColor" strokeWidth="1" />
        <path d="M10 1.5 A8.5 8.5 0 0 1 10 18.5 Z" fill="currentColor" />
      </motion.svg>
    </button>
  );
}
