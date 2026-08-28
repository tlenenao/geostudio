// SPDX-License-Identifier: Apache-2.0
// Extrait de MapSymbologyEditor.tsx (lignes 141-280 d'avant SP-27), sans
// changement de comportement : c'est le sous-éditeur « champ + palette +
// mode + classification + recalcul » utilisé par l'encodage COULEUR depuis
// SP-25, et désormais aussi par la couleur de CONTOUR (SP-27).
//
// Les libellés sont injectés, jamais littéraux : deux instances rendues en
// même temps (couleur et contour) auraient sinon des noms accessibles
// dupliqués, et les 16 tests existants de MapSymbologyEditor.test.tsx
// interrogent l'UI couleur par ces noms exacts. L'usage couleur passe donc
// les chaînes historiques au caractère près.
// `formatDomain` est DÉFINIE ici (déplacée depuis MapSymbologyEditor.tsx:30,
// où elle était module-privée) et exportée. Elle n'a jamais existé dans
// mapSymbology.ts (vérifié : grep → 2 occurrences, les deux dans l'éditeur).
import type {
  ClassifiedColorEncoding,
  ColorClassification,
  ColorDomain,
} from "../builder/widgets/mapSymbology";
import type { PaletteId } from "../builder/widgets/palette";
import type { ThemeColors } from "../api/types";
import { labelCls, inputCls } from "./formFieldStyles";

const PALETTE_OPTIONS: { id: Exclude<PaletteId, "theme-primary">; label: string }[] = [
  { id: "categorical-a", label: "Catégorielle A" },
  { id: "categorical-b", label: "Catégorielle B" },
  { id: "sequential-blue", label: "Séquentielle bleue" },
  { id: "sequential-warm", label: "Séquentielle chaude" },
];

export function formatDomain(domain: ColorDomain): string {
  if (domain.kind === "categorical") return domain.values.join(", ");
  if (domain.kind === "numeric-classed") return domain.breaks.map((b) => b.toFixed(1)).join(" – ");
  return `${domain.min} – ${domain.max}`;
}

// Alias local : le contrat canonique (`ClassifiedColorEncoding`, un champ,
// un mode, une palette persistée, une classification facultative, et le
// domaine FIGÉ avec son horodatage — invariant SP-25) est déclaré une seule
// fois dans mapSymbology.ts et référencé ici sous ce nom historique, plutôt
// que redéclaré (constat de revue Task 5, SP-27 : ce contrat existait avant
// en trois exemplaires qui divergeaient silencieusement).
export type ClassifiedEncoding = ClassifiedColorEncoding;

export type FieldClassificationLabels = {
  field: string;
  palette: string;
  mode: string;
  method: string;
  classes: string;
  recompute: string;
};

export function FieldClassificationPicker({
  labels,
  listId,
  themeColors,
  jenksAvailable,
  busy,
  error,
  value,
  onChange,
  onRecompute,
}: {
  labels: FieldClassificationLabels;
  // L'id de datalist est FOURNI par l'hôte, et l'ÉLÉMENT <datalist> reste
  // chez l'hôte : ce composant ne fait que `list={`${listId}-fields`}`. Deux
  // pickers d'un même éditeur partagent donc une seule liste de champs, avec
  // un seul élément dans le DOM. Rendre le <datalist> ici produirait deux
  // éléments de même id dès qu'un contour classé est configuré (constat I4) —
  // exactement la classe de défaut I2 de la revue finale SP-25.
  listId: string;
  themeColors: ThemeColors | undefined;
  jenksAvailable: boolean;
  busy: boolean;
  error: string | null;
  value: ClassifiedEncoding | undefined;
  onChange: (patch: Partial<ClassifiedEncoding>) => void;
  onRecompute: () => void;
}) {
  return (
    <>
      <label className={labelCls}>
        {labels.field}
        <input
          aria-label={labels.field}
          list={`${listId}-fields`}
          className={inputCls}
          value={value?.field ?? ""}
          onChange={(e) => onChange({ field: e.target.value })}
        />
      </label>
      {/* La palette est visible indépendamment d'un champ choisi : un auteur
          peut préparer sa palette avant de sélectionner le champ,
          contrairement à la classification (qui, elle, n'a de sens que
          rapportée à un champ). */}
      <label className={labelCls}>
        {labels.palette}
        <select
          aria-label={labels.palette}
          className={inputCls}
          value={value?.palette ?? "categorical-a"}
          onChange={(e) => onChange({ palette: e.target.value as PaletteId })}
        >
          {PALETTE_OPTIONS.map((p) => (
            <option key={p.id} value={p.id}>
              {p.label}
            </option>
          ))}
          {themeColors?.primary && <option value="theme-primary">Thème du site</option>}
        </select>
      </label>
      {value?.field && (
        <>
          <label className={labelCls}>
            {labels.mode}
            <select
              aria-label={labels.mode}
              className={inputCls}
              // Repli sur "categorical" : `mode` est obligatoire dans
              // `ClassifiedColorEncoding`, mais un document écrit à la main
              // ou par le MCP peut porter un contour data-driven sans ce
              // champ (constat C de la revue finale Task 5, SP-27). Sans ce
              // repli, `value.mode` vaut `undefined` et ce <select> devient
              // non contrôlé. Contrairement à <input>, react-dom n'émet
              // aucun avertissement console pour un <select> qui bascule
              // ainsi (vérifié dans sa source : le check "changing an
              // uncontrolled input to be controlled" n'existe que dans la
              // branche `case "input"`, pas `case "select"`) — le défaut est
              // silencieux : React cesse simplement de piloter l'option
              // sélectionnée, qui peut diverger du modèle après toute
              // interaction native.
              value={value.mode ?? "categorical"}
              onChange={(e) =>
                onChange({
                  mode: e.target.value as "categorical" | "numeric",
                  classification:
                    e.target.value === "categorical" ? undefined : value.classification,
                })
              }
            >
              <option value="categorical">Catégoriel</option>
              <option value="numeric">Numérique</option>
            </select>
          </label>
          {value.mode === "numeric" && (
            <>
              <label className={labelCls}>
                {labels.method}
                <select
                  aria-label={labels.method}
                  className={inputCls}
                  value={value.classification?.method ?? "continuous"}
                  onChange={(e) => {
                    const v = e.target.value;
                    onChange({
                      classification:
                        v === "continuous"
                          ? undefined
                          : ({
                              method: v,
                              classes: value.classification?.classes ?? 5,
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
              {value.classification && (
                <label className={labelCls}>
                  {labels.classes}
                  <input
                    aria-label={labels.classes}
                    type="number"
                    min={2}
                    max={9}
                    className={inputCls}
                    value={value.classification.classes}
                    onChange={(e) =>
                      onChange({
                        classification: {
                          ...value.classification!,
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
            disabled={busy}
            onClick={onRecompute}
          >
            {busy ? "Calcul…" : labels.recompute}
          </button>
          {error && (
            <p role="alert" className="text-xs text-red-600">
              {error}
            </p>
          )}
          {/* L'avertissement nomme le bouton réellement rendu : pour l'usage
              couleur `labels.recompute` vaut « Recalculer les classes », donc
              la phrase est identique au caractère près à celle d'avant
              l'extraction. */}
          {!value.computedAt && (
            <p className="text-xs text-amber-600">
              Classes non calculées — cliquez sur « {labels.recompute} ».
            </p>
          )}
          {value.computedAt && (
            <p className="text-xs text-slate-500">
              Classes calculées le {new Date(value.computedAt).toLocaleString()} :{" "}
              {formatDomain(value.domain)}
            </p>
          )}
        </>
      )}
    </>
  );
}
