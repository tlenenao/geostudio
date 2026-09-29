// SPDX-License-Identifier: Apache-2.0
export type ParsedDuckDbError = {
  category: string | null;
  message: string;
  line: number | null;
  column: number | null;
  sqlSnippet: string | null;
};

// Format DuckDB (vérifié empiriquement, spec Vague C §SP-C5) :
// "<Catégorie> Error: <message>\n\nLINE <n>: <sql tronqué>\n<espaces>^"
// La position du "^" (2e ligne suivant LINE) donne la colonne (1-indexée).
const HEADER_RE = /^([A-Za-z ]+ Error): (.*?)(?:\n\n|$)/s;
const LINE_RE = /^LINE (\d+): (.*)$/m;

export function parseDuckDbError(message: string): ParsedDuckDbError {
  const headerMatch = HEADER_RE.exec(message);
  const lineMatch = LINE_RE.exec(message);
  if (!headerMatch || !lineMatch) {
    return { category: null, message, line: null, column: null, sqlSnippet: null };
  }
  const lineIndex = message.indexOf(lineMatch[0]);
  const afterLine = message.slice(lineIndex + lineMatch[0].length);
  const caretMatch = /\n(\s*)\^/.exec(afterLine);
  const column = caretMatch ? caretMatch[1].length + 1 : null;
  return {
    category: headerMatch[1],
    message: headerMatch[2].trim(),
    line: Number(lineMatch[1]),
    column,
    sqlSnippet: lineMatch[2],
  };
}
