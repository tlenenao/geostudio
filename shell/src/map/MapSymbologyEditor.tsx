// SPDX-License-Identifier: Apache-2.0
import { useId, useState } from "react";
import {
  computeColorDomain,
  computeSizeDomain,
  type ColorClassification,
  type ColorDomain,
  type LayerSymbology,
  type SampleFieldFn,
  type StatQueryFn,
} from "../builder/widgets/mapSymbology";
import type { PaletteId } from "../builder/widgets/palette";
import type { ThemeColors } from "../api/types";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-8 rounded-md border border-slate-300 px-2 text-sm";

const PALETTE_OPTIONS: { id: Exclude<PaletteId, "theme-primary">; label: string }[] = [
  { id: "categorical-a", label: "Catégorielle A" },
  { id: "categorical-b", label: "Catégorielle B" },
  { id: "sequential-blue", label: "Séquentielle bleue" },
  { id: "sequential-warm", label: "Séquentielle chaude" },
];

// Union concrète plutôt que la gymnastique de type conditionnel dérivé de
// LayerSymbology["color"] — plus lisible et garantie de compiler sous tsc
// (repli explicitement prévu par le plan, cf. task-7-brief.md Step 4).
function formatDomain(domain: ColorDomain): string {
  if (domain.kind === "categorical") return domain.values.join(", ");
  if (domain.kind === "numeric-classed") return domain.breaks.map((b) => b.toFixed(1)).join(" – ");
  return `${domain.min} – ${domain.max}`;
}

// Éditeur partagé par les DEUX surfaces (éditeur de cartes et PropsPanel du
// widget carte) — même précédent que PopupEditor.tsx (SP-24). Les deux
// hôtes ne diffèrent que par comment `runStatistics`/`sampleField`
// résolvent (collectionId direct vs datasetId), jamais par l'UI elle-même.
export function MapSymbologyEditor({
  value,
  availableFields,
  themeColors,
  runStatistics,
  sampleField,
  jenksAvailable = true,
  onChange,
}: {
  value: LayerSymbology | undefined;
  availableFields: string[];
  themeColors: ThemeColors | undefined;
  runStatistics: StatQueryFn;
  sampleField: SampleFieldFn;
  // Certains hôtes (mapWidget.tsx) n'ont pas de collectionId résolu pour
  // échantillonner un champ : `sampleField` y lève systématiquement, donc
  // Jenks ne peut jamais fonctionner. Même précédent que l'option
  // "theme-primary" de la palette, conditionnelle sur `themeColors` : on
  // n'offre pas une méthode vouée à l'échec plutôt que de laisser l'auteur
  // la découvrir en cliquant "Recalculer" (I5 de la revue finale SP-25).
  jenksAvailable?: boolean;
  onChange: (value: LayerSymbology | undefined) => void;
}) {
  const [busy, setBusy] = useState<"color" | "size" | null>(null);
  const [colorError, setColorError] = useState<string | null>(null);
  const [sizeError, setSizeError] = useState<string | null>(null);
  // Id de datalist unique par instance : avec un id global, deux couches
  // stylées sur la même carte partageaient le même <datalist>, et le
  // navigateur résolvait toujours le `list=` de la 2e+ instance contre les
  // champs de la 1re (I2 de la revue finale SP-25). Même patron que
  // PopupEditor.tsx.
  const listId = useId();
  const color = value?.color;
  const size = value?.size;

  function setColorField(patch: Partial<NonNullable<LayerSymbology["color"]>>) {
    onChange({
      ...value,
      color: {
        field: color?.field ?? "",
        mode: color?.mode ?? "categorical",
        classification: color?.classification,
        palette: color?.palette ?? "categorical-a",
        domain: color?.domain ?? { kind: "categorical", values: [] },
        computedAt: color?.computedAt ?? "",
        ...patch,
      },
    });
  }

  // Seul chemin qui retire complètement l'encodage couleur — avant ce fix,
  // aucun code n'appelait jamais `onChange` avec `color` absent : vider le
  // champ texte laissait un objet `color` orphelin (`field: ""`) avec un
  // domaine périmé (C1 de la revue finale SP-25, déclencheur 2). Repasse
  // `symbology` à `undefined` plutôt qu'à `{}` si plus aucun encodage
  // n'est actif.
  function clearColor() {
    const { color: _color, ...rest } = value ?? {};
    onChange(rest.size ? rest : undefined);
  }

  function clearSize() {
    const { size: _size, ...rest } = value ?? {};
    onChange(rest.color ? rest : undefined);
  }

  async function recomputeColor() {
    if (!color?.field) return;
    setBusy("color");
    setColorError(null);
    try {
      const domain = await computeColorDomain(
        { field: color.field, mode: color.mode, classification: color.classification },
        { runStatistics, sampleField },
      );
      onChange({ ...value, color: { ...color, domain, computedAt: new Date().toISOString() } });
    } catch (e) {
      setColorError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  async function recomputeSize() {
    if (!size?.field) return;
    setBusy("size");
    setSizeError(null);
    try {
      const domain = await computeSizeDomain(size.field, { runStatistics });
      onChange({ ...value, size: { ...size, domain, computedAt: new Date().toISOString() } });
    } catch (e) {
      // Miroir exact de recomputeColor : sans ce catch, une requête en échec
      // (réseau, champ inconnu, ou le bug I5 "layer: ''" côté widget carte)
      // devenait une rejection non gérée sans aucun signal visible (I3 de
      // la revue finale SP-25).
      setSizeError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <label className={labelCls}>
        Champ couleur
        <input
          aria-label="Champ couleur"
          list={`${listId}-fields`}
          className={inputCls}
          value={color?.field ?? ""}
          onChange={(e) => setColorField({ field: e.target.value })}
        />
      </label>
      <datalist id={`${listId}-fields`}>
        {availableFields.map((f) => (
          <option key={f} value={f} />
        ))}
      </datalist>
      {color && (
        <button
          type="button"
          className="self-start text-xs text-red-700 underline"
          onClick={clearColor}
        >
          Retirer la couleur
        </button>
      )}
      {/* La palette est visible indépendamment d'un champ couleur choisi :
          un auteur peut préparer sa palette avant de sélectionner le champ,
          contrairement à la classification (qui, elle, n'a de sens que
          rapportée à un champ). */}
      <label className={labelCls}>
        Palette
        <select
          aria-label="Palette"
          className={inputCls}
          value={color?.palette ?? "categorical-a"}
          onChange={(e) => setColorField({ palette: e.target.value as PaletteId })}
        >
          {PALETTE_OPTIONS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
          {themeColors?.primary && <option value="theme-primary">Thème du site</option>}
        </select>
      </label>
      {color?.field && (
        <>
          <label className={labelCls}>
            Type de couleur
            <select
              aria-label="Type de couleur"
              className={inputCls}
              value={color.mode}
              onChange={(e) =>
                setColorField({
                  mode: e.target.value as "categorical" | "numeric",
                  classification:
                    e.target.value === "categorical" ? undefined : color.classification,
                })
              }
            >
              <option value="categorical">Catégoriel</option>
              <option value="numeric">Numérique</option>
            </select>
          </label>
          {color.mode === "numeric" && (
            <>
              <label className={labelCls}>
                Méthode de classification
                <select
                  aria-label="Méthode de classification"
                  className={inputCls}
                  value={color.classification?.method ?? "continuous"}
                  onChange={(e) => {
                    const v = e.target.value;
                    setColorField({
                      classification:
                        v === "continuous"
                          ? undefined
                          : ({
                              method: v,
                              classes: color.classification?.classes ?? 5,
                            } as ColorClassification),
                    });
                  }}
                >
                  <option value="continuous">Continu (dégradé)</option>
                  <option value="quantile">Quantiles</option>
                  <option value="equalInterval">Intervalles égaux</option>
                  {jenksAvailable && <option value="jenks">Seuils naturels (Jenks)</option>}
                </select>
              </label>
              {color.classification && (
                <label className={labelCls}>
                  Nombre de classes
                  <input
                    aria-label="Nombre de classes"
                    type="number"
                    min={2}
                    max={9}
                    className={inputCls}
                    value={color.classification.classes}
                    onChange={(e) =>
                      setColorField({
                        classification: {
                          ...color.classification!,
                          classes: Math.min(9, Math.max(2, Number(e.target.value) || 2)),
                        },
                      })
                    }
                  />
                </label>
              )}
            </>
          )}
          <button
            type="button"
            className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
            disabled={busy === "color"}
            onClick={() => void recomputeColor()}
          >
            {busy === "color" ? "Calcul…" : "Recalculer les classes"}
          </button>
          {colorError && (
            <p role="alert" className="text-xs text-red-600">
              {colorError}
            </p>
          )}
          {!color.computedAt && (
            <p className="text-xs text-amber-600">
              Classes non calculées — cliquez sur « Recalculer les classes ».
            </p>
          )}
          {color.computedAt && (
            <p className="text-xs text-slate-500">
              Classes calculées le {new Date(color.computedAt).toLocaleString()} :{" "}
              {formatDomain(color.domain)}
            </p>
          )}
        </>
      )}
      <label className={labelCls}>
        Champ taille
        <input
          aria-label="Champ taille"
          list={`${listId}-fields`}
          className={inputCls}
          value={size?.field ?? ""}
          onChange={(e) =>
            onChange({
              ...value,
              size: {
                field: e.target.value,
                domain: size?.domain ?? { min: 0, max: 0 },
                computedAt: size?.computedAt ?? "",
              },
            })
          }
        />
      </label>
      {size && (
        <button
          type="button"
          className="self-start text-xs text-red-700 underline"
          onClick={clearSize}
        >
          Retirer la taille
        </button>
      )}
      {size?.field && (
        <>
          <button
            type="button"
            className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
            disabled={busy === "size"}
            onClick={() => void recomputeSize()}
          >
            {busy === "size" ? "Calcul…" : "Recalculer la taille"}
          </button>
          {sizeError && (
            <p role="alert" className="text-xs text-red-600">
              {sizeError}
            </p>
          )}
          {!size.computedAt && (
            <p className="text-xs text-amber-600">
              Taille non calculée — cliquez sur « Recalculer la taille ».
            </p>
          )}
          {size.computedAt && (
            <p className="text-xs text-slate-500">
              Taille calculée le {new Date(size.computedAt).toLocaleString()} : {size.domain.min} –{" "}
              {size.domain.max}
            </p>
          )}
        </>
      )}
    </div>
  );
}
