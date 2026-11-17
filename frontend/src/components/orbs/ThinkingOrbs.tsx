// The thinking orbs: soft white (or black, in light mode) spheres that drift, touch and melt into
// each other while the backend works. The melting is an SVG "goo" filter: blur everything, then
// sharpen the edges again — where two blurred circles overlap they fuse like drops of liquid.
// Idle (the welcome screen) they drift slowly; active (thinking) they move faster and breathe.

import { motion } from "motion/react";
import { useId } from "react";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import "./orbs.css";

interface Props {
  active: boolean;
  size?: "large" | "medium";
  caption?: string;
}

// Each satellite orb travels a closed loop through the centre (viewBox 0..200), so they keep merging.
const SATELLITES = [
  { r: 20, cx: [100, 146, 128, 100], cy: [100, 82, 136, 100], d: 5.2 },
  { r: 16, cx: [100, 58, 70, 100], cy: [100, 122, 66, 100], d: 6.4 },
  { r: 13, cx: [100, 118, 150, 100], cy: [100, 52, 104, 100], d: 7.1 },
  { r: 11, cx: [100, 70, 44, 100], cy: [100, 150, 104, 100], d: 5.8 },
];

export function ThinkingOrbs({ active, size = "large", caption }: Props) {
  const reduced = useReducedMotion();
  const filterId = `goo-${useId().replace(/[^a-zA-Z0-9-]/g, "")}`;
  const speed = active ? 1 : 2.2; // idle drifts more slowly

  const core = reduced ? (
    <circle cx={100} cy={100} r={34} />
  ) : (
    <motion.circle
      cx={100}
      cy={100}
      initial={{ r: 30 }}
      animate={{ r: active ? [30, 40, 30] : [32, 36, 32] }}
      transition={{ duration: 2.6 * speed, repeat: Infinity, ease: "easeInOut" }}
    />
  );

  return (
    <div
      className={`orbs orbs--${size} ${active ? "orbs--active" : ""}`}
      data-testid="thinking-orbs"
      data-motion={reduced ? "reduced" : "full"}
      {...(active ? { role: "status", "aria-label": "Aether is thinking" } : { "aria-hidden": true })}
    >
      <svg viewBox="0 0 200 200" className="orbs__svg">
        <defs>
          <filter id={filterId} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="7" result="blur" />
            <feColorMatrix in="blur" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 22 -10" />
          </filter>
        </defs>
        <g className="orbs__halo">{core}</g>
        <g filter={`url(#${filterId})`} className="orbs__body">
          {core}
          {SATELLITES.map((s, i) =>
            reduced ? (
              <circle key={i} cx={s.cx[1]} cy={s.cy[1]} r={s.r * 0.8} />
            ) : (
              <motion.circle
                key={i}
                r={s.r}
                // Start part-way round the loop (already spread out), not stacked in the centre.
                initial={{ cx: s.cx[1], cy: s.cy[1] }}
                animate={{ cx: [s.cx[1], s.cx[2], s.cx[0], s.cx[1]], cy: [s.cy[1], s.cy[2], s.cy[0], s.cy[1]] }}
                transition={{ duration: s.d * speed, repeat: Infinity, ease: "easeInOut", delay: i * 0.35 }}
              />
            ),
          )}
        </g>
      </svg>
      {caption && (
        <motion.p
          key={caption}
          className="orbs__caption"
          initial={reduced ? { opacity: 0 } : { opacity: 0, y: 4, filter: "blur(4px)" }}
          animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
          transition={{ duration: 0.45, ease: [0.22, 1, 0.36, 1] }}
        >
          {caption}
          <span className="orbs__dots" aria-hidden>
            …
          </span>
        </motion.p>
      )}
    </div>
  );
}
