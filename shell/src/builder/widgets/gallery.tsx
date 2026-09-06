// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { useItemClient } from "../../api/ItemClientProvider";
import type { ResourceType } from "../../api/types";
import { t } from "../../i18n";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";

const RESOURCE_TYPES: [string, string][] = [
  ["", t("widgetGallery.typeAll")],
  ["app", t("widgetGallery.typeApp")],
  ["dashboard", t("widgetGallery.typeDashboard")],
  ["map", t("widgetGallery.typeMap")],
  ["site", t("widgetGallery.typeSite")],
];

export function registerGalleryWidget(): void {
  registerWidget({
    type: "gallery",
    label: t("widgetGallery.paletteLabel"),
    defaultProps: { type: "", tag: "", limit: 12, columns: 3 },
    defaultSize: { w: 12, h: 6 },
    configSchema: [
      { name: "type", type: "string", label: t("widgetGallery.typeConfig"), default: "" },
      { name: "tag", type: "string", label: t("widgetGallery.tagConfig"), default: "" },
      { name: "limit", type: "number", label: t("widgetGallery.limitConfig"), default: 12 },
      { name: "columns", type: "number", label: t("widgetGallery.columnsConfig"), default: 3 },
    ],
    PropsPanel: ({ props, onChange }) => {
      const set = (patch: Record<string, unknown>) => onChange({ ...props, ...patch });
      return (
        <div className="flex flex-col gap-2 text-sm">
          <label className={labelCls}>
            {t("widgetGallery.typeLabel")}
            <select
              aria-label={t("widgetGallery.typeLabel")}
              className={inputCls}
              value={String(props.type ?? "")}
              onChange={(e) => set({ type: e.target.value })}
            >
              {RESOURCE_TYPES.map(([v, l]) => (
                <option key={v} value={v}>
                  {l}
                </option>
              ))}
            </select>
          </label>
          <label className={labelCls}>
            {t("widgetGallery.tagConfig")}
            <input
              aria-label={t("widgetGallery.tagConfig")}
              className={inputCls}
              value={String(props.tag ?? "")}
              onChange={(e) => set({ tag: e.target.value })}
            />
          </label>
          <label className={labelCls}>
            {t("widgetGallery.limitLabel")}
            <input
              aria-label={t("widgetGallery.limitLabel")}
              type="number"
              className={inputCls}
              value={String(props.limit ?? 12)}
              onChange={(e) => set({ limit: Number(e.target.value) })}
            />
          </label>
          <label className={labelCls}>
            {t("widgetGallery.columnsConfig")}
            <input
              aria-label={t("widgetGallery.columnsConfig")}
              type="number"
              className={inputCls}
              value={String(props.columns ?? 3)}
              onChange={(e) => set({ columns: Number(e.target.value) })}
            />
          </label>
        </div>
      );
    },
    Component: ({ props }) => {
      const client = useItemClient();
      const type = props.type ? String(props.type) : undefined;
      const tag = props.tag ? String(props.tag) : undefined;
      const limit = Number(props.limit ?? 12);
      const columns = Number(props.columns ?? 3);
      const query = useQuery({
        queryKey: ["public-gallery", type, tag, limit],
        queryFn: () =>
          client.listPublicItems({
            type: type as ResourceType | undefined,
            tag,
            page: 1,
            pageSize: limit,
          }),
      });

      if (query.isLoading) {
        return <p className="text-xs text-[var(--gs-color-muted)]">{t("common.loading")}</p>;
      }
      if (query.isError) {
        return (
          <p role="alert" className="text-xs text-red-600">
            {t("widgetGallery.loadError")}
          </p>
        );
      }
      const items = query.data?.items ?? [];
      if (items.length === 0) {
        return <p className="text-sm text-[var(--gs-color-muted)]">{t("widgetGallery.empty")}</p>;
      }
      return (
        <div
          className="grid gap-4"
          style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
        >
          {items.map((item) => (
            <a
              key={item.pk}
              href={`/public/items/${item.pk}`}
              className="flex flex-col overflow-hidden rounded-[var(--gs-radius)] border border-[var(--gs-color-border)] bg-[var(--gs-color-surface)] text-inherit no-underline"
            >
              {item.thumbnailUrl ? (
                <img src={item.thumbnailUrl} alt="" className="h-32 w-full object-cover" />
              ) : (
                <div className="h-32 w-full bg-[var(--gs-color-background)]" />
              )}
              <div className="flex flex-col gap-1 p-3">
                <h3 className="text-sm font-semibold text-[var(--gs-color-text)]">{item.title}</h3>
                <p className="text-xs text-[var(--gs-color-muted)]">{item.abstract}</p>
                {(item.keywords ?? []).length > 0 && (
                  <div className="flex flex-wrap gap-1">
                    {(item.keywords ?? []).map((k) => (
                      <span
                        key={k}
                        className="rounded-full bg-[var(--gs-color-background)] px-2 py-0.5 text-[10px] text-[var(--gs-color-muted)]"
                      >
                        {k}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </a>
          ))}
        </div>
      );
    },
  });
}
