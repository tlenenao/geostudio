// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";

export function registerHeroWidget(): void {
  registerWidget({
    type: "hero",
    label: "Hero",
    defaultProps: { title: "Titre", subtitle: "", backgroundImageUrl: "", ctaLabel: "", ctaHref: "", align: "left" },
    defaultSize: { w: 12, h: 3 },
    events: ["cta"],
    PropsPanel: ({ props, onChange }) => {
      const set = (patch: Record<string, unknown>) => onChange({ ...props, ...patch });
      return (
        <div className="flex flex-col gap-2 text-sm">
          <label className={labelCls}>Titre du bandeau
            <input aria-label="Titre du bandeau" className={inputCls}
              value={String(props.title ?? "")} onChange={(e) => set({ title: e.target.value })} />
          </label>
          <label className={labelCls}>Sous-titre
            <input aria-label="Sous-titre" className={inputCls}
              value={String(props.subtitle ?? "")} onChange={(e) => set({ subtitle: e.target.value })} />
          </label>
          <label className={labelCls}>URL de l'image de fond
            <input aria-label="URL de l'image de fond" className={inputCls}
              value={String(props.backgroundImageUrl ?? "")} onChange={(e) => set({ backgroundImageUrl: e.target.value })} />
          </label>
          <label className={labelCls}>Libellé du CTA
            <input aria-label="Libellé du CTA" className={inputCls}
              value={String(props.ctaLabel ?? "")} onChange={(e) => set({ ctaLabel: e.target.value })} />
          </label>
          <label className={labelCls}>Lien du CTA
            <input aria-label="Lien du CTA" className={inputCls}
              value={String(props.ctaHref ?? "")} onChange={(e) => set({ ctaHref: e.target.value })} />
          </label>
          <label className={labelCls}>Alignement
            <select aria-label="Alignement" className={inputCls}
              value={String(props.align ?? "left")} onChange={(e) => set({ align: e.target.value })}>
              <option value="left">Gauche</option>
              <option value="center">Centre</option>
            </select>
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const align = props.align === "center" ? "items-center text-center" : "items-start text-left";
      const backgroundImageUrl = props.backgroundImageUrl ? String(props.backgroundImageUrl) : "";
      return (
        <div
          className={`flex h-full w-full flex-col justify-center gap-3 rounded-[var(--gs-radius)] p-8 text-white ${align}`}
          style={
            backgroundImageUrl
              ? { backgroundImage: `url(${backgroundImageUrl})`, backgroundSize: "cover", backgroundPosition: "center" }
              : { backgroundColor: "var(--gs-color-primary)" }
          }
        >
          <h1 className="text-3xl font-bold">{String(props.title ?? "")}</h1>
          {props.subtitle ? <p className="text-lg">{String(props.subtitle)}</p> : null}
          {props.ctaLabel ? (
            <button
              type="button"
              className="mt-2 w-fit rounded-[var(--gs-radius)] bg-white px-4 py-2 text-sm font-medium text-[var(--gs-color-primary)]"
              onClick={() => {
                ctx.bus?.emit(ctx.widgetId ?? "", "cta", { widgetId: ctx.widgetId });
                const href = String(props.ctaHref ?? "");
                if (href) window.open(href, "_blank", "noopener");
              }}
            >
              {String(props.ctaLabel)}
            </button>
          ) : null}
        </div>
      );
    },
  });
}
