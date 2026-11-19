// AI model limits, next to the theme toggle. One round button opens a small menu; its "Show model limits"
// button loads each model's free daily allowance (main -> backup -> last resort): available or resting
// (limit reached, back in N min), and tokens left over the last 24 hours, marked "exact" (the provider's own
// figure) or "estimated" (our count — Groq only states exact numbers once a limit is hit).

import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { ApiError, getUsage } from "../api/client";
import type { ModelUsage } from "../api/types";

const fmt = (n: number) => n.toLocaleString("en-US");

function Row({ m }: { m: ModelUsage }) {
  const resting = m.status === "resting";
  // Until the count covers 24 hours (or the provider gives a figure), earlier use is missing: show what was
  // used since counting began, never a "tokens left" figure that could be far too high.
  const known = m.exact || m.complete;
  const since = new Date(m.counting_since * 1000).toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  const share = known && m.daily_limit && m.remaining !== null ? m.remaining / m.daily_limit : null;
  return (
    <li className="usage__row" data-status={m.status}>
      <div className="usage__head">
        <span className="usage__name">{m.name}</span>
        <span className="usage__role">{m.role}</span>
      </div>
      <p className="usage__status">
        {resting
          ? `Limit reached — back in about ${Math.max(1, Math.ceil((m.back_in_s ?? 0) / 60))} min`
          : "Available"}
      </p>
      {share !== null && (
        <span className="usage__track" aria-hidden>
          <span className="usage__bar" style={{ width: `${Math.max(1, share * 100)}%` }} />
        </span>
      )}
      <p className="usage__numbers">
        {!known
          ? `${fmt(m.used)} tokens used since ${since}`
          : m.daily_limit && m.remaining !== null
            ? `${fmt(m.remaining)} of ${fmt(m.daily_limit)} tokens left`
            : `${fmt(m.used)} tokens used today`}
        <span className="usage__exact">{m.exact ? "exact" : known ? "estimated" : "partial"}</span>
      </p>
    </li>
  );
}

export function UsageMenu() {
  const [open, setOpen] = useState(false);
  const [rows, setRows] = useState<ModelUsage[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const root = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => root.current && !root.current.contains(e.target as Node) && setOpen(false);
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const toggle = () => {
    setOpen(!open);
    setRows(null);  // fresh numbers every time it is opened
    setProblem(null);
  };

  const load = async () => {
    setLoading(true);
    setProblem(null);
    try {
      setRows(await getUsage());
    } catch (err) {
      setProblem(err instanceof ApiError ? err.userMessage : "Couldn't load the model limits.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="usage" ref={root}>
      <button type="button" className="icon-button" aria-label="AI model limits" title="AI model limits"
        aria-expanded={open} onClick={toggle}>
        {/* a gauge: hairline arc and needle */}
        <svg viewBox="0 0 20 20" width="16" height="16" aria-hidden>
          <path d="M3 14 A7.5 7.5 0 1 1 17 14" fill="none" stroke="currentColor" strokeWidth="1" />
          <path d="M10 13 L13.5 7.5" stroke="currentColor" strokeWidth="1.2" strokeLinecap="round" />
          <circle cx="10" cy="13" r="1.2" fill="currentColor" />
        </svg>
      </button>
      <AnimatePresence>
        {open && (
          <motion.div className="usage__panel"
            initial={{ opacity: 0, y: -6, filter: "blur(4px)" }} animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -4, filter: "blur(4px)" }} transition={{ duration: 0.22, ease: [0.22, 1, 0.36, 1] }}>
            {rows === null ? (
              <button type="button" className="chip usage__show" onClick={load} disabled={loading}>
                {loading ? "Loading…" : "Show model limits"}
              </button>
            ) : (
              <ul className="usage__list" aria-label="AI models">
                {rows.length === 0 && <li className="usage__empty">No AI models configured.</li>}
                {rows.map((m) => <Row key={m.model} m={m} />)}
              </ul>
            )}
            {problem && <p className="usage__problem">{problem}</p>}
            {rows !== null && rows.length > 0 && (
              <p className="usage__note">Free daily allowance, last 24 hours. If the main model runs out, Aether
                switches to the next one automatically.</p>
            )}
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
