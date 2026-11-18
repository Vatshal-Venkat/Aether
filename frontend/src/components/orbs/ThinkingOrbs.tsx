// The thinking orbs: liquid droplets that drift, touch and melt into each other while the backend
// works — and change rhythm with what the backend is doing (see moods.ts: swirling while writing SQL,
// a heartbeat while querying, pulling into one drop for the safety check...).
//
// The melting is an SVG "goo" filter: blur everything, then sharpen the edges again — where two
// blurred circles overlap they fuse like drops of mercury.
//
// The motion is a tiny physics loop that runs every frame (about 60 times a second):
//  * the current rhythm (speed, spread, pulse, spin) GLIDES toward the target rhythm of the step the
//    backend just reported, so a change of step never makes the droplets jump;
//  * each droplet moves left-right and up-down on two separate rhythms that never line up, so its
//    path never visibly repeats; each also swells and shrinks, riding the core's pulse;
//  * the whole cluster turns slowly.
// With "reduce motion" switched on, the same droplets are drawn standing still.

import { useEffect, useId, useRef } from "react";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import { MOODS, type Mood, type MoodShape } from "./moods";
import "./orbs.css";

interface Props {
  active: boolean;
  size?: "large" | "medium";
  caption?: string;
  mood?: Mood;
}

// ax/ay: swing across/up-down; tx/ty: seconds per swing on each axis (deliberately unrelated);
// px/py: starting phase; r: size; tr: seconds per swell.
const DROPLETS = [
  { ax: 58, ay: 26, tx: 3.7, ty: 5.3, px: 0.0, py: 1.1, r: 17, tr: 4.1 },
  { ax: 44, ay: 40, tx: 4.9, ty: 3.3, px: 2.1, py: 0.4, r: 13, tr: 3.6 },
  { ax: 70, ay: 18, tx: 6.1, ty: 4.3, px: 4.0, py: 2.6, r: 10, tr: 5.2 },
  { ax: 36, ay: 46, tx: 5.6, ty: 6.7, px: 1.3, py: 5.0, r: 14, tr: 4.6 },
  { ax: 64, ay: 32, tx: 7.9, ty: 4.7, px: 5.2, py: 3.3, r: 8, tr: 3.1 },
];
const TAU = Math.PI * 2;

/** The core's pulse at position p (0..1) through one beat, as a fraction of its size. */
function pulseAt(kind: MoodShape["pulse"], p: number): number {
  switch (kind) {
    case "breathe":
      return 0.12 * Math.sin(TAU * p);
    case "heartbeat": // lub-dub: a strong beat, a softer echo, then rest
      return 0.24 * Math.exp(-(((p - 0.08) / 0.05) ** 2)) + 0.14 * Math.exp(-(((p - 0.3) / 0.05) ** 2)) - 0.03;
    case "tick": // a quick tap at the start of each beat
      return p < 0.18 ? 0.09 * (1 - p / 0.18) : 0;
    case "hold":
      return 0.03 * Math.sin(TAU * p);
  }
}

function dropletAt(d: (typeof DROPLETS)[number], t: number, spread: number) {
  return {
    cx: 100 + spread * d.ax * Math.sin((TAU * t) / d.tx + d.px),
    cy: 100 + spread * d.ay * Math.sin((TAU * t) / d.ty + d.py),
    r: d.r * (0.92 + 0.14 * Math.sin((TAU * t) / d.tr)),
  };
}

export function ThinkingOrbs({ active, size = "large", caption, mood: given }: Props) {
  const reduced = useReducedMotion();
  const gooId = `goo-${useId().replace(/[^a-zA-Z0-9-]/g, "")}`;
  const mood: Mood = active ? (given ?? "calm") : "idle";

  const moodRef = useRef(mood);
  moodRef.current = mood;
  const coreRef = useRef<SVGCircleElement>(null);
  const spinRef = useRef<SVGGElement>(null);
  const dropRefs = useRef<(SVGCircleElement | null)[]>([]);

  useEffect(() => {
    if (reduced || typeof requestAnimationFrame !== "function") return;
    const start = MOODS[moodRef.current];
    // The simulation's current rhythm; it glides toward the target mood every frame.
    const sim = { ...start, t: 0, angle: 0, beatPhase: 0, pulse: 0 };
    let last = performance.now();
    let frame = 0;

    const tick = (now: number) => {
      const dt = Math.min(0.05, (now - last) / 1000);
      last = now;
      const target = MOODS[moodRef.current];
      const glide = 1 - Math.exp(-dt * 2.4); // ~0.4 s to settle into a new rhythm
      sim.speed += (target.speed - sim.speed) * glide;
      sim.spread += (target.spread - sim.spread) * glide;
      sim.core += (target.core - sim.core) * glide;
      sim.spin += (target.spin - sim.spin) * glide;
      sim.beat += (target.beat - sim.beat) * glide;
      sim.jitter += (target.jitter - sim.jitter) * glide;

      sim.t += dt * sim.speed;
      sim.angle = (sim.angle + dt * sim.spin) % 360;
      sim.beatPhase = (sim.beatPhase + dt / sim.beat) % 1;
      const rawPulse = pulseAt(target.pulse, sim.beatPhase);
      sim.pulse += (rawPulse - sim.pulse) * Math.min(1, dt * 14); // smooth switch between pulse shapes

      coreRef.current?.setAttribute("r", (sim.core * (1 + sim.pulse)).toFixed(2));
      DROPLETS.forEach((d, i) => {
        const el = dropRefs.current[i];
        if (!el) return;
        const p = dropletAt(d, sim.t, sim.spread);
        const shake = sim.jitter ? () => (Math.random() - 0.5) * sim.jitter : () => 0;
        el.setAttribute("cx", (p.cx + shake()).toFixed(2));
        el.setAttribute("cy", (p.cy + shake()).toFixed(2));
        el.setAttribute("r", (p.r * (1 + 0.6 * sim.pulse)).toFixed(2)); // droplets ride the pulse
      });
      spinRef.current?.setAttribute("transform", `rotate(${sim.angle.toFixed(2)} 100 100)`);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [reduced]);

  return (
    <div
      className={`orbs orbs--${size} ${active ? "orbs--active" : ""}`}
      data-testid="thinking-orbs"
      data-motion={reduced ? "reduced" : "full"}
      data-mood={mood}
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
        <g ref={spinRef}>
          <g filter={`url(#${gooId})`} className="orbs__body">
            <circle ref={coreRef} className="core" cx={100} cy={100} r={MOODS[mood].core} />
            {DROPLETS.map((d, i) => {
              const p = dropletAt(d, reduced ? 0.6 : 0, MOODS[mood].spread);
              return (
                <circle key={i} ref={(el) => { dropRefs.current[i] = el; }} className="droplet" cx={p.cx} cy={p.cy} r={p.r} />
              );
            })}
          </g>
        </g>
      </svg>
      {caption && (
        <p key={caption} className="orbs__caption">
          {caption}
          <span className="orbs__dots" aria-hidden>
            …
          </span>
        </p>
      )}
    </div>
  );
}
