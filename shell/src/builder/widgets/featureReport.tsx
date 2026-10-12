// SPDX-License-Identifier: Apache-2.0
// ARC-26 : fiche d'entité imprimable. Affiche l'entité reçue par l'action
// `showRecord` (typiquement `itemSelected` d'une carte/table) ; l'export PDF
// passe par le worker d'export existant (`POST /export` avec `entityId`).
import { useState } from "react";
import { useInRouterContext, useParams } from "react-router-dom";
import { registerWidget } from "../registry";
import { useBusAction } from "../ActionBusContext";
import { useInstanceInfo } from "../../api/hooks";
import type { DataRecord } from "../../api/types";
import { ExportPanel } from "../print/ExportPanel";
import { EntityFiche, type FicheField } from "../print/EntityFiche";
import { t } from "../../i18n";
import "../../i18n/domains/widgets";

function FicheExport({ entityId }: { entityId: string }) {
  const { pk } = useParams();
  const exportEnabled = useInstanceInfo().data?.exportEnabled === true;
  if (!pk || !exportEnabled) return null;
  return <ExportPanel itemId={pk} entityId={entityId} label={t("widgetFeatureReport.exportPdf")} />;
}

export function registerFeatureReportWidget(): void {
  registerWidget({
    type: "featureReport",
    label: t("widgetFeatureReport.paletteLabel"),
    defaultProps: { titleTemplate: "", fields: [] },
    defaultSize: { w: 4, h: 5 },
    actions: ["showRecord"],
    configSchema: [
      {
        name: "titleTemplate",
        type: "string",
        label: t("widgetFeatureReport.titleConfig"),
        default: "",
      },
    ],
    PropsPanel: ({ props, onChange }) => {
      const fields = (props.fields as FicheField[] | undefined) ?? [];
      return (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex flex-col gap-1">
            {t("widgetFeatureReport.titleConfig")}
            <input
              className="h-9 rounded-md border border-control bg-surface px-2 text-ink"
              value={String(props.titleTemplate ?? "")}
              onChange={(e) => onChange({ ...props, titleTemplate: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1">
            {t("widgetFeatureReport.fieldsConfig")}
            <textarea
              className="min-h-24 rounded-md border border-control bg-surface px-2 py-1 text-ink"
              value={fields.map((f) => `${f.label} = ${f.template}`).join("\n")}
              onChange={(e) =>
                onChange({
                  ...props,
                  fields: e.target.value
                    .split("\n")
                    .filter((l) => l.includes("="))
                    .map((l) => {
                      const i = l.indexOf("=");
                      return { label: l.slice(0, i).trim(), template: l.slice(i + 1).trim() };
                    }),
                })
              }
            />
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const [record, setRecord] = useState<DataRecord | null>(null);
      const inRouter = useInRouterContext();
      useBusAction(ctx.bus, ctx.widgetId, "showRecord", (payload) => {
        if (payload) setRecord(payload as DataRecord);
      });
      if (!record) {
        return <p className="p-4 text-sm text-ink-2">{t("widgetFeatureReport.empty")}</p>;
      }
      return (
        <div className="flex h-full flex-col overflow-auto">
          <EntityFiche
            record={record}
            titleTemplate={String(props.titleTemplate ?? "") || undefined}
            fields={props.fields as FicheField[] | undefined}
            exprContext={{ vars: ctx.variables ?? {}, user: ctx.user ?? { name: "" } }}
          />
          {ctx.mode === "runtime" && inRouter && (
            <div className="px-4 pb-4">
              <FicheExport entityId={String(record.id)} />
            </div>
          )}
        </div>
      );
    },
  });
}
