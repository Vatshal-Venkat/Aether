// The thinking orbs: liquid droplets that drift, touch and melt into each other while the backend
// works. The melting is an SVG "goo" filter: blur everything, then sharpen the edges again — where
// two blurred circles overlap they fuse like drops of mercury.
//
// Why the motion feels fluid rather than mechanical:
//  * every droplet moves left-right and up-down on two SEPARATE rhythms whose lengths never line up
//    (e.g. 3.7 s and 5.3 s), so its path keeps changing and never visibly loops;
//  * each one also swells and shrinks on its own timing, and the core breathes;
//  * the whole cluster turns very slowly;
//  * all movement eases in and out (no sudden starts or stops).
// Idle (the welcome screen) everything runs about twice as slowly. With "reduce motion" switched on,
// the same droplets are drawn standing still.

import { motion } from "motion/react";
import { useId } from "react";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import "./orbs.css";

interface Props {
  active: boolean;
  size?: "large" | "medium";
  caption?: string;
}

// ax/ay: how far it swings across/up-down; tx/ty: seconds per swing on each axis (deliberately
// unrelated numbers); flip: start on the other side; r: size; tr: seconds per swell.
const DROPLETS = [
  { ax: 58, ay: 26, tx: 3.7, ty: 5.3, flip: false, r: 17, tr: 4.1 },
  { ax: 44, ay: 40, tx: 4.9, ty: 3.3, flip: true, r: 13, tr: 3.6 },
  { ax: 70, ay: 18, tx: 6.1, ty: 4.3, flip: false, r: 10, tr: 5.2 },
  { ax: 36, ay: 46, tx: 5.6, ty: 6.7, flip: true, r: 14, tr: 4.6 },
  { ax: 64, ay: 32, tx: 7.9, ty: 4.7, flip: false, r: 8, tr: 3.1 },
];

const swing = (duration: number) => ({ duration, repeat: Infinity, repeatType: "mirror" as const, ease: "easeInOut" as const });

export function ThinkingOrbs({ active, size = "large", caption }: Props) {
  const reduced = useReducedMotion();
  const gooId = `goo-${useId().replace(/[^a-zA-Z0-9-]/g, "")}`;
  const slow = active ? 1 : 2.1;

  const droplets = DROPLETS.map((d, i) => {
    const sign = d.flip ? -1 : 1;
    const x = [100 - sign * d.ax, 100 + sign * d.ax];
    const y = [100 + sign * d.ay, 100 - sign * d.ay];
    if (reduced) {
      return <circle key={i} className="droplet" cx={100 + sign * d.ax * 0.45} cy={100 - sign * d.ay * 0.45} r={d.r} />;
    }
    return (
      <motion.circle
        key={i}
        className="droplet"
        initial={{ cx: x[0], cy: y[0], r: d.r }}
        animate={{ cx: x, cy: y, r: [d.r * 0.8, d.r * 1.15] }}
        transition={{ cx: swing(d.tx * slow), cy: swing(d.ty * slow), r: swing(d.tr * slow) }}
      />
    );
  });

  const core = reduced ? (
    <circle className="core" cx={100} cy={100} r={32} />
  ) : (
    <motion.circle
      className="core"
      initial={{ cx: 100, cy: 100, r: 30 }}
      animate={{ cx: [96, 104], cy: [103, 97], r: active ? [28, 37] : [30, 34] }}
      transition={{ cx: swing(4.4 * slow), cy: swing(5.8 * slow), r: swing(2.4 * slow) }}
    />
  );

  return (
    <div
      className={`orbs orbs--${size} ${active ? "orbs--active" : ""}`}
      data-testid="thinking-orbs"
      data-motion={reduced ? "reduced" : "full"}
      {...(active ? { role: "status", "aria-label": "Aether is thinking" } : { "aria-hidden": true })}
    >
      <svg viewBox="0 10 200 180" className="orbs__svg">
        <defs>
          <filter id={gooId} x="-30%" y="-30%" width="160%" height="160%">
            <feGaussianBlur in="SourceGraphic" stdDeviation="9" result="blur" />
            <feColorMatrix in="blur" mode="matrix" values="1 0 0 0 0  0 1 0 0 0  0 0 1 0 0  0 0 0 21 -9" />
          </filter>
        </defs>
        <g className="orbs__halo">
          <circle cx={100} cy={100} r={44} />
        </g>
        <g className="orbs__spin">
          <g filter={`url(#${gooId})`} className="orbs__body">
            {core}
            {droplets}
          </g>
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
