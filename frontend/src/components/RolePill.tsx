// The "who is asking" switch: Clinician | Patient. A thin outline pill with a solid indicator that
// slides between the two choices (motion's shared layout animation).

import { motion } from "motion/react";
import type { Role } from "../api/types";

const ROLES: { id: Role; label: string }[] = [
  { id: "clinician", label: "Clinician" },
  { id: "patient", label: "Patient" },
];

export function RolePill({ role, onChange }: { role: Role; onChange: (role: Role) => void }) {
  return (
    <div className="role-pill" role="group" aria-label="View as">
      {ROLES.map((r) => (
        <button
          key={r.id}
          type="button"
          className="role-pill__option"
          aria-pressed={role === r.id}
          onClick={() => role !== r.id && onChange(r.id)}
        >
          {role === r.id && (
            <motion.span layoutId="role-pill-indicator" className="role-pill__indicator"
              transition={{ type: "spring", stiffness: 420, damping: 36 }} />
          )}
          <span className="role-pill__label">{r.label}</span>
        </button>
      ))}
    </div>
  );
}
