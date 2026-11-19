// "View as patient": a searchable list of the 111 fake patients. Type a few letters to filter,
// click (or Enter for the first match) to choose. Opens by itself when you switch to Patient
// and nobody is chosen yet. Escape or a click outside closes it.

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useMemo, useRef, useState } from "react";
import { getPatients } from "../api/client";
import type { Patient } from "../api/types";
import { cleanNames } from "../lib/names";
import { similarity } from "../lib/trigram";

const FUZZY_MIN = 0.3; // trigram score below which two names are different names
const FUZZY_MAX = 5;   // at most this many "closest matches"

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

  // Exact text first (the name as shown, "miranda jacobs", or as stored, "jacobs452"). If nothing contains
  // what was typed, fall back to the closest-sounding names by trigram score, so typos still find people.
  const { matches, fuzzy } = useMemo(() => {
    const all = patients ?? [];
    const q = query.trim().toLowerCase();
    const exact = all.filter((p) => !q || cleanNames(p.name).toLowerCase().includes(q) || p.name.toLowerCase().includes(q));
    if (exact.length || q.length < 3) return { matches: exact, fuzzy: false };
    const close = all
      .map((p) => ({ p, score: similarity(q, cleanNames(p.name)) }))
      .filter((s) => s.score >= FUZZY_MIN)
      .sort((a, b) => b.score - a.score)
      .slice(0, FUZZY_MAX)
      .map((s) => s.p);
    return { matches: close, fuzzy: close.length > 0 };
  }, [patients, query]);

  const choose = (p: Patient) => {
    onSelect(p);
    setOpen(false);
    setQuery("");
  };

  return (
    <div className="picker" ref={root}>
      <button type="button" className="picker__button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(!open)}>
        <span className={patient ? "" : "picker__placeholder"}>{patient ? cleanNames(patient.name) : "Choose a patient"}</span>
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
              {fuzzy && <li className="picker__empty" role="presentation">Closest matches</li>}
              {matches.map((p) => (
                <li key={p.id} role="option" aria-selected={patient?.id === p.id} className="picker__option" onClick={() => choose(p)}>
                  <span>{cleanNames(p.name)}</span>
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
