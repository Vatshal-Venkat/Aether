// Automatic charts: does a result table make a useful chart, and which one?
//   * names/categories + a number  -> horizontal bars, in the result's own order (the SQL already sorted it);
//   * dates or years + a number    -> a line, sorted by time (needs at least 3 points);
//   * anything else (one number, no numbers, repeated labels, only ids) -> no chart; the table and the answer say it.
// Ids, codes and rank columns are never plotted as amounts. Several number columns -> one at a time, to choose from.

import type { QueryResult } from "../api/types";
import { cleanNames } from "./names";

export const MAX_BARS = 20;

export interface ChartPoint {
  label: string;
  x: number;        // position in time (lines); the row's place (bars)
  values: number[]; // one per measure
}

export interface ChartSpec {
  kind: "bar" | "line";
  label: string;     // the column the labels come from
  measures: string[];
  points: ChartPoint[];
  total: number;     // rows in the result (bars show at most MAX_BARS)
}

const ID_NAME = /(^|_)(id|uuid)$|^id$|code$/i;
const RANK_NAME = /^(rank|ranking|row_?num(ber)?|position)$/i;
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const NUMBER_TEXT = /^-?\d+(\.\d+)?$/;
const DATE_TEXT = /^\d{4}(-\d{2}(-\d{2}([T ][\d:.]+Z?)?)?)?$/;

const present = (values: unknown[]) => values.filter((v) => v !== null && v !== undefined);
const isNumberLike = (v: unknown) => typeof v === "number" || (typeof v === "string" && NUMBER_TEXT.test(v.trim()));
const toNumber = (v: unknown) => (v === null || v === undefined ? 0 : Number(v));

function isYearColumn(name: string, values: unknown[]): boolean {
  return /year/i.test(name) && present(values).every((v) => Number.isInteger(Number(v)) && +v! >= 1800 && +v! <= 2200);
}

function timeOf(value: unknown): number {
  const s = String(value).trim();
  const iso = /^\d{4}$/.test(s) ? `${s}-01-01` : /^\d{4}-\d{2}$/.test(s) ? `${s}-01` : s;
  return Date.parse(iso);
}

export function chartSpec(table: QueryResult): ChartSpec | null {
  const { columns, rows } = table;
  if (rows.length < 2) return null;
  const column = (i: number) => rows.map((r) => r[i]);
  const numeric = columns.map((_, i) => present(column(i)).length > 0 && present(column(i)).every(isNumberLike));
  const years = columns.map((c, i) => numeric[i] && isYearColumn(c, column(i)));

  // The label: the first text column that isn't an id; failing that, a year column.
  let labelIndex = columns.findIndex((c, i) => !numeric[i] && !ID_NAME.test(c)
    && !present(column(i)).every((v) => typeof v === "string" && UUID.test(v)));
  if (labelIndex < 0) labelIndex = years.findIndex(Boolean);
  if (labelIndex < 0) return null;

  const measureIndexes = columns.map((_, i) => i)
    .filter((i) => i !== labelIndex && numeric[i] && !years[i] && !ID_NAME.test(columns[i]) && !RANK_NAME.test(columns[i]));
  if (!measureIndexes.length) return null;

  const labels = column(labelIndex).map((v) => (v === null || v === undefined ? "—" : String(v)));
  if (new Set(labels).size !== labels.length) return null; // repeated labels: one bar each would mislead

  const timeLike = years[labelIndex] || labels.every((l) => DATE_TEXT.test(l.trim()) && !Number.isNaN(timeOf(l)));
  const points: ChartPoint[] = rows.map((row, r) => ({
    label: timeLike ? labels[r].slice(0, 10) : cleanNames(labels[r]),
    x: timeLike ? timeOf(labels[r]) : r,
    values: measureIndexes.map((i) => toNumber(row[i])),
  }));
  const base = { label: columns[labelIndex], measures: measureIndexes.map((i) => columns[i]), total: rows.length };
  if (timeLike && points.length >= 3) return { kind: "line", ...base, points: points.sort((a, b) => a.x - b.x) };
  return { kind: "bar", ...base, points: points.slice(0, MAX_BARS) };
}

/** Round tick values covering [min, max]: 0, 20, 40... (about 5 steps of 1, 2 or 5 x a power of ten). */
export function niceTicks(min: number, max: number, steps = 5): number[] {
  const range = max - min || Math.abs(max) || 1;
  const raw = range / steps;
  const power = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= raw) ?? 10 * power;
  const ticks: number[] = [];
  for (let v = Math.floor(min / step) * step; v <= Math.ceil(max / step) * step + step / 2; v += step) {
    ticks.push(Number(v.toPrecision(12)));
  }
  return ticks;
}

/** 1,284 / 12.9K / 4.2M — for axis ticks. */
export function compact(n: number): string {
  return new Intl.NumberFormat("en-US", { notation: Math.abs(n) >= 10000 ? "compact" : "standard", maximumFractionDigits: 1 }).format(n);
}

/** Full value for labels and tooltips: 2,313.07 */
export function fullNumber(n: number): string {
  return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
}
