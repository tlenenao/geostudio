// SPDX-License-Identifier: Apache-2.0
// ARC-17 : sélecteur de mode avancé (densité de points, prédominant, bivarié,
// comparer A à B) et d'effets. Monté par MapSymbologyEditor, donc identique
// dans l'éditeur de cartes et le PropsPanel du widget carte.
import { useState } from "react";
import { DOT_DEFAULT_COLOR, type AdvancedSymbology } from "../builder/widgets/advancedSymbology";
import {
  computeSizeDomain,
  type LayerSymbology,
  type StatQueryFn,
} from "../builder/widgets/mapSymbology";
import { Button } from "../ui/kit/Button";
import { inputCls, labelCls } from "./formFieldStyles";
import { t } from "../i18n";
import "../i18n/domains/map";

type Mode = "none" | AdvancedSymbology["kind"];
const MODES: Mode[] = ["none", "dotDensity", "predominant", "bivariate", "compare"];

function defaultFor(mode: Exclude<Mode, "none">): AdvancedSymbology {
  switch (mode) {
    case "dotDensity":
      return { kind: "dotDensity", field: "", valuePerDot: 100, color: DOT_DEFAULT_COLOR };
    case "predominant":
      return { kind: "predominant", fields: [] };
    case "bivariate":
      return {
        kind: "bivariate",
        fieldX: "",
        fieldY: "",
        domainX: { min: 0, max: 0 },
        domainY: { min: 0, max: 0 },
        computedAt: "",
      };
    case "compare":
      return { kind: "compare", fieldA: "", fieldB: "", maxAbs: 0, computedAt: "" };
  }
}

const MODE_LABEL = {
  none: "mapSymbology.advancedModeNone",
  dotDensity: "mapSymbology.advancedModeDotDensity",
  predominant: "mapSymbology.advancedModePredominant",
  bivariate: "mapSymbology.advancedModeBivariate",
  compare: "mapSymbology.advancedModeCompare",
} as const;

export function AdvancedSymbologyEditor({
  value,
  availableFields,
  runStatistics,
  onChange,
}: {
  value: LayerSymbology | undefined;
  availableFields: string[];
  runStatistics: StatQueryFn;
  onChange: (value: LayerSymbology | undefined) => void;
}) {
  const adv = value?.advanced;
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function setAdvanced(next: AdvancedSymbology | undefined) {
    const rest = { ...(value ?? {}) };
    delete rest.advanced;
    const out = next ? { ...rest, advanced: next } : rest;
    onChange(Object.keys(out).length > 0 ? out : undefined);
  }

  // Un champ qui change invalide l'échelle figée (même règle que couleur/taille).
  function patch(p: Partial<AdvancedSymbology>, invalidate = false) {
    if (!adv) return;
    const next = { ...adv, ...p } as AdvancedSymbology;
    if (invalidate && "computedAt" in next) next.computedAt = "";
    setAdvanced(next);
  }

  async function recompute() {
    if (adv?.kind !== "bivariate" && adv?.kind !== "compare") return;
    setBusy(true);
    setError(null);
    const stamp = new Date().toISOString();
    try {
      if (adv.kind === "bivariate") {
        const [domainX, domainY] = await Promise.all([
          computeSizeDomain(adv.fieldX, { runStatistics }),
          computeSizeDomain(adv.fieldY, { runStatistics }),
        ]);
        setAdvanced({ ...adv, domainX, domainY, computedAt: stamp });
      } else {
        const [a, b] = await Promise.all([
          computeSizeDomain(adv.fieldA, { runStatistics }),
          computeSizeDomain(adv.fieldB, { runStatistics }),
        ]);
        const maxAbs = Math.max(Math.abs(a.max - b.min), Math.abs(a.min - b.max));
        setAdvanced({ ...adv, maxAbs, computedAt: stamp });
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const fieldSelect = (label: string, current: string, onPick: (v: string) => void) => (
    <label className={labelCls}>
      {label}
      <select className={inputCls} value={current} onChange={(e) => onPick(e.target.value)}>
        <option value="" />
        {availableFields.map((f) => (
          <option key={f} value={f}>
            {f}
          </option>
        ))}
      </select>
    </label>
  );

  const effects = value?.effects ?? {};
  const toggleEffect = (key: "bloom" | "shadow" | "blend", on: boolean) => {
    const next = { ...effects, [key]: on || undefined };
    const clean = Object.fromEntries(Object.entries(next).filter(([, v]) => v));
    const rest = { ...(value ?? {}) };
    delete rest.effects;
    const out = Object.keys(clean).length > 0 ? { ...rest, effects: clean } : rest;
    onChange(Object.keys(out).length > 0 ? out : undefined);
  };

  return (
    <div className="flex flex-col gap-2 border-t border-rule-2 pt-2">
      <label className={labelCls}>
        {t("mapSymbology.advancedModeLabel")}
        <select
          className={inputCls}
          value={adv?.kind ?? "none"}
          onChange={(e) => {
            const m = e.target.value as Mode;
            setError(null);
            setAdvanced(m === "none" ? undefined : defaultFor(m));
          }}
        >
          {MODES.map((m) => (
            <option key={m} value={m}>
              {t(MODE_LABEL[m])}
            </option>
          ))}
        </select>
      </label>

      {adv && <p className="text-xs text-ink-3">{t("mapSymbology.advancedOverridesColorHint")}</p>}

      {adv?.kind === "dotDensity" && (
        <>
          {fieldSelect(t("mapSymbology.advancedFieldLabel"), adv.field, (v) => patch({ field: v }))}
          <label className={labelCls}>
            {t("mapSymbology.advancedValuePerDotLabel")}
            <input
              type="number"
              min={1}
              className={inputCls}
              value={adv.valuePerDot}
              onChange={(e) => patch({ valuePerDot: Number(e.target.value) })}
            />
          </label>
          <label className={labelCls}>
            {t("mapSymbology.advancedDotColorLabel")}
            <input
              type="color"
              value={adv.color}
              onChange={(e) => patch({ color: e.target.value })}
            />
          </label>
          <p className="text-xs text-ink-3">{t("mapSymbology.advancedPolygonOnlyHint")}</p>
        </>
      )}

      {adv?.kind === "predominant" && (
        <fieldset className="flex flex-col gap-1">
          <legend className="text-xs text-ink-3">
            {t("mapSymbology.advancedPredominantFieldsLegend")}
          </legend>
          {availableFields.map((f) => (
            <label key={f} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={adv.fields.includes(f)}
                onChange={(e) =>
                  patch({
                    fields: e.target.checked
                      ? [...adv.fields, f]
                      : adv.fields.filter((x) => x !== f),
                  })
                }
              />
              {f}
            </label>
          ))}
        </fieldset>
      )}

      {adv?.kind === "bivariate" &&
        fieldSelect(t("mapSymbology.advancedFieldXLabel"), adv.fieldX, (v) =>
          patch({ fieldX: v }, true),
        )}
      {adv?.kind === "bivariate" &&
        fieldSelect(t("mapSymbology.advancedFieldYLabel"), adv.fieldY, (v) =>
          patch({ fieldY: v }, true),
        )}
      {adv?.kind === "compare" &&
        fieldSelect(t("mapSymbology.advancedFieldALabel"), adv.fieldA, (v) =>
          patch({ fieldA: v }, true),
        )}
      {adv?.kind === "compare" &&
        fieldSelect(t("mapSymbology.advancedFieldBLabel"), adv.fieldB, (v) =>
          patch({ fieldB: v }, true),
        )}

      {(adv?.kind === "bivariate" || adv?.kind === "compare") && (
        <>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="self-start"
            disabled={
              busy ||
              (adv.kind === "bivariate" ? !adv.fieldX || !adv.fieldY : !adv.fieldA || !adv.fieldB)
            }
            onClick={() => void recompute()}
          >
            {busy ? t("mapSymbology.computingButton") : t("mapSymbology.advancedRecomputeButton")}
          </Button>
          {error && (
            <p role="alert" className="text-xs text-danger">
              {error}
            </p>
          )}
          {!adv.computedAt && (
            <p className="text-xs text-warn">{t("mapSymbology.advancedNotComputedHint")}</p>
          )}
        </>
      )}

      <fieldset className="flex flex-col gap-1">
        <legend className="text-xs text-ink-3">{t("mapSymbology.effectsLegend")}</legend>
        {(["bloom", "shadow", "blend"] as const).map((k) => (
          <label
            key={k}
            className="flex min-h-6 items-center gap-2 text-sm pointer-coarse:min-h-11"
          >
            <input
              type="checkbox"
              checked={!!effects[k]}
              onChange={(e) => toggleEffect(k, e.target.checked)}
            />
            {t(
              k === "bloom"
                ? "mapSymbology.effectBloom"
                : k === "shadow"
                  ? "mapSymbology.effectShadow"
                  : "mapSymbology.effectBlend",
            )}
          </label>
        ))}
      </fieldset>
    </div>
  );
}
