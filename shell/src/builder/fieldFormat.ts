// SPDX-License-Identifier: Apache-2.0
import type { CollectionFieldType } from "../api/types";

// D35 (Vague C, SP-C6) : formatage fr-FR des valeurs de champ affichées en
// lecture seule (widget table, popup carte en mode `fields`). Le mode
// `template` d'un popup (gabarit libre `${expr}`) reste hors périmètre —
// cf. commentaire de tête de popupContent.ts et la note de scope du plan.
const NUMBER_FORMAT = new Intl.NumberFormat("fr-FR");
const DATE_FORMAT = new Intl.DateTimeFormat("fr-FR");

export function formatFieldValue(value: unknown, fieldType?: CollectionFieldType): string {
  if (value === null || value === undefined) return "";
  if ((fieldType === "integer" || fieldType === "number") && typeof value === "number") {
    return NUMBER_FORMAT.format(value);
  }
  if ((fieldType === "date" || fieldType === "datetime") && typeof value === "string") {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return DATE_FORMAT.format(parsed);
  }
  return String(value);
}
