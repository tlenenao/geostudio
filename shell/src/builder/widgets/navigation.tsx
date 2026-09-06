// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";
import { t } from "../../i18n";

export function registerNavigationWidget(): void {
  registerWidget({
    type: "nav",
    label: t("widgetNavigation.paletteLabel"),
    defaultProps: { direction: "horizontal" },
    defaultSize: { w: 4, h: 1 },
    configSchema: [
      {
        name: "direction",
        type: "string",
        label: t("widgetNavigation.directionConfig"),
        default: "horizontal",
      },
    ],
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          {t("widgetNavigation.orientationText")}
          <select
            aria-label={t("widgetNavigation.orientationLabel")}
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.direction ?? "horizontal")}
            onChange={(e) => onChange({ ...props, direction: e.target.value })}
          >
            <option value="horizontal">{t("widgetNavigation.horizontal")}</option>
            <option value="vertical">{t("widgetNavigation.vertical")}</option>
          </select>
        </label>
        <p className="text-[10px] text-ink-2">{t("widgetNavigation.autoPagesHelp")}</p>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const pages = ctx.pages ?? [];
      const vertical = props.direction === "vertical";
      if (pages.length === 0)
        return <p className="text-xs text-ink-2">{t("widgetNavigation.noPages")}</p>;
      return (
        <nav className={`flex gap-1 ${vertical ? "flex-col" : "flex-row flex-wrap"}`}>
          {pages.map((p) => (
            <button
              key={p.id}
              type="button"
              className="rounded-[var(--gs-radius)] border border-[var(--gs-color-border)] px-2 py-1 text-sm text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
              onClick={() => ctx.navigate?.(p.id)}
            >
              {p.name}
            </button>
          ))}
        </nav>
      );
    },
  });
}
