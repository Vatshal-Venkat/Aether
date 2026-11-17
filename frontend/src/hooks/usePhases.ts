// The caption under the thinking orbs: the backend's steps, in order. Until streaming exists
// (Plan 4) the website can't see which step the backend is really on, so these advance on a timer
// and stop at the last one — an honest "roughly what's happening", not a live report.

import { useEffect, useState } from "react";

export const PHASES = ["Routing", "Writing SQL", "Checking safety", "Querying", "Writing the answer", "Checking numbers"];
const STEP_MS = 1400;

export function usePhases(active: boolean): string {
  const [index, setIndex] = useState(0);
  useEffect(() => {
    if (!active) return;
    setIndex(0);
    const timer = setInterval(() => setIndex((i) => Math.min(i + 1, PHASES.length - 1)), STEP_MS);
    return () => clearInterval(timer);
  }, [active]);
  return PHASES[index];
}
