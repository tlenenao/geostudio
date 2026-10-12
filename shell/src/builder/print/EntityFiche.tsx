// SPDX-License-Identifier: Apache-2.0
// ARC-26/ARC-30 : fiche d'une entité, partagée par le widget « Fiche d'entité »
// et par les pages de l'atlas. Chaque libellé de champ est un gabarit CEL
// `${record.nom}` (même syntaxe que les popups) ; rendu en texte React, jamais
// en HTML. Sans `fields`, toutes les propriétés de l'entité sont listées.
import type { DataRecord } from "../../api/types";
import { interpolatePopupTemplate } from "../../map/popupTemplate";
import type { ExprContext } from "../expr";

export type FicheField = { label: string; template: string };

export function EntityFiche({
  record,
  titleTemplate,
  fields,
  exprContext,
}: {
  record: DataRecord;
  titleTemplate?: string;
  fields?: FicheField[];
  exprContext?: Partial<ExprContext>;
}) {
  const ctx: ExprContext = {
    vars: {},
    user: { name: "" },
    ...exprContext,
    record: record.properties,
  };
  const title = titleTemplate ? interpolatePopupTemplate(titleTemplate, ctx) : String(record.id);
  const rows =
    fields && fields.length > 0
      ? fields.map((f) => ({ label: f.label, value: interpolatePopupTemplate(f.template, ctx) }))
      : Object.entries(record.properties).map(([k, v]) => ({
          label: k,
          value: v === null || v === undefined ? "" : String(v),
        }));
  return (
    <article className="flex flex-col gap-3 p-4 text-ink">
      <h2 className="text-lg font-semibold">{title}</h2>
      <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
        {rows.map((r) => (
          <div key={r.label} className="contents">
            <dt className="font-medium text-ink-2">{r.label}</dt>
            <dd>{r.value}</dd>
          </div>
        ))}
      </dl>
    </article>
  );
}
