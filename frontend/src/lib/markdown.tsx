// A tiny Markdown reader for answers: paragraphs, bullet/numbered lists, tables, **bold** and
// `code`. That's all the AI uses. It builds React elements (never raw HTML), so even if an answer
// or a drug label contained "<script>", it is shown as plain text and can't run.
//
// With { reveal: true } every word is wrapped in a span numbered in reading order (--i); CSS fades
// them in one after another, so the answer appears word by word. The whole text is in the page from
// the start, so screen readers and copy/paste get all of it at once.

import type { CSSProperties, ReactNode } from "react";

/** A drug's FDA label: the first time the answer names the drug, a small "label ↗" link follows the name. */
export interface LabelLink {
  name: string; // e.g. "Hydrochlorothiazide" or "Metoprolol Succinate"
  url: string;
}

interface Ctx {
  reveal: boolean;
  next: number; // the next word's position in reading order
  labels: { link: LabelLink; pattern: RegExp }[];
  linked: Set<string>; // drugs already given a link (only the first mention gets one)
}

const escapeRe = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

/** The name as written in full, or by its first word when that is distinctive ("Metoprolol Succinate" -> "metoprolol"). */
function labelPattern(name: string): RegExp {
  const first = name.split(/\s+/)[0];
  const forms = [name, ...(first.length >= 5 && first !== name ? [first] : [])].map(escapeRe);
  return new RegExp(`\\b(?:${forms.join("|")})\\b`, "i");
}

/** Where the next not-yet-linked drug is named in this text: [end of the name, link], or null. */
function nextLabel(text: string, ctx: Ctx): [number, LabelLink] | null {
  let best: [number, number, LabelLink] | null = null;
  for (const { link, pattern } of ctx.labels) {
    if (ctx.linked.has(link.name)) continue;
    const m = pattern.exec(text);
    if (m && (!best || m.index < best[0])) best = [m.index, m.index + m[0].length, link];
  }
  return best && [best[1], best[2]];
}

function labelChip(link: LabelLink, key: string): ReactNode {
  return (
    <a key={key} className="label-chip" href={link.url} target="_blank" rel="noreferrer noopener"
       title={`Open the FDA label for ${link.name}`} aria-label={`FDA label for ${link.name}`}>
      label ↗
    </a>
  );
}

/** Plain text with a label link after each drug's first mention. */
function linked(text: string, keyBase: string, ctx: Ctx, render: (t: string, k: string) => ReactNode[]): ReactNode[] {
  const out: ReactNode[] = [];
  let rest = text;
  for (let n = 0; ; n++) {
    const hit = nextLabel(rest, ctx);
    if (!hit) return [...out, ...render(rest, `${keyBase}t${n}`)];
    const [end, link] = hit;
    ctx.linked.add(link.name);
    out.push(...render(rest.slice(0, end), `${keyBase}t${n}`), " ", labelChip(link, `${keyBase}c${n}`));
    rest = rest.slice(end);
  }
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
      // "**hydrochlorothiazide**": the link goes after the bold name, not inside it.
      const bold = part.slice(2, -2);
      const chips: ReactNode[] = [];
      for (let hit = nextLabel(bold, ctx), n = 0; hit; hit = nextLabel(bold, ctx), n++) {
        ctx.linked.add(hit[1].name);
        chips.push(" ", labelChip(hit[1], `${key}c${n}`));
      }
      return [<strong key={key}>{words(bold, key, ctx)}</strong>, ...chips];
    }
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2) {
      return [<code key={key}>{words(part.slice(1, -1), key, ctx)}</code>];
    }
    return linked(part, key, ctx, (t, k) => words(t, k, ctx));
  });
}

const cells = (line: string) => line.trim().replace(/^\||\|$/g, "").split("|").map((c) => c.trim());
const isDivider = (line: string) => /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(line);
const BULLET = /^\s*[-*•]\s+/;
const NUMBERED = /^\s*\d+[.)]\s+/;

export function renderMarkdown(text: string, options: { reveal?: boolean; labels?: LabelLink[] } = {}): ReactNode[] {
  const labels = [...(options.labels ?? [])].sort((a, b) => b.name.length - a.name.length);
  const ctx: Ctx = { reveal: options.reveal ?? false, next: 0, linked: new Set(),
                     labels: labels.map((link) => ({ link, pattern: labelPattern(link.name) })) };
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
