// Asks the backend "are you there?" (GET /health) on start and every 15 seconds, for the status orb.

import { useEffect, useState } from "react";
import { getHealth } from "../api/client";
import type { Health } from "../api/types";

export function useHealth(intervalMs = 15000) {
  const [health, setHealth] = useState<Health | null>(null);
  const [error, setError] = useState(false);
  useEffect(() => {
    let alive = true;
    const check = () =>
      getHealth()
        .then((h) => alive && (setHealth(h), setError(false)))
        .catch(() => alive && (setHealth(null), setError(true)));
    check();
    const timer = setInterval(check, intervalMs);
    return () => {
      alive = false;
      clearInterval(timer);
    };
  }, [intervalMs]);
  return { health, error };
}
