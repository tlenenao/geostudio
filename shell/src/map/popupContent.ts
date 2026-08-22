// SPDX-License-Identifier: Apache-2.0
import type { ExprContext } from "../builder/expr";
import type { PopupConfig } from "../api/types";
import { renderPopupTemplate, stringifyObject } from "./popupTemplate";

export type PopupRow = { label: string; value: string };
export type PopupContent = { title: string | null; rows: PopupRow[]; html: string | null };

const EMPTY = "—";

// Durcissement identique à `stringify()` de popupTemplate.ts (cf. son
// commentaire) : un popup doit se dégrader, jamais planter la carte, même
// sur une valeur non sérialisable (structure circulaire, `toJSON` qui lève).
function display(value: unknown): string {
  if (value === null || value === undefined) return EMPTY;
  if (typeof value === "object") return stringifyObject(value);
  return String(value);
}

// Résolution d'un PopupConfig contre les propriétés de l'entité cliquée.
// Deux modes exclusifs : gabarit (s'il est non vide) ou liste de champs.
// Sans configuration du tout : tous les champs présents, dans leur ordre.
export function resolvePopupContent(
  config: PopupConfig | undefined,
  properties: Record<string, unknown>,
  ctx: Omit<ExprContext, "record">,
): PopupContent {
  const template = config?.template?.trim();
  if (template) {
    return {
      title: null,
      rows: [],
      html: renderPopupTemplate(template, { ...ctx, record: properties }),
    };
  }
  const names = config?.fields?.length
    ? config.fields.filter((f) => f.name in properties).map((f) => f.name)
    : Object.keys(properties);
  const labels = new Map((config?.fields ?? []).map((f) => [f.name, f.label]));
  return {
    title:
      config?.titleField && config.titleField in properties
        ? display(properties[config.titleField])
        : null,
    rows: names
      .filter((n) => n !== config?.titleField)
      .map((n) => ({ label: labels.get(n) || n, value: display(properties[n]) })),
    html: null,
  };
}
