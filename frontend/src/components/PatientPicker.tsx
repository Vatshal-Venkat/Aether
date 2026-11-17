// "View as patient": a searchable list of the 111 fake patients. Type a few letters to filter,
// click (or Enter for the first match) to choose. Opens by itself when you switch to Patient
// and nobody is chosen yet. Escape or a click outside closes it.

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getPatients } from "../api/client";
import type { Patient } from "../api/types";

interface Props {
  patient: Patient | null;
  onSelect: (p: Patient) => void;
}

export function PatientPicker({ patient, onSelect }: Props) {
  const [open, setOpen] = useState(patient === null);
  const [query, setQuery] = useState("");
  const [patients, setPatients] = useState<Patient[] | null>(null);
  const [failed, setFailed] = useState(false);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    getPatients().then(setPatients).catch(() => setFailed(true));
  }, []);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => root.current && !root.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener("mousedown", onDown);
    return () => document.removeEventListener("mousedown", onDown);
  }, [open]);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    return (patients ?? []).filter((p) => !q || p.name.toLowerCase().includes(q));
  }, [patients, query]);

  const choose = (p: Patient) => {
    onSelect(p);
    setOpen(false);
    setQuery("");
  };

  return (
    <div className="picker" ref={root}>
      <button type="button" className="picker__button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className={patient ? "" : "picker__placeholder"}>{patient ? patient.name : "Choose a patient"}</span>
        <span className="picker__caret" aria-hidden>▾</span>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            className="picker__panel"
            initial={{ opacity: 0, y: -6, filter: "blur(4px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -4, filter: "blur(4px)" }}
            transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}
          >
            <input
              type="search"
              className="picker__search"
              name="patient-search"
              aria-label="Search patients"
              placeholder="Search 111 patients…"
              autoFocus
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && matches[0]) choose(matches[0]);
                if (e.key === "Escape") setOpen(false);
              }}
            />
            <ul className="picker__list" role="listbox" aria-label="Patients">
              {failed && <li className="picker__empty">Couldn't load patients.</li>}
              {!failed && patients === null && <li className="picker__empty">Loading…</li>}
              {patients !== null && matches.length === 0 && <li className="picker__empty">No match.</li>}
              {matches.map((p) => (
                <li key={p.id} role="option" aria-selected={patient?.id === p.id} className="picker__option" onClick={() => choose(p)}>
                  <span>{p.name}</span>
                  <span className="picker__detail">{p.gender} · {p.birthdate.slice(0, 4)}</span>
                </li>
              ))}
            </ul>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
