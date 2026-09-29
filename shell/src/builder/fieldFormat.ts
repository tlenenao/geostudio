// SPDX-License-Identifier: Apache-2.0
import type { CollectionFieldType } from "../api/types";

// D35 (Vague C, SP-C6) : formatage fr-FR des valeurs de champ affichées en
// lecture seule (widget table, popup carte en mode `fields`). Le mode
// `template` d'un popup (gabarit libre `${expr}`) reste hors périmètre —
// cf. commentaire de tête de popupContent.ts et la note de scope du plan.
//
// Revue finale Vague C (point 5), 4 défauts corrigés :
//  - `datetime` ne montrait que la date : `Intl.DateTimeFormat("fr-FR")`
//    sans options n'inclut ni heure ni minute — l'heure disparaissait
//    silencieusement. Formaté à part via `toLocaleString("fr-FR")`, même
//    convention que le reste du dépôt (ConfigHistoryPanel,
//    PipelineRunPanel, ReportRunPanel, NotificationBell…) ;
//  - `Intl.NumberFormat` limite par défaut à 3 décimales
//    (`maximumFractionDigits` implicite) — une valeur géospatiale (aire,
//    coordonnée dérivée…) plus précise était tronquée sans avertissement.
//    Relevé à 6 décimales (précision centimétrique pour une coordonnée
//    WGS84) ;
//  - `new Date("YYYY-MM-DD")` (un champ `date`, sans heure) est interprété
//    comme minuit **UTC** par la spec ECMA-262 — dans un fuseau à décalage
//    négatif (ex. America/New_York), le formatage en heure locale affichait
//    la veille (décalage d'un jour, vérifié : "26/09/2026" au lieu de
//    "27/09/2026"). Parsé désormais composant par composant en minuit
//    *local*, qui n'a pas ce défaut puisqu'aucune conversion de fuseau
//    n'intervient ;
//  - un entier "année" (ex. 2024) recevait un séparateur de milliers
//    (`Intl.NumberFormat` groupe par défaut) — jamais souhaité pour une
//    année calendaire. Heuristique volontairement étroite (entier à 4
//    chiffres dans une plage d'années plausible) : `CollectionFieldType` ne
//    porte aucun type "year" dédié, donc un compteur entier à 4 chiffres
//    perd aussi son séparateur dans ce cas précis — coût jugé négligeable
//    (un entier à 4 chiffres reste lisible sans séparateur) face au gain.
const NUMBER_FORMAT = new Intl.NumberFormat("fr-FR", { maximumFractionDigits: 6 });
const YEAR_FORMAT = new Intl.NumberFormat("fr-FR", { useGrouping: false });
const DATE_FORMAT = new Intl.DateTimeFormat("fr-FR");

const PLAUSIBLE_YEAR_MIN = 1000;
const PLAUSIBLE_YEAR_MAX = 9999;

function looksLikeCalendarYear(value: number): boolean {
  return Number.isInteger(value) && value >= PLAUSIBLE_YEAR_MIN && value <= PLAUSIBLE_YEAR_MAX;
}

const DATE_ONLY_PATTERN = /^(\d{4})-(\d{2})-(\d{2})$/;

export function formatFieldValue(value: unknown, fieldType?: CollectionFieldType): string {
  if (value === null || value === undefined) return "";
  if ((fieldType === "integer" || fieldType === "number") && typeof value === "number") {
    if (fieldType === "integer" && looksLikeCalendarYear(value)) return YEAR_FORMAT.format(value);
    return NUMBER_FORMAT.format(value);
  }
  if (fieldType === "date" && typeof value === "string") {
    const dateOnly = DATE_ONLY_PATTERN.exec(value);
    if (dateOnly) {
      const [, y, m, d] = dateOnly;
      const localMidnight = new Date(Number(y), Number(m) - 1, Number(d));
      return DATE_FORMAT.format(localMidnight);
    }
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return DATE_FORMAT.format(parsed);
  }
  if (fieldType === "datetime" && typeof value === "string") {
    const parsed = new Date(value);
    if (!Number.isNaN(parsed.getTime())) return parsed.toLocaleString("fr-FR");
  }
  return String(value);
}
