// Trigram similarity — how alike two spellings are (the same method as the backend's app/search/trigram.py and
// PostgreSQL's pg_trgm). Each word is cut into overlapping 3-letter pieces ("  a", " an", "ang", ...); the score is
// shared pieces / all distinct pieces: 1 = identical, near 0 = unrelated. A typo changes only a few pieces, so
// "angelin haris" still scores well against "Angelyn Harris". Runs in the browser in well under a millisecond.

function trigrams(text: string): Set<string> {
  const grams = new Set<string>();
  for (const word of text.toLowerCase().match(/[\p{L}\d]+/gu) ?? []) {
    const padded = `  ${word} `;
    for (let i = 0; i + 3 <= padded.length; i++) grams.add(padded.slice(i, i + 3));
  }
  return grams;
}

export function similarity(a: string, b: string): number {
  const ta = trigrams(a);
  const tb = trigrams(b);
  if (!ta.size || !tb.size) return 0;
  let shared = 0;
  for (const g of ta) if (tb.has(g)) shared++;
  return shared / (ta.size + tb.size - shared);
}
