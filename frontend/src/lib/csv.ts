// "Export CSV": the result table as a spreadsheet file. Names lose Synthea's random digits, like on screen.
// Text a spreadsheet would run as a formula (=, +, -, @ at the start) gets a leading apostrophe, so a value in the
// data can never become a live formula when the file is opened (CSV injection). Numbers stay numbers.

import { cleanNames } from "./names";

const FORMULA_START = /^[=+\-@\t\r]/;

function field(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "number") return String(value);
  let text = typeof value === "string" ? cleanNames(value) : typeof value === "object" ? JSON.stringify(value) : String(value);
  if (FORMULA_START.test(text)) text = `'${text}`;
  return /[",\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function toCsv(columns: string[], rows: unknown[][]): string {
  return [columns, ...rows].map((row) => row.map(field).join(",") + "\r\n").join("");
}

export function csvFilename(now: Date = new Date()): string {
  const p = (n: number) => String(n).padStart(2, "0");
  return `aether-result-${now.getFullYear()}-${p(now.getMonth() + 1)}-${p(now.getDate())}-${p(now.getHours())}${p(now.getMinutes())}.csv`;
}

/** Hand the file to the browser's download. A byte-order mark makes Excel read it as UTF-8 (names with accents). */
export function downloadCsv(filename: string, csv: string): void {
  const url = URL.createObjectURL(new Blob(["﻿", csv], { type: "text/csv;charset=utf-8" }));
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
