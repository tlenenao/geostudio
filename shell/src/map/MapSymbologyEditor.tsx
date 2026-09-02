// SPDX-License-Identifier: Apache-2.0
import { useEffect, useId, useRef, useState } from "react";
import {
  computeColorDomain,
  computeSizeDomain,
  type IconRef,
  type LayerStroke,
  type LayerSymbology,
  type SampleFieldFn,
  type StatQueryFn,
  type StrokeStyle,
} from "../builder/widgets/mapSymbology";
import { LUCIDE_ICONS, type IconCategory } from "../builder/widgets/iconLibrary";
import { Button } from "../ui/kit/Button";
import { FieldClassificationPicker, type ClassifiedEncoding } from "./FieldClassificationPicker";
import { labelCls, inputCls } from "./formFieldStyles";
import type { ThemeColors } from "../api/types";

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
  listCustomIcons,
  uploadCustomIcon,
  deleteCustomIcon,
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
  // Optionnelles : ce composant est rendu inline dans 18 tests et à deux
  // sites de production ; les rendre obligatoires ferait échouer
  // `tsc --noEmit` partout. Absentes ⇒ la section « icônes personnalisées »
  // n'est simplement pas proposée.
  listCustomIcons?: () => Promise<{ id: string; title: string; category: string }[]>;
  uploadCustomIcon?: (file: File, title: string, category: string) => Promise<{ id: string }>;
  deleteCustomIcon?: (id: string) => Promise<void>;
  onChange: (value: LayerSymbology | undefined) => void;
}) {
  const [busy, setBusy] = useState<"color" | "size" | null>(null);
  const [colorError, setColorError] = useState<string | null>(null);
  const [sizeError, setSizeError] = useState<string | null>(null);
  const [strokeBusy, setStrokeBusy] = useState(false);
  const [strokeError, setStrokeError] = useState<string | null>(null);
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

  const icon = value?.icon;
  // Booléen dédié : `useState("")` + `iconField !== undefined` était
  // toujours vrai, donc le bloc s'affichait en permanence et le bouton
  // « Ajouter des icônes » n'avait aucun effet observable.
  const [iconDraft, setIconDraft] = useState(false);
  const [iconField, setIconField] = useState(icon?.field ?? "");
  // Fix I4 de la revue finale SP-27 : `iconField` ne se resynchronisait
  // qu'au montage (initialiseur de useState, jamais réévalué) — TOUS les
  // autres contrôles de cet éditeur lisent `value` directement (`stroke`,
  // `value?.opacity`…) et suivent donc naturellement un changement externe de
  // `value`, mais `iconField` gardait sa propre copie. Ça désynchronise à
  // travers l'undo/redo de SP-19 (le composant ne démonte pas ; `value.icon`
  // change sous lui sans que `iconField` ne suive), et « Recalculer les
  // valeurs » pouvait alors réécrire dans le document le NOM DE CHAMP
  // périmé, ré-appliquant un changement que l'utilisateur venait d'annuler.
  //
  // Effet clé sur `icon?.field` (un primitif), pas sur `icon` (l'objet) :
  // il ne se redéclenche donc QUE quand le nom de champ committé change
  // réellement, jamais à cause d'un rendu du parent qui touche une autre
  // partie de `value` (couleur, contour…) pendant que l'auteur tape encore
  // un nom de champ non validé — `iconField` reste la brouillon local tant
  // que « Recalculer les valeurs » (recomputeIconDomain) n'a pas committé le
  // même nom dans `icon.field`, moment où cet effet et le state restent de
  // toute façon déjà d'accord (no-op).
  useEffect(() => {
    setIconField(icon?.field ?? "");
  }, [icon?.field]);
  const [iconBusy, setIconBusy] = useState(false);
  const [iconError, setIconError] = useState<string | null>(null);
  const [editingValue, setEditingValue] = useState<string | null>(null);
  const [customIcons, setCustomIcons] = useState<{ id: string; title: string; category: string }[]>(
    [],
  );

  // La prop peut être une flèche inline recréée à chaque rendu de l'hôte
  // (c'est le style des autres props fonction de ce composant) : la lire par
  // ref et ne dépendre de rien évite la boucle « effet → setState → nouvelle
  // identité → effet ».
  const listCustomIconsRef = useRef(listCustomIcons);
  useEffect(() => {
    listCustomIconsRef.current = listCustomIcons;
  }, [listCustomIcons]);
  useEffect(() => {
    const fn = listCustomIconsRef.current;
    if (!fn) return;
    let cancelled = false;
    // try/catch OBLIGATOIRE autour de l'appel lui-même : `fn` peut LEVER
    // SYNCHRONIQUEMENT (un hôte dont le client est partiel — voir le défaut
    // n° 5 de l'en-tête de cette tâche, mesuré). Un `.catch()` seul
    // n'attraperait rien, parce qu'il n'y a pas encore de promesse quand
    // l'exception part, et l'exception sortirait du callback d'effet en
    // faisant échouer le rendu.
    try {
      void fn()
        .then((icons) => {
          if (!cancelled) setCustomIcons(icons);
        })
        .catch(() => {
          // Bibliothèque indisponible : la grille Lucide reste utilisable.
          if (!cancelled) setCustomIcons([]);
        });
    } catch {
      setCustomIcons([]);
    }
    return () => {
      cancelled = true;
    };
  }, []);

  async function recomputeIconDomain() {
    if (!iconField) return;
    setIconBusy(true);
    setIconError(null);
    try {
      const domain = await computeColorDomain(
        { field: iconField, mode: "categorical" },
        { runStatistics, sampleField },
      );
      if (domain.kind !== "categorical") {
        setIconError("Ce champ n'a pas de valeurs catégorielles exploitables.");
        return;
      }
      onChange({
        ...value,
        icon: {
          field: iconField,
          domain,
          mapping: icon?.mapping ?? {},
          ...(icon?.fallback ? { fallback: icon.fallback } : {}),
        },
      });
    } catch (e) {
      setIconError(e instanceof Error ? e.message : String(e));
    } finally {
      setIconBusy(false);
    }
  }

  function assignIcon(forValue: string, ref: IconRef) {
    if (!icon) return;
    onChange({ ...value, icon: { ...icon, mapping: { ...icon.mapping, [forValue]: ref } } });
    setEditingValue(null);
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
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="self-start"
            disabled={busy === "size"}
            onClick={() => void recomputeSize()}
          >
            {busy === "size" ? "Calcul…" : "Recalculer la taille"}
          </Button>
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
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="self-start"
          onClick={() => setStroke({})}
        >
          Ajouter un contour
        </Button>
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
                // Même reset qu'au passage en mode fixe (constat D de la
                // revue finale Task 5, SP-27) : sans lui, le chemin erreur de
                // recalcul → « Retirer le contour » → « Ajouter un contour »
                // → « par attribut » faisait réapparaître une erreur périmée.
                setStrokeError(null);
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
              // Libellés structurellement distincts de ceux de l'usage
              // couleur (constat A de la revue finale Task 5, SP-27) : aucun
              // des six ne doit contenir un libellé couleur comme
              // sous-chaîne, ni l'inverse — `getByLabel`/`getByRole({ name })`
              // de Playwright matchent en sous-chaîne (et insensible à la
              // casse) par défaut, contrairement à `getByLabelText` de
              // Testing Library qui matche exact. Vérifié mécaniquement
              // (cf. rapport de tâche), pas seulement à l'œil.
              labels={{
                field: "Champ du contour",
                palette: "Couleurs du contour",
                mode: "Type de valeurs du contour",
                method: "Méthode de répartition du contour",
                classes: "Nombre de tranches du contour",
                recompute: "Recalculer le contour",
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
      {!icon && !iconDraft && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="self-start"
          onClick={() => setIconDraft(true)}
        >
          Ajouter des icônes
        </Button>
      )}
      {(icon || iconDraft) && (
        <div className="flex flex-col gap-2 border-l-2 border-slate-200 pl-2">
          <label className={labelCls}>
            Champ icône
            <input
              aria-label="Champ icône"
              list={`${listId}-fields`}
              className={inputCls}
              value={iconField}
              onChange={(e) => setIconField(e.target.value)}
            />
          </label>
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="self-start"
            disabled={iconBusy || !iconField}
            onClick={() => void recomputeIconDomain()}
          >
            {iconBusy ? "Calcul…" : "Recalculer les valeurs"}
          </Button>
          {iconError && <p className="text-xs text-red-700">{iconError}</p>}

          {icon?.domain.values.map((v) => {
            const assigned = icon.mapping[v];
            return (
              <div key={v} className="flex items-center gap-2">
                <span className="text-xs font-medium">{v}</span>
                <button
                  type="button"
                  aria-label={`Choisir l'icône de ${v}`}
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs"
                  onClick={() => setEditingValue(editingValue === v ? null : v)}
                >
                  {assigned
                    ? assigned.source === "lucide"
                      ? assigned.name
                      : (customIcons.find((c) => c.id === assigned.id)?.title ?? "icône")
                    : "Aucune"}
                </button>
              </div>
            );
          })}

          {/* UNE seule grille, pour la seule valeur en cours d'édition : la
              rendre par valeur de domaine produisait 140 × N boutons et des
              noms accessibles dupliqués, donc un getByRole ambigu. */}
          {editingValue !== null && (
            <div className="flex flex-col gap-1" data-testid="icon-grid">
              <p className="text-xs">Icône pour « {editingValue} »</p>
              {(
                [
                  "generic",
                  "buildings",
                  "nature",
                  "transport",
                  "services",
                  "safety-health",
                  "leisure",
                ] as IconCategory[]
              ).map((category) => (
                <div key={category} className="flex flex-col gap-1">
                  <h4 className="text-[10px] uppercase text-slate-500">{category}</h4>
                  <div className="flex flex-wrap gap-1">
                    {LUCIDE_ICONS.filter((li) => li.category === category).map((li) => (
                      <button
                        key={li.name}
                        type="button"
                        role="img"
                        aria-label={li.name}
                        title={li.name}
                        className="h-6 w-6 rounded border border-slate-200"
                        onClick={() =>
                          assignIcon(editingValue, { source: "lucide", name: li.name })
                        }
                      />
                    ))}
                  </div>
                </div>
              ))}
              {customIcons.length > 0 && (
                <div className="flex flex-col gap-1">
                  <h4 className="text-[10px] uppercase text-slate-500">Bibliothèque du tenant</h4>
                  <div className="flex flex-wrap gap-1">
                    {customIcons.map((ci) => (
                      <span key={ci.id} className="flex items-center gap-1">
                        <button
                          type="button"
                          role="img"
                          aria-label={ci.title}
                          className="h-6 w-6 rounded border border-slate-200"
                          onClick={() => assignIcon(editingValue, { source: "custom", id: ci.id })}
                        />
                        {deleteCustomIcon && (
                          <button
                            type="button"
                            aria-label={`Supprimer l'icône ${ci.title}`}
                            className="text-[10px] text-red-700 underline"
                            onClick={() => {
                              // Fix I3 (Part B) de la revue finale SP-27 : le cœur ne fait
                              // AUCUN comptage de références — supprimer une icône laisse
                              // toute entrée `symbology.icon.mapping` qui la référençait
                              // encore (`{source: "custom", id}`) pointer dans le vide.
                              // `loadIconImages`/`fetchMapIconBlob` avalent alors le 404
                              // dans un `console.warn` (MapView.tsx) : la catégorie
                              // affectée perd silencieusement son icône sur TOUTE carte qui
                              // l'utilisait, sans rien qui l'explique dans cet éditeur. Un
                              // comptage de références ou une tombe côté cœur est hors
                              // périmètre de ce correctif (suivi non bloquant) — seule cette
                              // confirmation, qui nomme la conséquence, est demandée ici.
                              if (
                                !window.confirm(
                                  `Cette icône est peut-être utilisée par des cartes existantes ; la supprimer la fera disparaître sans avertissement sur ces cartes. Supprimer « ${ci.title} » ?`,
                                )
                              )
                                return;
                              // Fix I3 (Part A) : même convention d'erreur que le champ
                              // d'import juste en dessous — sans elle, un échec (404,
                              // réseau, session révoquée) devenait une rejection non gérée
                              // et l'icône restait affichée comme si de rien n'était.
                              setIconError(null);
                              void deleteCustomIcon(ci.id)
                                .then(() =>
                                  setCustomIcons((prev) => prev.filter((c) => c.id !== ci.id)),
                                )
                                .catch((err) =>
                                  setIconError(err instanceof Error ? err.message : String(err)),
                                );
                            }}
                          >
                            ×
                          </button>
                        )}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {uploadCustomIcon && (
            <label className={labelCls}>
              Ajouter une icône au tenant (PNG ou SVG)
              <input
                aria-label="Ajouter une icône au tenant (PNG ou SVG)"
                type="file"
                accept="image/png,image/svg+xml"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (!file) return;
                  setIconError(null);
                  void uploadCustomIcon(file, file.name, "generic")
                    .then((created) =>
                      setCustomIcons((prev) => [
                        ...prev,
                        { id: created.id, title: file.name, category: "generic" },
                      ]),
                    )
                    .catch((err) => setIconError(err instanceof Error ? err.message : String(err)));
                }}
              />
            </label>
          )}

          {icon && (
            <button
              type="button"
              className="self-start text-xs text-red-700 underline"
              onClick={() => {
                setIconDraft(false);
                setEditingValue(null);
                clearEncoding("icon");
              }}
            >
              Retirer les icônes
            </button>
          )}
        </div>
      )}

      {!value?.label && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className="self-start"
          onClick={() =>
            onChange({
              ...value,
              label: {
                template: "",
                size: 12,
                color: "#1e293b",
                haloColor: "#ffffff",
                haloWidth: 1,
              },
            })
          }
        >
          Ajouter une étiquette
        </Button>
      )}
      {value?.label && (
        <div className="flex flex-col gap-2 border-l-2 border-slate-200 pl-2">
          <label className={labelCls}>
            Gabarit d'étiquette
            <textarea
              aria-label="Gabarit d'étiquette"
              className={inputCls}
              rows={2}
              value={value.label.template}
              onChange={(e) =>
                onChange({ ...value, label: { ...value.label!, template: e.target.value } })
              }
            />
          </label>
          <p className="text-xs text-slate-500">
            {'Syntaxe : ${record.nom}, ${record.pop > 10000 ? "ville" : "commune"}'}
          </p>
          <label className={labelCls}>
            Taille du texte (px)
            <input
              aria-label="Taille du texte (px)"
              type="number"
              min={8}
              max={32}
              className={inputCls}
              value={value.label.size}
              onChange={(e) =>
                onChange({
                  ...value,
                  label: { ...value.label!, size: Number(e.target.value) },
                })
              }
            />
          </label>
          <label className={labelCls}>
            Couleur du texte
            <input
              aria-label="Couleur du texte"
              type="color"
              value={value.label.color}
              onChange={(e) =>
                onChange({ ...value, label: { ...value.label!, color: e.target.value } })
              }
            />
          </label>
          <button
            type="button"
            className="self-start text-xs text-red-700 underline"
            onClick={() => clearEncoding("label")}
          >
            Retirer l'étiquette
          </button>
        </div>
      )}
    </div>
  );
}
