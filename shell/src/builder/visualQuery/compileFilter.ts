// SPDX-License-Identifier: Apache-2.0
import type { CollectionFieldType, CollectionSchema } from "../../api/types";

export type FilterOperator = "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "contains";
export type FilterRow = { column: string; operator: FilterOperator; value: string };

export function quoteIdent(name: string): string {
  return `"${name.replace(/"/g, '""')}"`;
}

export function quoteSqlLiteral(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

const OPERATOR_TO_SQL: Record<FilterOperator, string> = {
  eq: "=", neq: "!=", gt: ">", gte: ">=", lt: "<", lte: "<=", contains: "LIKE",
};
const SQL_TO_OPERATOR: Record<string, FilterOperator> = {
  "=": "eq", "!=": "neq", ">": "gt", ">=": "gte", "<": "lt", "<=": "lte", LIKE: "contains",
};

function formatValue(row: FilterRow, fieldType: CollectionFieldType): string {
  if (row.operator === "contains") return quoteSqlLiteral(`%${row.value}%`);
  switch (fieldType) {
    case "integer":
    case "number":
      return row.value; // le formulaire (Task 10) ne laisse saisir que des chiffres pour ces types
    case "boolean":
      return row.value === "true" ? "TRUE" : "FALSE";
    default:
      return quoteSqlLiteral(row.value);
  }
}

// Défense en profondeur (revue finale SP-14o) : le sandbox serveur
// (app.pipelines.expr_validation) bloque déjà toute évasion SQL, mais rien
// ne garantissait côté client qu'une valeur numérique attendue le soit
// vraiment — une valeur non numérique pouvait produire une erreur DuckDB
// opaque, ou pire, une comparaison colonne-à-colonne silencieuse si elle
// coïncidait avec un nom de colonne existant.
export function isFilterRowValueValid(row: FilterRow, schema: CollectionSchema): boolean {
  if (row.value.trim() === "") return false;
  if (row.operator === "contains") return true;
  const fieldType = schema.fields.find((f) => f.name === row.column)?.type;
  if (fieldType === "integer" || fieldType === "number") {
    return /^-?\d+(\.\d+)?$/.test(row.value.trim());
  }
  return true;
}

export function compileFilterRowsToSql(rows: FilterRow[], schema: CollectionSchema): string {
  return rows
    .map((row) => {
      const field = schema.fields.find((f) => f.name === row.column);
      const fieldType = field?.type ?? "string";
      return `${quoteIdent(row.column)} ${OPERATOR_TO_SQL[row.operator]} ${formatValue(row, fieldType)}`;
    })
    .join(" AND ");
}

// Best-effort : ne comprend que la forme exacte produite par
// compileFilterRowsToSql. Toute forme non reconnue (y compris une valeur
// texte contenant littéralement " AND ", cf. test dédié) renvoie null — le
// point d'appel (Task 9/13) traite null comme "pipeline modifié à la main,
// repli vers le canvas complet", un comportement voulu, pas un bug.
export function decompileSqlToFilterRows(expr: string): FilterRow[] | null {
  if (expr === "") return [];
  const clauses = expr.split(" AND ");
  const rows: FilterRow[] = [];
  for (const clause of clauses) {
    const match = clause.match(/^"((?:[^"]|"")+)" (=|!=|>=|<=|>|<|LIKE) (.+)$/);
    if (!match) return null;
    const [, rawColumn, sqlOp, rawValue] = match;
    const column = rawColumn.replace(/""/g, '"');
    const operator = SQL_TO_OPERATOR[sqlOp];
    let value: string;
    if (operator === "contains") {
      const litMatch = rawValue.match(/^'%(.*)%'$/);
      if (!litMatch) return null;
      value = litMatch[1].replace(/''/g, "'");
    } else if (rawValue === "TRUE" || rawValue === "FALSE") {
      value = rawValue === "TRUE" ? "true" : "false";
    } else if (rawValue.startsWith("'")) {
      const litMatch = rawValue.match(/^'(.*)'$/);
      if (!litMatch) return null;
      value = litMatch[1].replace(/''/g, "'");
    } else {
      value = rawValue; // numérique, non quoté
    }
    rows.push({ column, operator, value });
  }
  return rows;
}
