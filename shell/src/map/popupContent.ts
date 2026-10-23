// SPDX-License-Identifier: Apache-2.0
import type { CollectionSchemaField, PopupConfig } from "../api/types";
import type { ExprContext } from "../builder/expr";
import { renderPopupTemplate, stringifyObject } from "./popupTemplate";
import { formatFieldValue } from "../builder/fieldFormat";

export type PopupRow = { label: string; value: string };
export type PopupContent = { title: string | null; rows: PopupRow[]; html: string | null };

const EMPTY = "—";

// Résolution d'un PopupConfig contre les propriétés de l'entité cliquée.
// Deux modes exclusifs : gabarit (s'il est non vide) ou liste de champs.
// Sans configuration du tout : tous les champs présents, dans leur ordre.
//
// Contexte CEL (`vars`/`user`/`ctx`) : optionnel, fourni par le widget carte
// d'app (AUD-052, prop `popupContext` de MapView) ; l'éditeur autonome et
// l'explorateur n'en ont pas, leur seul vocabulaire reste `record.*`.
//
// D35 (Vague C, SP-C6) : le formatage fr-FR (`formatFieldValue`) ne
// s'applique qu'au mode `fields` ci-dessous — jamais au gabarit libre
// `template` (`renderPopupTemplate`), hors périmètre de cette tâche
// (décision de scope documentée dans le plan SP-C6).
export function resolvePopupContent(
  config: PopupConfig | undefined,
  properties: Record<string, unknown>,
  schema?: CollectionSchemaField[],
  // AUD-052 : contexte d'expression de l'hôte (variables d'app, utilisateur, contexte
  // analytique) ; `record` reste toujours l'entité cliquée.
  exprContext?: Omit<ExprContext, "record">,
): PopupContent {
  const fieldTypes = new Map((schema ?? []).map((f) => [f.name, f.type] as const));
  // Durcissement identique à `stringify()` de popupTemplate.ts (cf. son
  // commentaire) : un popup doit se dégrader, jamais planter la carte, même
  // sur une valeur non sérialisable (structure circulaire, `toJSON` qui
  // lève). `fieldName` absent (ex. appel interne sans nom de champ connu) :
  // comportement `String(value)` historique via `formatFieldValue`.
  function display(value: unknown, fieldName?: string): string {
    if (value === null || value === undefined) return EMPTY;
    if (typeof value === "object") return stringifyObject(value);
    return fieldName ? formatFieldValue(value, fieldTypes.get(fieldName)) : String(value);
  }
  const template = config?.template?.trim();
  if (template) {
    return {
      title: null,
      rows: [],
      html: renderPopupTemplate(template, {
        vars: {},
        user: { name: "" },
        ...exprContext,
        record: properties,
      }),
    };
  }
  // Présence de `fields`, pas sa longueur : `fields: []` est un choix
  // délibéré de l'auteur (« aucun champ »), à distinguer de l'absence de
  // clé (« pas encore configuré, tout afficher »). Une confusion des deux
  // ferait ressortir des propriétés internes qu'un auteur a explicitement
  // voulu masquer sur une carte ou un site publics.
  const names = config?.fields
    ? config.fields.filter((f) => f.name in properties).map((f) => f.name)
    : Object.keys(properties);
  const labels = new Map((config?.fields ?? []).map((f) => [f.name, f.label]));
  return {
    title:
      config?.titleField && config.titleField in properties
        ? display(properties[config.titleField], config.titleField)
        : null,
    rows: names
      .filter((n) => n !== config?.titleField)
      .map((n) => ({ label: labels.get(n) || n, value: display(properties[n], n) })),
    html: null,
  };
}
