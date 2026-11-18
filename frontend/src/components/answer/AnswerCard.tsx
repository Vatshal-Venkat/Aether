// One reply from Aether. The text rises in block by block; under it, a quiet line with where the
// facts came from and how long it took; then the hairline buttons that open the SQL, the table,
// the drug-label passages and the timeline. If the fact-checker couldn't match some numbers to
// the data, they're listed in a note — never hidden.

import { motion } from "motion/react";
import type { ChatResult } from "../../api/types";
import { useReducedMotion } from "../../hooks/useReducedMotion";
import { renderMarkdown } from "../../lib/markdown";
import { AnswerOrb } from "../orbs/AnswerOrb";
import { Disclosures, type Panel } from "./Disclosure";
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

export function AnswerCard({ result, onOption, owner }: { result: ChatResult; onOption?: (option: string) => void; owner?: Owner }) {
  const reduced = useReducedMotion();
  const total = Object.values(result.timings).reduce((a, b) => a + b, 0);
  const tables = result.sources.filter((s) => !s.startsWith("openFDA label:"));
  const labelCount = result.sources.length - tables.length;
  const meta = [...tables, ...(labelCount ? [`${labelCount} FDA label${labelCount > 1 ? "s" : ""}`] : [])];
  const panels: Panel[] = [];
  if (result.sql.length) panels.push({ id: "sql", title: "SQL", count: String(result.sql.length), content: <SqlList sql={result.sql} /> });
  if (result.table) {
    const n = result.table.total_rows;
    panels.push({ id: "table", title: "Table", count: `${n.toLocaleString("en-US")} row${n === 1 ? "" : "s"}`,
      content: <ResultTable table={result.table} owner={owner} /> });
  }
  if (result.documents.length) {
    panels.push({ id: "labels", title: "Labels", count: String(result.documents.length), content: <LabelList documents={result.documents} /> });
  }
  if (Object.keys(result.timings).length) panels.push({ id: "timeline", title: "Timeline", content: <Timeline timings={result.timings} /> });

  // Word-by-word reveal (the full text is in the page from the start). With "reduce motion" on, the answer
  // appears at once: no word spans at all (final review, Plan 4).
  const blocks = renderMarkdown(cleanAnswer(result.answer, result.sources.length > 0), { reveal: !reduced });
  return (
    <article className="answer" data-kind={result.kind}>
      <AnswerOrb kind={result.kind} />
      <div className="answer__body">
        {KIND_LABEL[result.kind] && <p className="answer__kind">{KIND_LABEL[result.kind]}</p>}
        {result.standalone_question && (
          // How a follow-up was read ("how many of them..." -> the full question), so a wrong reading is visible.
          <p className="answer__understood">
            <span className="answer__understood-label">Understood as</span>
            <span>{result.standalone_question}</span>
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
        {result.kind === "clarification" && (result.options?.length ?? 0) > 0 && (
          <div className="answer__options">
            {result.options!.map((option) => (
              <button key={option} type="button" className="chip" disabled={!onOption} onClick={() => onOption?.(option)}>
                {option}
              </button>
            ))}
          </div>
        )}
        <Disclosures panels={panels} />
      </div>
    </article>
  );
}
