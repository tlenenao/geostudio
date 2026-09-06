// SPDX-License-Identifier: Apache-2.0
import { getWidget, registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import type { DataRecord } from "../../api/types";
import { registerDataWidgets } from "./data";
import { registerIndicatorWidget } from "./indicator";
import { registerMapWidget } from "./mapWidget";
import { registerFilterWidget } from "./filter";
import { registerChartWidget } from "./chart";
import { registerPivotWidget } from "./pivot";
import { registerNavigationWidget } from "./navigation";
import { registerFormWidget } from "./form";
import { registerHeroWidget } from "./hero";
import { registerRichSectionWidget } from "./richSection";
import { registerGalleryWidget } from "./gallery";
import { registerDatasetCardWidget } from "./datasetCard";
import { registerDateRangeFilterWidget } from "./dateRangeFilter";
import { registerSelectFilterWidget } from "./selectFilter";
import { registerSliderFilterWidget } from "./sliderFilter";
import { registerTabsWidget } from "./tabs";
import { registerModalWidget } from "./modal";
import { registerDrawerWidget } from "./drawer";
import { registerVariableInputWidget } from "./variableInput";
import { t } from "../../i18n";

// Replaces {{var:nom}} tokens from ctx.variables (always, regardless of any
// bound source), then {{champ}} tokens from the record's properties (only
// when a source is bound — an unbound Texte still shows {{champ}} verbatim).
function stringifyVariable(value: unknown): string {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function interpolate(
  text: string,
  record: DataRecord | undefined,
  variables: Record<string, unknown>,
): string {
  let out = text.replace(/\{\{\s*var:([\w.]+)\s*\}\}/g, (_, name: string) =>
    stringifyVariable(variables[name]),
  );
  if (record) {
    out = out.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, key: string) => {
      const v = record.properties[key];
      return v === null || v === undefined ? "" : String(v);
    });
  }
  return out;
}

export function registerBuiltinWidgets(): void {
  if (getWidget("text")) return;
  registerWidget({
    type: "text",
    label: t("widgetIndex.textPaletteLabel"),
    defaultProps: { text: t("widgetIndex.newTextDefault"), dataSourceId: "" },
    defaultSize: { w: 4, h: 2 },
    configSchema: [
      {
        name: "text",
        type: "string",
        label: t("widgetIndex.textConfig"),
        default: t("widgetIndex.newTextDefault"),
      },
      {
        name: "dataSourceId",
        type: "dataSource",
        label: t("widgetIndex.dataSourceConfig"),
        default: "",
      },
    ],
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          {t("widgetIndex.textConfig")}
          <textarea
            aria-label={t("widgetIndex.textAria")}
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
        <p className="text-[10px] text-ink-2">{t("widgetIndex.interpolationHelp")}</p>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const raw = String(props.text ?? "");
      const text = interpolate(raw, ctx.data?.records[0], ctx.variables ?? {});
      return <p className="whitespace-pre-wrap text-[var(--gs-color-text)]">{text}</p>;
    },
  });

  registerWidget({
    type: "image",
    label: t("widgetIndex.imagePaletteLabel"),
    defaultProps: { src: "", alt: "" },
    defaultSize: { w: 4, h: 4 },
    configSchema: [
      { name: "src", type: "string", label: t("widgetIndex.urlConfig"), default: "" },
      { name: "alt", type: "string", label: t("widgetIndex.altConfig"), default: "" },
    ],
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          {t("widgetIndex.urlConfig")}
          <input
            aria-label={t("widgetIndex.urlAria")}
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.src ?? "")}
            onChange={(e) => onChange({ ...props, src: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          {t("widgetIndex.altConfig")}
          <input
            aria-label={t("widgetIndex.altConfig")}
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.alt ?? "")}
            onChange={(e) => onChange({ ...props, alt: e.target.value })}
          />
        </label>
      </div>
    ),
    Component: ({ props }) =>
      props.src ? (
        <img
          className="h-full w-full object-cover"
          src={String(props.src)}
          alt={String(props.alt ?? "")}
        />
      ) : (
        <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-ink-2">
          {t("widgetIndex.imagePaletteLabel")}
        </div>
      ),
  });

  registerWidget({
    type: "button",
    label: t("widgetIndex.buttonPaletteLabel"),
    defaultProps: { label: "Bouton", href: "" },
    defaultSize: { w: 2, h: 1 },
    configSchema: [
      { name: "label", type: "string", label: t("widgetIndex.labelConfig"), default: "Bouton" },
      { name: "href", type: "string", label: t("widgetIndex.hrefConfig"), default: "" },
    ],
    events: ["clicked"],
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          {t("widgetIndex.labelConfig")}
          <input
            aria-label={t("widgetIndex.labelAria")}
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")}
            onChange={(e) => onChange({ ...props, label: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          {t("widgetIndex.hrefConfig")}
          <input
            aria-label={t("widgetIndex.hrefAria")}
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
  registerPivotWidget();
  registerNavigationWidget();
  registerFormWidget();
  registerHeroWidget();
  registerRichSectionWidget();
  registerGalleryWidget();
  registerDatasetCardWidget();
  registerDateRangeFilterWidget();
  registerSelectFilterWidget();
  registerSliderFilterWidget();
  registerTabsWidget();
  registerModalWidget();
  registerDrawerWidget();
  registerVariableInputWidget();
}
