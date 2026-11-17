// The contents of the panels under an answer — nothing the backend did is hidden:
//  * SqlList: every query the AI wrote, on which database; failed tries are struck through with the
//    database's error (that's the self-correction loop, visible).
//  * ResultTable: the rows that came back (first 200 drawn; the full count is shown).
//  * LabelList: the FDA label passages the answer was based on, with a link to the official label.
//  * Timeline: how long each step took, as hairline bars.

import type { DocumentRef, QueryResult, SqlRecord } from "../../api/types";

const DB_LABEL = { clinical: "clinical_db", billing: "billing_db" } as const;
const MAX_ROWS = 200;

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
  return String(value);
}

export function ResultTable({ table }: { table: QueryResult }) {
  const shown = table.rows.slice(0, MAX_ROWS);
  return (
    <div className="result">
      <div className="result__meta">
        {table.total_rows > MAX_ROWS && (
          <span>
            Showing {MAX_ROWS} of {table.total_rows.toLocaleString("en-US")}
          </span>
        )}
        {table.truncated && <span className="badge">partial — more rows exist</span>}
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
