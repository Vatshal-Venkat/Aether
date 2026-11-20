// The "Chart" panel: drawn automatically when a result is names + numbers (bars) or dates + numbers (a line).
// lib/chart.ts decides; this file draws it in the app's own hairline style: ink marks, muted text, no colours —
// one series at a time, so no legend is needed (the caption names it). Several number columns: chips switch.
// The Table panel stays the full, exact view of the same rows.

import { useState, type KeyboardEvent, type PointerEvent } from "react";
import { compact, fullNumber, niceTicks, type ChartSpec } from "../../lib/chart";

export function Chart({ spec }: { spec: ChartSpec }) {
  const [measure, setMeasure] = useState(0);
  const name = spec.measures[measure];
  return (
    <div className="chart">
      {spec.measures.length > 1 && (
        <div className="chart__measures" role="group" aria-label="Number to chart">
          {spec.measures.map((m, i) => (
            <button key={m} type="button" className="chart__measure" aria-pressed={i === measure} onClick={() => setMeasure(i)}>
              {m}
            </button>
          ))}
        </div>
      )}
      {spec.kind === "bar" ? <Bars spec={spec} measure={measure} name={name} /> : <Line spec={spec} measure={measure} name={name} />}
    </div>
  );
}

function Bars({ spec, measure, name }: { spec: ChartSpec; measure: number; name: string }) {
  const values = spec.points.map((p) => p.values[measure]);
  const lo = Math.min(0, ...values);
  const hi = Math.max(0, ...values);
  const span = hi - lo || 1;
  const zero = (-lo / span) * 100; // where the baseline sits (0% unless there are negative values)
  return (
    <figure className="chart__figure" aria-label={`${name} by ${spec.label}`}>
      <ul className="chart__bars">
        {spec.points.map((p, i) => {
          const v = p.values[measure];
          const width = (Math.abs(v) / span) * 100;
          return (
            <li key={i} className="chart__row" title={`${p.label}: ${fullNumber(v)}`}>
              <span className="chart__label">{p.label}</span>
              <span className="chart__track">
                <span className="chart__bar" data-negative={v < 0 ? "true" : undefined}
                  style={{ left: `${v < 0 ? zero - width : zero}%`, width: `${Math.max(width, v === 0 ? 0 : 0.5)}%` }} />
              </span>
              <span className="chart__value">{fullNumber(v)}</span>
            </li>
          );
        })}
      </ul>
      <figcaption className="chart__caption">
        {name} by {spec.label}
        {spec.total > spec.points.length && ` · first ${spec.points.length} of ${spec.total.toLocaleString("en-US")} rows`}
      </figcaption>
    </figure>
  );
}

const W = 640, H = 220, LEFT = 48, RIGHT = 16, TOP = 12, BOTTOM = 28;

function Line({ spec, measure, name }: { spec: ChartSpec; measure: number; name: string }) {
  const [active, setActive] = useState<number | null>(null);
  const pts = spec.points;
  const values = pts.map((p) => p.values[measure]);
  const min = Math.min(...values), max = Math.max(...values);
  const ticks = niceTicks(min >= 0 && min < max * 0.3 ? 0 : min, max, 4);
  const y0 = ticks[0], y1 = ticks[ticks.length - 1];
  const x0 = pts[0].x, x1 = pts[pts.length - 1].x;
  const sx = (x: number) => LEFT + ((x - x0) / (x1 - x0 || 1)) * (W - LEFT - RIGHT);
  const sy = (v: number) => TOP + (1 - (v - y0) / (y1 - y0 || 1)) * (H - TOP - BOTTOM);
  const path = pts.map((p, i) => `${i ? "L" : "M"}${sx(p.x).toFixed(1)},${sy(p.values[measure]).toFixed(1)}`).join("");
  const xLabels = [...new Set([0, Math.floor((pts.length - 1) / 2), pts.length - 1])];
  const last = pts.length - 1;
  const shown = active ?? last;

  const onMove = (e: PointerEvent<SVGRectElement>) => {
    const box = e.currentTarget.ownerSVGElement!.getBoundingClientRect();
    const x = ((e.clientX - box.left) / (box.width || 1)) * W;
    let best = 0;
    pts.forEach((p, i) => { if (Math.abs(sx(p.x) - x) < Math.abs(sx(pts[best].x) - x)) best = i; });
    setActive(best);
  };
  const onKey = (e: KeyboardEvent<SVGSVGElement>) => {
    if (e.key === "ArrowLeft") setActive(Math.max(0, shown - 1));
    else if (e.key === "ArrowRight") setActive(Math.min(last, shown + 1));
    else return;
    e.preventDefault();
  };

  return (
    <figure className="chart__figure chart__figure--line">
      <svg viewBox={`0 0 ${W} ${H}`} className="chart__svg" role="img" tabIndex={0} onKeyDown={onKey}
        aria-label={`${name} by ${spec.label}, ${pts[0].label} to ${pts[last].label}. Arrow keys step through the points.`}>
        {ticks.map((t) => (
          <g key={t}>
            <line className="chart__grid" x1={LEFT} x2={W - RIGHT} y1={sy(t)} y2={sy(t)} />
            <text className="chart__tick" x={LEFT - 8} y={sy(t)} textAnchor="end" dominantBaseline="middle">{compact(t)}</text>
          </g>
        ))}
        {xLabels.map((i) => (
          <text key={i} className="chart__tick" x={sx(pts[i].x)} y={H - 8}
            textAnchor={i === 0 ? "start" : i === last ? "end" : "middle"}>{pts[i].label}</text>
        ))}
        {active !== null && <line className="chart__cross" x1={sx(pts[active].x)} x2={sx(pts[active].x)} y1={TOP} y2={H - BOTTOM} />}
        <path className="chart__line" d={path} />
        <circle className="chart__dot" cx={sx(pts[shown].x)} cy={sy(pts[shown].values[measure])} r={4} />
        <rect x={LEFT} y={0} width={W - LEFT - RIGHT} height={H} fill="transparent"
          onPointerMove={onMove} onPointerLeave={() => setActive(null)} />
      </svg>
      <figcaption className="chart__caption" aria-live="polite">
        <strong>{fullNumber(pts[shown].values[measure])}</strong> {name} · {pts[shown].label}
      </figcaption>
    </figure>
  );
}
