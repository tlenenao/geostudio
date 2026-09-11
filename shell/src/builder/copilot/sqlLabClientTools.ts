// SPDX-License-Identifier: Apache-2.0
// Outil CLIENT du copilote sur SQL Lab (GAP-17) — insère un brouillon SQL
// dans l'éditeur, jamais exécuté. Même patron que clientTools.ts (builder).
type ClientToolSchema = { name: string; description: string; inputSchema: Record<string, unknown> };

export function buildSqlLabClientToolSchemas(): ClientToolSchema[] {
  return [
    {
      name: "applySqlDraft",
      description:
        "Insère une requête SQL générée comme brouillon dans l'éditeur SQL Lab. " +
        "Ne l'exécute jamais — l'utilisateur doit cliquer sur Exécuter.",
      inputSchema: {
        type: "object",
        properties: { sql: { type: "string", description: "Requête SQL brouillon" } },
        required: ["sql"],
      },
    },
  ];
}
