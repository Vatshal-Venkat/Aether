// Synthea, which made our fake patients, adds random digits to every name ("Lyndon118 Bechtelar572") so
// no record is mistaken for a real person. The digits mean nothing, so the website hides them:
// "Lyndon Bechtelar". Display only: the database, the SQL panel and anything sent back keep the original.
//
// A name word is a capital letter, then lower-case letters (accents included: Raúl, Zoë; with ' or - inside,
// e.g. O'Keefe, Ward-Smith), then digits glued straight on. Codes don't look like that and are left alone:
// A1c, B12, COVID-19, E11.9. (JavaScript's \b only knows A-Z, so letters are checked with \p{L} instead.)

const NAME_WITH_DIGITS = /(?<![\p{L}\d])(\p{Lu}\p{Ll}+(?:['’-]\p{L}+)*)\d+(?![\p{L}\d])/gu;

export function cleanNames(text: string): string {
  return text.replace(NAME_WITH_DIGITS, "$1");
}
