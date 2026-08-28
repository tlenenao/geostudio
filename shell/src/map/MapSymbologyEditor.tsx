// SPDX-License-Identifier: Apache-2.0
import { useId, useState } from "react";
import {
  computeColorDomain,
  computeSizeDomain,
  type LayerStroke,
  type LayerSymbology,
  type SampleFieldFn,
  type StatQueryFn,
  type StrokeStyle,
} from "../builder/widgets/mapSymbology";
import { FieldClassificationPicker, type ClassifiedEncoding } from "./FieldClassificationPicker";
import type { ThemeColors } from "../api/types";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-8 rounded-md border border-slate-300 px-2 text-sm";

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

  // Un seul chemin de retrait pour TOUS les encodages : la version
  // précédente testait « reste-t-il l'AUTRE encodage historique ? »
  // (rest.size / rest.color), ce qui détruisait silencieusement stroke,
  // opacity, label et icon (piège n°4 de CLAUDE.md, régression C1 de
  // SP-25). Ne jamais réintroduire de test nommant un encodage précis.
  function clearEncoding(key: keyof LayerSymbology) {
    const rest = { ...(value ?? {}) };
    delete rest[key];
    onChange(Object.keys(rest).length > 0 ? rest : undefined);
  }

  function clearColor() {
    clearEncoding("color");
  }

  function clearSize() {
    clearEncoding("size");
  }

  const stroke = value?.stroke;

  function setStroke(patch: Partial<LayerStroke>) {
    onChange({
      ...value,
      stroke: {
        color: stroke?.color ?? { fixed: "#000000" },
        width: stroke?.width ?? { fixed: 1 },
        style: stroke?.style ?? "solid",
        ...patch,
      },
    });
  }

  const [strokeBusy, setStrokeBusy] = useState(false);
  const [strokeError, setStrokeError] = useState<string | null>(null);
  const strokeColorIsFixed = !!stroke && "fixed" in stroke.color;

  function setStrokeColorPatch(patch: Partial<ClassifiedEncoding>) {
    if (!stroke || "fixed" in stroke.color) return;
    setStroke({ color: { ...stroke.color, ...patch } });
  }

  async function recomputeStrokeDomain() {
    if (!stroke || "fixed" in stroke.color || !stroke.color.field) return;
    const encoding = stroke.color;
    setStrokeBusy(true);
    setStrokeError(null);
    try {
      const domain = await computeColorDomain(
        {
          field: encoding.field,
          mode: encoding.mode,
          classification: encoding.classification,
        },
        { runStatistics, sampleField },
      );
      // Invariant SP-25 : on FIGE le domaine et l'horodatage dans le
      // document ; le rendu (buildMapPaint) ne recalcule jamais.
      setStroke({ color: { ...encoding, domain, computedAt: new Date().toISOString() } });
    } catch (e) {
      setStrokeError(e instanceof Error ? e.message : String(e));
    } finally {
      setStrokeBusy(false);
    }
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
      <FieldClassificationPicker
        labels={{
          field: "Champ couleur",
          palette: "Palette",
          mode: "Type de couleur",
          method: "Méthode de classification",
          classes: "Nombre de classes",
          recompute: "Recalculer les classes",
        }}
        listId={listId}
        themeColors={themeColors}
        jenksAvailable={jenksAvailable}
        busy={busy === "color"}
        error={colorError}
        value={color}
        onChange={setColorField}
        onRecompute={() => void recomputeColor()}
      />
      {/* UN SEUL <datalist> par instance d'éditeur, chez l'hôte : deux
          pickers coexistants (couleur et contour) partagent cet id, et le
          champ « Champ taille » plus bas le référence aussi. */}
      <datalist id={`${listId}-fields`}>
        {availableFields.map((f) => (
          <option key={f} value={f} />
        ))}
      </datalist>
      {/* Le retrait d'un encodage appartient à l'éditeur, pas au
          sous-éditeur : le contour a son propre bouton de retrait. */}
      {color && (
        <button
          type="button"
          className="self-start text-xs text-red-700 underline"
          onClick={clearColor}
        >
          Retirer la couleur
        </button>
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
      <label className={labelCls}>
        Opacité
        <input
          aria-label="Opacité"
          type="range"
          min={0}
          max={100}
          step={5}
          className="w-full"
          value={value?.opacity ?? 100}
          onChange={(e) => onChange({ ...value, opacity: Number(e.target.value) })}
        />
      </label>
      {!stroke && (
        <button
          type="button"
          className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs"
          onClick={() => setStroke({})}
        >
          Ajouter un contour
        </button>
      )}
      {stroke && (
        <div className="flex flex-col gap-2 border-l-2 border-slate-200 pl-2">
          <div className="flex gap-1">
            <button
              type="button"
              className={`rounded-md border border-slate-300 px-2 py-1 text-xs ${
                strokeColorIsFixed ? "bg-slate-200" : ""
              }`}
              aria-pressed={strokeColorIsFixed}
              onClick={() => {
                // Reclic sur le mode déjà actif : no-op. Sans ce garde, une
                // couleur fixe choisie par l'utilisateur (ex. #ff0000) était
                // écrasée par la valeur par défaut à chaque reclic (Important
                // de la revue finale Task 5, SP-27).
                if (strokeColorIsFixed) return;
                // Miroir du reset de colorError/sizeError sur les chemins
                // d'écriture voisins : sans lui, une erreur de recalcul du
                // contour survivait au passage en mode fixe et réapparaissait
                // telle quelle au retour en mode « par attribut ».
                setStrokeError(null);
                setStroke({ color: { fixed: "#000000" } });
              }}
            >
              Couleur de contour fixe
            </button>
            <button
              type="button"
              className={`rounded-md border border-slate-300 px-2 py-1 text-xs ${
                !strokeColorIsFixed ? "bg-slate-200" : ""
              }`}
              aria-pressed={!strokeColorIsFixed}
              onClick={() => {
                // Reclic sur le mode déjà actif : no-op. Sans ce garde, un
                // champ/palette/classification déjà choisis — et surtout un
                // domaine déjà calculé via `runStatistics` — étaient perdus à
                // chaque reclic (Important de la revue finale Task 5, SP-27).
                if (!strokeColorIsFixed) return;
                setStroke({
                  color: {
                    field: "",
                    mode: "categorical",
                    palette: "categorical-a",
                    domain: { kind: "categorical", values: [] },
                    computedAt: "",
                  },
                });
              }}
            >
              Couleur de contour par attribut
            </button>
          </div>
          {strokeColorIsFixed ? (
            <label className={labelCls}>
              Couleur de contour
              <input
                aria-label="Couleur de contour"
                type="color"
                value={"fixed" in stroke.color ? stroke.color.fixed : "#000000"}
                onChange={(e) => setStroke({ color: { fixed: e.target.value } })}
              />
            </label>
          ) : (
            <FieldClassificationPicker
              labels={{
                field: "Champ couleur de contour",
                palette: "Palette du contour",
                mode: "Type de couleur de contour",
                method: "Méthode de classification du contour",
                classes: "Nombre de classes du contour",
                recompute: "Recalculer les classes du contour",
              }}
              listId={listId}
              themeColors={themeColors}
              jenksAvailable={jenksAvailable}
              busy={strokeBusy}
              error={strokeError}
              value={"fixed" in stroke.color ? undefined : stroke.color}
              onChange={setStrokeColorPatch}
              onRecompute={() => void recomputeStrokeDomain()}
            />
          )}
          <label className={labelCls}>
            Épaisseur de contour (px)
            <input
              aria-label="Épaisseur de contour (px)"
              type="number"
              min={0}
              max={20}
              className={inputCls}
              value={"fixed" in stroke.width ? stroke.width.fixed : 1}
              onChange={(e) => setStroke({ width: { fixed: Number(e.target.value) } })}
            />
          </label>
          <label className={labelCls}>
            Style de contour
            <select
              aria-label="Style de contour"
              className={inputCls}
              value={stroke.style}
              onChange={(e) => setStroke({ style: e.target.value as StrokeStyle })}
            >
              <option value="solid">Plein</option>
              <option value="dashed">Tirets</option>
              <option value="dotted">Pointillés</option>
            </select>
          </label>
          <button
            type="button"
            className="self-start text-xs text-red-700 underline"
            onClick={() => clearEncoding("stroke")}
          >
            Retirer le contour
          </button>
        </div>
      )}
    </div>
  );
}
