// SPDX-License-Identifier: Apache-2.0
// Tâche 35 (SP-C6, D15) : extrait tel quel de builder/widgets/mapWidget.tsx
// (comportement inchangé) pour être réutilisé par MapEditorPage.tsx, qui
// n'affichait jusqu'ici aucune légende de symbologie.
import type { LegendSpec } from "../builder/widgets/mapSymbology";
import type { AdvancedLegend } from "../builder/widgets/advancedSymbology";
import { t } from "../i18n";
import { formatNumber } from "../lib/format";
import "../i18n/domains/widgets";

// Correctif revue Tâche 35 : `mapWidget.tsx` monte toujours une seule
// instance directement dans son propre conteneur `relative`, donc l'ancrage
// `absolute` en dur ci-dessous (coin bas-droit) est correct pour ce seul
// appelant ("floating", défaut inchangé). `MapEditorPage.tsx` peut en
// revanche monter plusieurs instances (une par couche vecteur visible avec
// symbologie) dans son propre conteneur déjà positionné et empilé en
// `flex-col` — un `absolute` par enfant les ferait tous se superposer au
// même point (sorti du flux, `gap`/`flex-col` du parent ignorés) au lieu de
// s'empiler. `variant="static"` retire cet ancrage propre pour laisser le
// parent gérer position ET empilement.
export function MapSymbologyLegend({
  legend,
  variant = "floating",
}: {
  legend: LegendSpec;
  variant?: "floating" | "static";
}) {
  return (
    <div
      className={
        variant === "floating"
          ? "absolute bottom-2 right-2 z-10 flex flex-col gap-2 rounded-md bg-surface/90 p-2 text-xs text-ink shadow"
          : "flex flex-col gap-2 rounded-md bg-surface/90 p-2 text-xs text-ink shadow"
      }
    >
      {legend.color?.kind === "categorical" && (
        <ul>
          {legend.color.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-sm"
                style={{ backgroundColor: e.color }}
              />
              {e.value}
            </li>
          ))}
        </ul>
      )}
      {legend.color?.kind === "classed" && (
        <ul>
          {legend.color.classes.map((c, i) => (
            <li key={i} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-sm"
                style={{ backgroundColor: c.color }}
              />
              {formatNumber(c.from, 1, 1)} – {formatNumber(c.to, 1, 1)}
            </li>
          ))}
        </ul>
      )}
      {legend.color?.kind === "numeric" && (
        <div>
          <div
            className="h-2 w-24 rounded"
            style={{
              background: `linear-gradient(to right, ${legend.color.colorLow}, ${legend.color.colorHigh})`,
            }}
          />
          <span>
            {legend.color.min} – {legend.color.max}
          </span>
        </div>
      )}
      {legend.size && (
        <div className="flex items-end gap-2">
          <span
            className="rounded-full bg-ink-3"
            style={{ width: legend.size.radiusMin, height: legend.size.radiusMin }}
          />
          <span
            className="rounded-full bg-ink-3"
            style={{ width: legend.size.radiusMax, height: legend.size.radiusMax }}
          />
          <span>
            {legend.size.min} – {legend.size.max}
          </span>
        </div>
      )}
      {legend.stroke?.kind === "categorical" && (
        <ul aria-label={t("widgetMap.strokeLegendAria")}>
          {legend.stroke.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-sm border-2"
                style={{ borderColor: e.color }}
              />
              {e.value}
            </li>
          ))}
        </ul>
      )}
      {/* Fix I2 de la revue finale SP-27 : un contour classé/continu se
          compile correctement (buildMapPaint, expression step/interpolate
          sur fill-outline-color) depuis que Task 5 a rendu le sélecteur de
          couleur de contour symétrique du remplissage, mais la légende ne
          savait décrire que le cas catégoriel — miroir exact des blocs
          legend.color juste au-dessus. */}
      {legend.stroke?.kind === "classed" && (
        <ul aria-label={t("widgetMap.strokeLegendAria")}>
          {legend.stroke.classes.map((c, i) => (
            <li key={i} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-sm border-2"
                style={{ borderColor: c.color }}
              />
              {formatNumber(c.from, 1, 1)} – {formatNumber(c.to, 1, 1)}
            </li>
          ))}
        </ul>
      )}
      {legend.stroke?.kind === "numeric" && (
        <div aria-label={t("widgetMap.strokeLegendAria")}>
          <div
            className="h-2 w-24 rounded border-2"
            style={{
              background: `linear-gradient(to right, ${legend.stroke.colorLow}, ${legend.stroke.colorHigh})`,
            }}
          />
          <span>
            {legend.stroke.min} – {legend.stroke.max}
          </span>
        </div>
      )}
      {legend.advanced && <AdvancedLegendBlock adv={legend.advanced} />}
      {legend.icon && (
        <ul aria-label={t("widgetMap.iconLegendAria")}>
          {legend.icon.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span aria-hidden="true" className="text-base">
                ◈
              </span>
              {e.value}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

// ARC-17 : légende des modes avancés (prédominant, bivarié, comparer, densité de points).
function AdvancedLegendBlock({ adv }: { adv: AdvancedLegend }) {
  return (
    <div aria-label={t("widgetMap.advancedLegendAria")} data-testid="legend-advanced">
      {adv.kind === "predominant" && (
        <ul>
          {adv.entries.map((e) => (
            <li key={e.value} className="flex items-center gap-1">
              <span
                className="inline-block h-3 w-3 rounded-sm"
                style={{ backgroundColor: e.color }}
              />
              {e.value}
            </li>
          ))}
        </ul>
      )}
      {adv.kind === "bivariate" && (
        <div>
          <div className="grid w-fit grid-cols-3">
            {/* ligne du haut = y fort : ordre des lignes inversé */}
            {[2, 1, 0].flatMap((y) =>
              [0, 1, 2].map((x) => (
                <span
                  key={`${x}-${y}`}
                  className="h-4 w-4"
                  style={{ backgroundColor: adv.colors[y * 3 + x] }}
                />
              )),
            )}
          </div>
          <span>{t("widgetMap.bivariateAxes", { fieldX: adv.fieldX, fieldY: adv.fieldY })}</span>
        </div>
      )}
      {adv.kind === "compare" && (
        <div>
          <div
            className="h-2 w-24 rounded"
            style={{
              background: `linear-gradient(to right, ${adv.colorLow}, ${adv.colorMid}, ${adv.colorHigh})`,
            }}
          />
          <span>
            {formatNumber(-adv.maxAbs, 1)} – {formatNumber(adv.maxAbs, 1)}
          </span>
          <br />
          <span>{t("widgetMap.compareCaption", { fieldA: adv.fieldA, fieldB: adv.fieldB })}</span>
        </div>
      )}
      {adv.kind === "dotDensity" && (
        <div className="flex items-center gap-1">
          <span
            className="inline-block h-2 w-2 rounded-full"
            style={{ backgroundColor: adv.color }}
          />
          {t("widgetMap.dotDensityCaption", {
            value: formatNumber(adv.valuePerDot, 2),
            field: adv.field,
          })}
        </div>
      )}
    </div>
  );
}
