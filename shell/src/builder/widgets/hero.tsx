// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";
import { t } from "../../i18n";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-9 rounded-md border border-slate-300 px-2";

const SAFE_HREF_SCHEMES = new Set(["http:", "https:", "mailto:"]);

/** Author-controlled hrefs must be validated before being handed to window.open — a bare
 * scheme allowlist against the resolved URL, matching the anti-injection intent of
 * RichSection's sanitizeMarkdown() chokepoint (author -> anonymous visitor trust boundary). */
export function isSafeHref(href: string): boolean {
  try {
    const resolved = new URL(href, window.location.origin);
    return SAFE_HREF_SCHEMES.has(resolved.protocol);
  } catch {
    return false;
  }
}

export function registerHeroWidget(): void {
  registerWidget({
    type: "hero",
    label: t("widgetHero.paletteLabel"),
    defaultProps: {
      title: "Titre",
      subtitle: "",
      backgroundImageUrl: "",
      ctaLabel: "",
      ctaHref: "",
      align: "left",
    },
    defaultSize: { w: 12, h: 3 },
    configSchema: [
      { name: "title", type: "string", label: t("widgetHero.titleConfig"), default: "Titre" },
      { name: "subtitle", type: "string", label: t("widgetHero.subtitleConfig"), default: "" },
      {
        name: "backgroundImageUrl",
        type: "string",
        label: t("widgetHero.bgImageConfig"),
        default: "",
      },
      { name: "ctaLabel", type: "string", label: t("widgetHero.ctaLabelConfig"), default: "" },
      { name: "ctaHref", type: "string", label: t("widgetHero.ctaHrefConfig"), default: "" },
      { name: "align", type: "string", label: t("widgetHero.alignConfig"), default: "left" },
    ],
    events: ["cta"],
    PropsPanel: ({ props, onChange }) => {
      const set = (patch: Record<string, unknown>) => onChange({ ...props, ...patch });
      return (
        <div className="flex flex-col gap-2 text-sm">
          <label className={labelCls}>
            {t("widgetHero.titleBanner")}
            <input
              aria-label={t("widgetHero.titleBanner")}
              className={inputCls}
              value={String(props.title ?? "")}
              onChange={(e) => set({ title: e.target.value })}
            />
          </label>
          <label className={labelCls}>
            {t("widgetHero.subtitleConfig")}
            <input
              aria-label={t("widgetHero.subtitleConfig")}
              className={inputCls}
              value={String(props.subtitle ?? "")}
              onChange={(e) => set({ subtitle: e.target.value })}
            />
          </label>
          <label className={labelCls}>
            {t("widgetHero.bgImageLabel")}
            <input
              aria-label={t("widgetHero.bgImageLabel")}
              className={inputCls}
              value={String(props.backgroundImageUrl ?? "")}
              onChange={(e) => set({ backgroundImageUrl: e.target.value })}
            />
          </label>
          <label className={labelCls}>
            {t("widgetHero.ctaLabelText")}
            <input
              aria-label={t("widgetHero.ctaLabelText")}
              className={inputCls}
              value={String(props.ctaLabel ?? "")}
              onChange={(e) => set({ ctaLabel: e.target.value })}
            />
          </label>
          <label className={labelCls}>
            {t("widgetHero.ctaHrefText")}
            <input
              aria-label={t("widgetHero.ctaHrefText")}
              className={inputCls}
              value={String(props.ctaHref ?? "")}
              onChange={(e) => set({ ctaHref: e.target.value })}
            />
          </label>
          <label className={labelCls}>
            {t("widgetHero.alignConfig")}
            <select
              aria-label={t("widgetHero.alignConfig")}
              className={inputCls}
              value={String(props.align ?? "left")}
              onChange={(e) => set({ align: e.target.value })}
            >
              <option value="left">{t("widgetHero.alignLeft")}</option>
              <option value="center">{t("widgetHero.alignCenter")}</option>
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
              ? {
                  backgroundImage: `url(${backgroundImageUrl})`,
                  backgroundSize: "cover",
                  backgroundPosition: "center",
                }
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
                if (href && isSafeHref(href)) window.open(href, "_blank", "noopener");
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
