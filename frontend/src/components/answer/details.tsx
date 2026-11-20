// The contents of the panels under an answer — nothing the backend did is hidden:
//  * SqlList: every query the AI wrote, on which database; failed tries are struck through with the
//    database's error (that's the self-correction loop, visible).
//  * ResultTable: the rows that came back (first 200 drawn; the full count is shown), with "Export CSV" (every row).
//  * LabelList: the FDA label passages the answer was based on, with a link to the official label.
//  * Timeline: how long each step took, as hairline bars.

import { useState } from "react";
import { ApiError, getResultPage } from "../../api/client";
import type { DocumentRef, QueryResult, Role, SqlRecord } from "../../api/types";
import { csvFilename, downloadCsv, toCsv } from "../../lib/csv";
import { cleanNames } from "../../lib/names";

const DB_LABEL = { clinical: "clinical_db", billing: "billing_db" } as const;
const MAX_ROWS = 200;
const PAGE = 100; // rows per page from the server

export function SqlList({ sql }: { sql: SqlRecord[] }) {
  return (
    <ol className="sql-list">
      {sql.map((s, i) => (
        <li key={i} className="sql-item" data-failed={s.error ? "true" : "false"}>
          <div className="sql-item__head">
            <span>{DB_LABEL[s.db]}</span>
            <span className="sql-item__try">query {i + 1}{s.error ? " · rejected" : ""}</span>
          </div>
          <pre className="sql-item__code">
            <code>{s.query}</code>
          </pre>
          {s.error && <p className="sql-item__error">{s.error}</p>}
        </li>
      ))}
    </ol>
  );
}

function cell(value: unknown): string {
  if (value === null || value === undefined) return "—";
  if (typeof value === "number") return Number.isInteger(value) ? String(value) : String(Math.round(value * 100) / 100);
  return cleanNames(String(value)); // "Abe604" -> "Abe" (Synthea's random digits)
}

export interface Owner {
  role: Role;
  patientId: string | null;
}

/** The result rows. A big table arrives 100 rows at a time with a ticket (result_id): "Load more" fetches
 *  the next page — only for the person who asked. Tables without a ticket draw at most 200 rows. */
export function ResultTable({ table, owner }: { table: QueryResult; owner?: Owner }) {
  const [rows, setRows] = useState<unknown[][]>(table.rows);
  const [loading, setLoading] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const paged = Boolean(table.result_id && owner);
  const shown = paged ? rows : rows.slice(0, MAX_ROWS);
  const canLoadMore = paged && rows.length < table.total_rows;

  // Export CSV: every row, not just those drawn — pages not loaded yet are fetched first (and shown too).
  const [exporting, setExporting] = useState(false);
  const exportCsv = async () => {
    setExporting(true);
    setProblem(null);
    try {
      let all = rows;
      if (paged) {
        for (let page = Math.floor(all.length / PAGE) + 1; all.length < table.total_rows; page++) {
          const next = await getResultPage(table.result_id!, page, owner!.role, owner!.patientId);
          if (!next.rows.length) break;
          all = [...all, ...next.rows];
        }
        setRows(all);
      }
      downloadCsv(csvFilename(), toCsv(table.columns, all));
    } catch (err) {
      setProblem(err instanceof ApiError ? err.userMessage : "Couldn't export the table.");
    } finally {
      setExporting(false);
    }
  };

  const loadMore = async () => {
    setLoading(true);
    setProblem(null);
    try {
      const page = await getResultPage(table.result_id!, Math.floor(rows.length / PAGE) + 1, owner!.role, owner!.patientId);
      setRows((r) => [...r, ...page.rows]);
    } catch (err) {
      setProblem(err instanceof ApiError ? err.userMessage : "Couldn't load more rows.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="result">
      <div className="result__meta">
        {table.total_rows > shown.length && (
          <span>
            Showing {shown.length.toLocaleString("en-US")} of {table.total_rows.toLocaleString("en-US")}
          </span>
        )}
        {table.truncated && <span className="badge">partial — more rows exist</span>}
        <button type="button" className="chip result__export" onClick={exportCsv} disabled={exporting}
          title={table.truncated ? "Exports the rows Aether kept (the result was cut off)" : "Every row, as a spreadsheet file"}>
          {exporting ? "Exporting…" : "Export CSV"}
        </button>
      </div>
      <div className="result__scroll">
        <table>
          <thead>
            <tr>
              {table.columns.map((c) => (
                <th key={c}>{c}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((row, r) => (
              <tr key={r}>
                {row.map((v, c) => (
                  <td key={c}>{cell(v)}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {canLoadMore && (
        <button type="button" className="chip result__more" onClick={loadMore} disabled={loading}>
          {loading ? "Loading…" : `Load more (${Math.min(PAGE, table.total_rows - rows.length)} rows)`}
        </button>
      )}
      {problem && <p className="result__problem">{problem}</p>}
    </div>
  );
}

export function LabelList({ documents }: { documents: DocumentRef[] }) {
  return (
    <ul className="labels">
      {documents.map((d, i) => (
        <li key={i} className="label">
          <div className="label__head">
            <strong>{d.label.replace(/^openFDA label: /, "")}</strong>
            <a href={d.source_url} target="_blank" rel="noreferrer noopener">
              Open label ↗
            </a>
          </div>
          <p className="label__excerpt">{d.excerpt}</p>
        </li>
      ))}
    </ul>
  );
}

export function Timeline({ timings }: { timings: Record<string, number> }) {
  const entries = Object.entries(timings);
  const max = Math.max(...entries.map(([, t]) => t), 0.001);
  return (
    <ul className="timeline">
      {entries.map(([step, t]) => (
        <li key={step} className="timeline__row">
          <span className="timeline__step">{step}</span>
          <span className="timeline__track">
            <span className="timeline__bar" style={{ width: `${Math.max(2, (t / max) * 100)}%` }} />
          </span>
          <span className="timeline__time">{t.toFixed(2)} s</span>
        </li>
      ))}
    </ul>
  );
}
