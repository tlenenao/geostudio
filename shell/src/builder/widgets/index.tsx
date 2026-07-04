import { getWidget, registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import type { DataRecord } from "../../api/types";
import { registerDataWidgets } from "./data";
import { registerIndicatorWidget } from "./indicator";
import { registerMapWidget } from "./mapWidget";
import { registerFilterWidget } from "./filter";
import { registerChartWidget } from "./chart";

// Replace {{champ}} tokens with the record's property values (empty if absent).
function interpolate(text: string, record: DataRecord | undefined): string {
  if (!record) return text;
  return text.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, key: string) => {
    const v = record.properties[key];
    return v === null || v === undefined ? "" : String(v);
  });
}

export function registerBuiltinWidgets(): void {
  if (getWidget("text")) return;
  registerWidget({
    type: "text",
    label: "Texte",
    defaultProps: { text: "Nouveau texte", dataSourceId: "" },
    defaultSize: { w: 4, h: 2 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          Texte
          <textarea
            aria-label="Texte du widget"
            className="rounded-md border border-slate-300 p-2 text-sm"
            value={String(props.text ?? "")}
            onChange={(e) => onChange({ ...props, text: e.target.value })}
          />
        </label>
        <DataSourceSelect
          value={String(props.dataSourceId ?? "")}
          dataSources={dataSources}
          onChange={(id) => onChange({ ...props, dataSourceId: id })}
        />
        <p className="text-[10px] text-slate-400">Utilisez {"{{champ}}"} pour insérer une valeur de la source liée.</p>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const raw = String(props.text ?? "");
      const text = ctx.data ? interpolate(raw, ctx.data.records[0]) : raw;
      return <p className="whitespace-pre-wrap text-[var(--gs-color-text)]">{text}</p>;
    },
  });

  registerWidget({
    type: "image",
    label: "Image",
    defaultProps: { src: "", alt: "" },
    defaultSize: { w: 4, h: 4 },
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          URL
          <input
            aria-label="URL de l'image"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.src ?? "")}
            onChange={(e) => onChange({ ...props, src: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          Texte alternatif
          <input
            aria-label="Texte alternatif"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.alt ?? "")}
            onChange={(e) => onChange({ ...props, alt: e.target.value })}
          />
        </label>
      </div>
    ),
    Component: ({ props }) =>
      props.src ? (
        <img className="h-full w-full object-cover" src={String(props.src)} alt={String(props.alt ?? "")} />
      ) : (
        <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-slate-400">
          Image
        </div>
      ),
  });

  registerWidget({
    type: "button",
    label: "Bouton",
    defaultProps: { label: "Bouton", href: "" },
    defaultSize: { w: 2, h: 1 },
    events: ["clicked"],
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          Libellé
          <input
            aria-label="Libellé du bouton"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")}
            onChange={(e) => onChange({ ...props, label: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          Lien
          <input
            aria-label="Lien du bouton"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.href ?? "")}
            onChange={(e) => onChange({ ...props, href: e.target.value })}
          />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => (
      <button
        type="button"
        className="rounded-[var(--gs-radius)] bg-[var(--gs-color-primary)] px-3 py-1.5 text-sm text-white"
        onClick={() => {
          ctx.bus?.emit(ctx.widgetId ?? "", "clicked", { widgetId: ctx.widgetId });
          const href = String(props.href ?? "");
          if (href) window.open(href, "_blank", "noopener");
        }}
      >
        {String(props.label ?? "Bouton")}
      </button>
    ),
  });

  registerDataWidgets();
  registerIndicatorWidget();
  registerMapWidget();
  registerFilterWidget();
  registerChartWidget();
}
