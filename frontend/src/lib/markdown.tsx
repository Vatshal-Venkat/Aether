// A tiny Markdown reader for answers: paragraphs, bullet/numbered lists, tables, **bold** and
// `code`. That's all the AI uses. It builds React elements (never raw HTML), so even if an answer
// or a drug label contained "<script>", it is shown as plain text and can't run.
//
// With { reveal: true } every word is wrapped in a span numbered in reading order (--i); CSS fades
// them in one after another, so the answer appears word by word. The whole text is in the page from
// the start, so screen readers and copy/paste get all of it at once.

import type { CSSProperties, ReactNode } from "react";

interface Ctx {
  reveal: boolean;
  next: number; // the next word's position in reading order
}

function words(text: string, keyBase: string, ctx: Ctx): ReactNode[] {
  if (!ctx.reveal) return [text];
  return text
    .split(/(\s+)/)
    .filter(Boolean)
    .map((piece, i) =>
      /^\s+$/.test(piece) ? (
        piece
      ) : (
        <span key={`${keyBase}w${i}`} className="w" style={{ "--i": ctx.next++ } as CSSProperties}>
          {piece}
        </span>
      ),
    );
}

function inline(text: string, keyBase: string, ctx: Ctx): ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean);
  return parts.flatMap((part, i): ReactNode[] => {
    const key = `${keyBase}-${i}`;
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return [<strong key={key}>{words(part.slice(2, -2), key, ctx)}</strong>];
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return [<code key={key}>{words(part.slice(1, -1), key, ctx)}</code>];
    }
    return words(part, key, ctx);
  });
}

const cells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
const isDivider = (line: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);
const BULLET = /^\s*[-*•]\s+/;
const NUMBERED = /^\s*\d+[.)]\s+/;

export function renderMarkdown(text: string, options: { reveal?: boolean } = {}): ReactNode[] {
  const ctx: Ctx = { reveal: options.reveal ?? false, next: 0 };
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  const blocks: ReactNode[] = [];
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    const key = `b${i}`;
    if (!line.trim()) {
      i++;
      continue;
    }
    if (line.trim().startsWith("|") && i + 1 < lines.length && isDivider(lines[i + 1])) {
      const head = cells(line);
      const body: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) body.push(cells(lines[i++]));
      blocks.push(
        <div className="md-table" key={key}>
          <table>
            <thead>
              <tr>{head.map((c, j) => <th key={j}>{inline(c, `${key}h${j}`, ctx)}</th>)}</tr>
            </thead>
            <tbody>
              {body.map((row, r) => (
                <tr key={r}>{row.map((c, j) => <td key={j}>{inline(c, `${key}r${r}c${j}`, ctx)}</td>)}</tr>
              ))}
            </tbody>
          </table>
        </div>,
      );
      continue;
    }
    let listed = false;
    for (const [pattern, Tag] of [[BULLET, "ul"], [NUMBERED, "ol"]] as const) {
      if (pattern.test(line)) {
        const items: string[] = [];
        while (i < lines.length && pattern.test(lines[i])) items.push(lines[i++].replace(pattern, ""));
        blocks.push(<Tag key={key}>{items.map((it, j) => <li key={j}>{inline(it, `${key}i${j}`, ctx)}</li>)}</Tag>);
        listed = true;
        break;
      }
    }
    if (listed) continue;
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !BULLET.test(lines[i]) && !NUMBERED.test(lines[i])
           && !(lines[i].trim().startsWith("|") && i + 1 < lines.length && isDivider(lines[i + 1]))) {
      para.push(lines[i++].trim());
    }
    blocks.push(
      <p key={key}>
        {para.flatMap((p, j) => (j ? [<br key={`${key}br${j}`} />, ...inline(p, `${key}l${j}`, ctx)] : inline(p, `${key}l${j}`, ctx)))}
      </p>,
    );
  }
  return blocks;
}
