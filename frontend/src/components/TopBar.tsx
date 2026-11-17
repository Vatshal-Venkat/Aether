// The bar across the top: the AETHER wordmark, the "view as" switch (and patient picker), the
// backend status orb and the theme toggle. A single hairline separates it from the conversation.

import type { Health, Patient, Role } from "../api/types";
import type { Theme } from "../hooks/useTheme";
import { StatusOrb } from "./orbs/StatusOrb";
import { PatientPicker } from "./PatientPicker";
import { RolePill } from "./RolePill";
import { ThemeToggle } from "./ThemeToggle";

interface Props {
  role: Role;
  patient: Patient | null;
  onRole: (role: Role, patient?: Patient | null) => void;
  health: Health | null;
  healthError: boolean;
  theme: Theme;
  onTheme: () => void;
}

export function TopBar({ role, patient, onRole, health, healthError, theme, onTheme }: Props) {
  return (
    <header className="topbar">
      <div className="topbar__brand">
        <span className="wordmark">AETHER</span>
      </div>
      <div className="topbar__center">
        <RolePill role={role} onChange={(r) => onRole(r)} />
        {role === "patient" && <PatientPicker patient={patient} onSelect={(p) => onRole("patient", p)} />}
      </div>
      <div className="topbar__end">
        <StatusOrb health={health} error={healthError} />
        <ThemeToggle theme={theme} onToggle={onTheme} />
      </div>
    </header>
  );
}
