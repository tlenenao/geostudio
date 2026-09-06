// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";
import { t } from "../../i18n";

export function registerFilterWidget(): void {
  registerWidget({
    type: "filter",
    label: t("widgetFilter.paletteLabel"),
    defaultProps: { field: "", label: "Filtrer" },
    defaultSize: { w: 3, h: 1 },
    configSchema: [
      { name: "field", type: "string", label: t("widgetFilter.fieldConfig"), default: "" },
      { name: "label", type: "string", label: t("widgetFilter.labelConfig"), default: "Filtrer" },
    ],
    events: ["changed"],
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          {t("widgetFilter.fieldConfig")}
          <input
            aria-label={t("widgetFilter.fieldConfig")}
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.field ?? "")}
            onChange={(e) => onChange({ ...props, field: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          {t("widgetFilter.labelConfig")}
          <input
            aria-label={t("widgetFilter.labelAria")}
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")}
            onChange={(e) => onChange({ ...props, label: e.target.value })}
          />
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const field = String(props.field ?? "");
      return (
        <label className="flex flex-col gap-1 text-sm text-[var(--gs-color-text)]">
          {String(props.label ?? "Filtrer")}
          <input
            aria-label={t("widgetFilter.valueAria")}
            className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
            onChange={(e) => {
              const value = e.target.value;
              ctx.bus?.emit(ctx.widgetId ?? "", "changed", field ? { [field]: value } : {});
            }}
          />
        </label>
      );
    },
  });
}
