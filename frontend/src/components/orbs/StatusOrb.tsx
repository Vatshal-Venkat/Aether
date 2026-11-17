// The tiny orb in the top bar that shows whether the backend is running. It breathes gently while
// /health says everything is fine, holds still and goes hollow when the backend can't be reached,
// and shows a half-filled state when one database is down. Hover it for the details.

import type { Health } from "../../api/types";
import "./orbs.css";

interface Props {
  health: Health | null;
  error: boolean;
}

export function StatusOrb({ health, error }: Props) {
  const state = error || !health ? "down" : health.status === "ok" ? "up" : "degraded";
  const title =
    state === "down"
      ? "Backend not reachable (start it with: uvicorn app.main:app --port 8000)"
      : `Backend running — clinical: ${health!.clinical} · billing: ${health!.billing} · drug labels: ${health!.drug_labels} · AI: ${health!.llm_provider}`;
  return (
    <span className="status-orb" data-testid="status-orb" data-state={state} title={title}>
      <span className="visually-hidden">{state === "down" ? "Backend offline" : "Backend online"}</span>
    </span>
  );
}
