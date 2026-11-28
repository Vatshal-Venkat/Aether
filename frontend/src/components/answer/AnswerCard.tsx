// One reply from Aether. The text rises in block by block; under it, a quiet line with where the
// facts came from and how long it took; then the hairline buttons that open the SQL, the table,
// the drug-label passages and the timeline. If the fact-checker couldn't match some numbers to
// the data, they're listed in a note — never hidden.

import { motion } from "motion/react";
import { useState } from "react";
import type { ChatResult, DocumentRef } from "../../api/types";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import { type LabelLink, renderMarkdown } from "../../lib/markdown";
import { cleanNames } from "../../lib/names";
import { AnswerOrb } from "../orbs/AnswerOrb";
import { Disclosures, type Panel } from "./Disclosure";
import { chartSpec } from "../../lib/chart";
import { Chart } from "./Chart";
import { LabelList, type Owner, ResultTable, SqlList, Timeline } from "./details";
import "./answer.css";

const KIND_LABEL = { answer: "", clarification: "A quick question", refusal: "Not allowed", out_of_scope: "Out of scope", error: "Couldn't answer" };

/** The AI ends answers with its own "Source: ..." line and sometimes adds 【1】 markers; the meta line
 *  under the answer already shows the sources, so both are dropped from the displayed text. */
export function cleanAnswer(text: string, hasSources: boolean): string {
  // The backend appends "⚠ Some numbers ... could not be matched"; the card shows its own note instead.
  let out = text.replace(/\n*⚠ Some numbers in this answer could not be matched[^\n]*$/, "").replace(/\s*【\d+】/g, "");
  if (hasSources) {
    const lines = out.trimEnd().split("\n");
    // Only a line that IS a source list ("Source:", "**Sources:**") — the colon is required, so
    // "Sources of the balance: ..." or "Sourced from the label ..." stay (final review).
    const isSourceLine = (line: string) => /^\s*(\*\*)?sources?(\*\*)?\s*:/i.test(line);
    while (lines.length > 1 && (isSourceLine(lines[lines.length - 1]) || !lines[lines.length - 1].trim())) {
      lines.pop();
    }
    out = lines.join("\n");
  }
  return out;
}

/** "openFDA label: Hydrochlorothiazide — Side effects" -> "Hydrochlorothiazide". */
export const labelDrug = (label: string) => label.replace(/^openFDA label: /, "").split(" — ")[0].trim();

/** One link per drug (its first label), for the "label ↗" links in the answer text. */
export function labelLinks(documents: DocumentRef[]): LabelLink[] {
  const seen = new Map<string, LabelLink>();
  for (const d of documents) {
    const name = labelDrug(d.label);
    if (name && !seen.has(name.toLowerCase())) seen.set(name.toLowerCase(), { name, url: d.source_url });
  }
  return [...seen.values()];
}

/** Labels of drugs the answer names come first, in the order the answer names them; the rest keep their order. */
export function mentionedFirst(documents: DocumentRef[], answer: string): DocumentRef[] {
  const text = answer.toLowerCase();
  const position = (d: DocumentRef) => {
    const name = labelDrug(d.label).toLowerCase();
    const first = name.split(/\s+/)[0];
    const at = [name, ...(first.length >= 5 ? [first] : [])].map((n) => text.indexOf(n)).filter((i) => i >= 0);
    return at.length ? Math.min(...at) : Infinity;
  };
  return documents.map((d, i) => ({ d, i, p: position(d) })).sort((a, b) => a.p - b.p || a.i - b.i).map((x) => x.d);
}

export function AnswerCard({ result, onOption, owner }: { result: ChatResult; onOption?: (option: string) => void; owner?: Owner }) {
  const reduced = useReducedMotion();
  const [declined, setDeclined] = useState(false);
  // An option may carry the exact question it sends ("Yes" -> "...side effects of metformin?"); "" means it sends
  // nothing ("No" to "did you mean metformin?") — the person simply asks again. Without a mapping, the label is sent.
  const choose = (option: string) => {
    const question = result.option_questions?.[option];
    if (question === "") setDeclined(true);
    else onOption?.(question ?? option);
  };
  const total =Object.values(result.timings).reduce((a, b) => a + b, 0);
  const tables = result.sources.filter((s) => !s.startsWith("openFDA label:"));
  const labelCount = result.sources.length - tables.length;
  const meta = [...tables, ...(labelCount ? [`${labelCount} FDA label${labelCount > 1 ? "s" : ""}`] : [])];
  const panels: Panel[] = [];
  if (result.sql.length) panels.push({ id: "sql", title: "SQL", count: String(result.sql.length), content: <SqlList sql={result.sql} /> });
  if (result.table) {
    const n = result.table.total_rows;
    panels.push({ id: "table", title: "Table", count: `${n.toLocaleString("en-US")} row${n === 1 ? "" : "s"}`,
      content: <ResultTable table={result.table} owner={owner} /> });
    // Names + numbers or dates + numbers: a chart, drawn automatically (lib/chart.ts decides).
    const spec = chartSpec(result.table);
    if (spec) panels.push({ id: "chart", title: "Chart", content: <Chart spec={spec} /> });
  }
  if (result.documents.length) {
    panels.push({ id: "labels", title: "Labels", count: String(result.documents.length),
      content: <LabelList documents={mentionedFirst(result.documents, result.answer)} /> });
  }
  if (Object.keys(result.timings).length) panels.push({ id: "timeline", title: "Timeline", content: <Timeline timings={result.timings} /> });

  // Word-by-word reveal (the full text is in the page from the start). With "reduce motion" on, the answer
  // appears at once: no word spans at all (final review, Plan 4).
  const blocks = renderMarkdown(cleanNames(cleanAnswer(result.answer, result.sources.length > 0)),
    { reveal: !reduced, labels: labelLinks(result.documents) });
  return (
    <article className="answer" data-kind={result.kind}>
      <AnswerOrb kind={result.kind} />
      <div className="answer__body">
        {result.model_notice && (
          // A backup AI model wrote this answer (the main one hit its daily limit): say so, plainly.
          <p className="answer__notice" role="status" aria-label="Model notice">{result.model_notice}</p>
        )}
        {KIND_LABEL[result.kind] && <p className="answer__kind">{KIND_LABEL[result.kind]}</p>}
        {result.standalone_question && (
          // How a follow-up was read ("how many of them..." -> the full question), so a wrong reading is visible.
          <p className="answer__understood">
            <span className="answer__understood-label">Understood as</span>
            <span>{cleanNames(result.standalone_question)}</span>
          </p>
        )}
        <div className="answer__text">
          {blocks.map((block, i) => (
            <motion.div
              key={i}
              initial={reduced ? { opacity: 0 } : { opacity: 0, y: 8, filter: "blur(6px)" }}
              animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
              transition={{ duration: 0.55, delay: 0.08 + i * 0.07, ease: [0.22, 1, 0.36, 1] }}
            >
              {block}
            </motion.div>
          ))}
        </div>
        {result.unverified_numbers.length > 0 && (
          <p className="answer__warning">
            These numbers could not be matched to the data:{" "}
            {result.unverified_numbers.map((n, i) => (
              <span key={i} className="answer__unverified">
                {n}
              </span>
            ))}
          </p>
        )}
        {(meta.length > 0 || total > 0) && (
          <motion.p className="answer__meta" initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.3, duration: 0.6 }}>
            {meta.map((s, i) => (
              <span key={s}>
                {i > 0 && <span className="answer__sep"> · </span>}
                <span>{s}</span>
              </span>
            ))}
            {result.saved_query && !result.cached && (
              <>
                {meta.length > 0 && <span className="answer__sep"> · </span>}
                <span title="Asked before: Aether ran the same SQL as the first time, so the numbers stay the same.">
                  same query as before
                </span>
              </>
            )}
            {result.cached && (
              <>
                {meta.length > 0 && <span className="answer__sep"> · </span>}
                <span>from cache</span>
              </>
            )}
            {total > 0 && !result.cached && ( // a cached answer's timings belong to the original run
              <>
                {meta.length > 0 && <span className="answer__sep"> · </span>}
                <span>{`${total.toFixed(1)} s`}</span>
              </>
            )}
          </motion.p>
        )}
        {(result.options?.length ?? 0) > 0 && ( // a clarifying question's options, or example questions
          <div className="answer__options">
            {result.options!.map((option) => (
              <button key={option} type="button" className="chip" disabled={!onOption || declined} onClick={() => choose(option)}>
                {cleanNames(option)}
              </button>
            ))}
          </div>
        )}
        {declined && <p className="answer__declined">No problem — ask your question again.</p>}
        {result.from_history && (
          <p className="answer__history">Saved answer · tables and SQL aren't kept — ask again to see them.</p>
        )}
        <Disclosures panels={panels} />
      </div>
    </article>
  );
}
