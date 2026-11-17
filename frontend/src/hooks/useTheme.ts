// Dark (default) or light. The choice is remembered in this browser only (localStorage); if the
// browser blocks storage, the toggle still works for the current visit.

import { useCallback, useEffect, useState } from "react";

export type Theme = "dark" | "light";
const KEY = "aether.theme";

function stored(): Theme {
  try {
    return localStorage.getItem(KEY) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(stored);
  useEffect(() => {
    document.documentElement.dataset.theme = theme;
  }, [theme]);
  const toggle = useCallback(() => {
    setTheme((t) => {
      const next: Theme = t === "dark" ? "light" : "dark";
      try {
        localStorage.setItem(KEY, next);
      } catch {
        /* storage unavailable: keep the choice for this visit only */
      }
      return next;
    });
  }, []);
  return { theme, toggle };
}
