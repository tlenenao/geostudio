# SP-34 — Dette de tokens LayersPanel/MapSymbologyEditor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer les couleurs Tailwind brutes (`slate-*`, `red-*`, `amber-*`, `blue-700`, `white`) par les tokens sémantiques (`ink`/`ink-2`/`ink-3`/`rule`/`rule-2`/`danger`/`warn`/`accent`/`surface`/`sunken`) et les `<button>` natifs autonomes par le `Button` du kit, sur les 8 fichiers de `shell/src/map/` listés dans la spec — sans aucun changement de comportement.

**Architecture :** Passe purement visuelle/structurelle, fichier par fichier, dans l'ordre des dépendances (`formFieldStyles.ts` d'abord, car deux fichiers l'importent). Chaque tâche modifie un seul fichier (ou une seule moitié d'un gros fichier), fait tourner son fichier de test associé avant/après, grep-vérifie l'absence de couleur brute résiduelle, puis commit. Aucun nouveau composant, aucune nouvelle dépendance : uniquement le `Button` du kit déjà existant (`shell/src/ui/kit/Button.tsx`), déjà consommé ailleurs dans `shell/src/map/` (`LayerPicker.tsx`, `CameraControls.tsx`, `Terrain3DUploadButton.tsx`).

**Tech Stack :** React 18 + TypeScript, Tailwind CSS v4 (tokens définis dans `shell/src/styles/tokens.css`), Vitest + Testing Library, Playwright (E2E, vérification finale seulement).

## Global Constraints

Ces contraintes viennent de `docs/superpowers/specs/2026-09-03-sp34-dette-tokens-layerspanel-design.md` et s'appliquent à toutes les tâches ci-dessous :

- **Périmètre fermé à 8 fichiers**, tous sous `shell/src/map/` : `formFieldStyles.ts`, `FieldClassificationPicker.tsx`, `MapSymbologyEditor.tsx`, `PopupEditor.tsx`, `LayersPanel.tsx`, `MapMeasureSketchToolbar.tsx`, `MapPopup.tsx`, `MapLegend.tsx`. Ne pas toucher `LayerPicker.tsx` (dette distincte, hors périmètre).
- **Mapping couleur → token** (table complète de la spec) :
  `border-slate-300`→`border-rule` · `border-slate-200`→`border-rule-2` · `bg-slate-200`→`bg-sunken` · `text-slate-500`/`text-slate-400`→`text-ink-3` · `text-red-700`/`text-red-600`→`text-danger` · `text-amber-600`→`text-warn` · `text-blue-700`→`text-accent` · `bg-white`/`bg-white/90`→`bg-surface`/`bg-surface/90`.
- **`<button>` natif → `Button` du kit** UNIQUEMENT pour les actions autonomes non répétées (idiome exact déjà utilisé par `CameraControls.tsx` : `<Button type="button" size="sm" variant="outline" onClick={...}>Label</Button>`). Reste natif : (a) tout bouton stylé en lien inline (`underline`), (b) tout bouton répété par ligne/item dans une liste dense (grille d'icônes, lignes ↑/↓/👁/✕ de `LayersPanel`, lignes de champ de `PopupEditor`, toggle `aria-pressed` de mode contour, barre d'outils `MapMeasureSketchToolbar`).
- **Hauteur des contrôles** : `h-8`→`h-9` par défaut sur les contrôles de formulaire non denses ; **exception** — un contrôle répété par ligne dans une liste dense reste `h-8`.
- **Hors périmètre, à ne PAS faire dans ce plan** : conversion des `<select>`/`<input list=…>` vers `Select`/`Combobox` du kit ; conversion du toggle contour fixe/attribut vers `Segmented` ; tout changement de comportement (ne pas toucher aux invariants I2–I16/M2/M7 documentés en commentaire) ; ajout de `bg-surface`/`text-ink` sur des `<input>`/`<select>` qui n'avaient auparavant AUCUNE classe de couleur (dette pré-existante, non couverte par la table de mapping — ne pas l'étendre de sa propre initiative).
- **Aucun nouveau test, aucune nouvelle infrastructure de test** (pas de `expectTokenizedClasses()` sur ces fichiers consommateurs — ce mécanisme reste réservé aux primitives du kit). Le filet est : le fichier de test existant reste vert sans modification + un grep de clôture.
- Import du kit `Button` : `import { Button } from "../ui/kit/Button";` (chemin relatif vérifié contre `LayerPicker.tsx`/`CameraControls.tsx`).
- Toutes les commandes ci-dessous s'exécutent depuis `shell/` (`cd /home/lenen/projets/geostudio/shell` en début de session si besoin).

---

## Task 1: `formFieldStyles.ts` — tokens + hauteur

**Files:**
- Modify: `shell/src/map/formFieldStyles.ts`
- Test: `shell/src/map/FieldClassificationPicker.test.tsx`, `shell/src/map/MapSymbologyEditor.test.tsx` (consommateurs indirects — ce fichier n'a pas son propre test)

**Interfaces:**
- Consomme : rien (fichier de constantes pur)
- Produit : `labelCls`/`inputCls` (mêmes noms et même type `string`) consommés par `FieldClassificationPicker.tsx` et `MapSymbologyEditor.tsx` (imports existants, inchangés) et, à partir de la Task 5, par `PopupEditor.tsx`

- [ ] **Step 1: Run the two consumer test files to confirm the green baseline**

Run: `npx vitest run src/map/FieldClassificationPicker.test.tsx src/map/MapSymbologyEditor.test.tsx`
Expected: PASS (tous les tests existants verts)

- [ ] **Step 2: Edit the file**

Remplacer tout le contenu de `shell/src/map/formFieldStyles.ts` par :

```ts
// SPDX-License-Identifier: Apache-2.0
// Classes Tailwind partagées par les éditeurs de carte qui composent un
// formulaire label+input simple. Centralisées ici plutôt que copiées : avant
// ce fichier, MapSymbologyEditor.tsx et FieldClassificationPicker.tsx en
// avaient chacun leur propre copie identique (constat de revue Task 5,
// SP-27) — et les tâches 12/14 allaient propager cette copie si on la
// laissait. Un petit module de constantes plutôt qu'un export de l'un vers
// l'autre : ni fichier n'a besoin d'importer l'autre pour ces deux chaînes.
export const labelCls = "flex flex-col gap-1";
export const inputCls = "h-9 rounded-md border border-rule px-2 text-sm";
```

(Seul changement réel : `h-8`→`h-9` et `border-slate-300`→`border-rule` sur la ligne `inputCls`. Le commentaire existant reste tel quel — il documente toujours pourquoi ce fichier existe, pas ce qu'il contient.)

- [ ] **Step 3: Grep-check no raw color remains in this file**

Run: `grep -n "slate\|red-[0-9]\|amber-[0-9]\|blue-700\|bg-white" src/map/formFieldStyles.ts`
Expected: no output (empty)

- [ ] **Step 4: Re-run the two consumer test files**

Run: `npx vitest run src/map/FieldClassificationPicker.test.tsx src/map/MapSymbologyEditor.test.tsx`
Expected: PASS, aucune régression (le changement de `h-8`→`h-9` ne casse aucune assertion existante — vérifié : aucun test de ces deux fichiers n'affirme `toHaveClass`/`h-8`)

- [ ] **Step 5: Commit**

```bash
git add src/map/formFieldStyles.ts
git commit -m "style(shell): tokenise formFieldStyles.ts et relève sa hauteur à h-9 (SP-34)"
```

---

## Task 2: `FieldClassificationPicker.tsx` — tokens + Button

**Files:**
- Modify: `shell/src/map/FieldClassificationPicker.tsx`
- Test: `shell/src/map/FieldClassificationPicker.test.tsx`

**Interfaces:**
- Consomme : `Button` de `../ui/kit/Button` (nouveau import), `labelCls`/`inputCls` de `./formFieldStyles` (déjà importés, valeurs changées par Task 1)
- Produit : aucune API publique changée — `FieldClassificationPickerLabels`, la signature du composant, restent identiques

- [ ] **Step 1: Run the test file to confirm the green baseline**

Run: `npx vitest run src/map/FieldClassificationPicker.test.tsx`
Expected: PASS

- [ ] **Step 2: Add the Button import**

Dans `shell/src/map/FieldClassificationPicker.tsx`, après le dernier import existant (`import { labelCls, inputCls } from "./formFieldStyles";`), ajouter :

```ts
import { Button } from "../ui/kit/Button";
```

- [ ] **Step 3: Convert the standalone "recompute" button to the kit Button**

Remplacer :

```tsx
          <button
            type="button"
            className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
            disabled={busy}
            onClick={onRecompute}
          >
            {busy ? "Calcul…" : labels.recompute}
          </button>
```

par :

```tsx
          <Button
            type="button"
            size="sm"
            variant="outline"
            className="self-start"
            disabled={busy}
            onClick={onRecompute}
          >
            {busy ? "Calcul…" : labels.recompute}
          </Button>
```

- [ ] **Step 4: Tokenize the three remaining raw colors**

Remplacer (une seule occurrence chacune dans ce fichier) :

```tsx
        <p role="alert" className="text-xs text-red-600">
```
→
```tsx
        <p role="alert" className="text-xs text-danger">
```

```tsx
            <p className="text-xs text-amber-600">
```
→
```tsx
            <p className="text-xs text-warn">
```

```tsx
            <p className="text-xs text-slate-500">
```
→
```tsx
            <p className="text-xs text-ink-3">
```

- [ ] **Step 5: Grep-check**

Run: `grep -n "slate\|red-[0-9]\|amber-[0-9]\|blue-700\|bg-white" src/map/FieldClassificationPicker.tsx`
Expected: no output

- [ ] **Step 6: Re-run the test file**

Run: `npx vitest run src/map/FieldClassificationPicker.test.tsx`
Expected: PASS, sans modification du fichier de test (le bouton reste accessible par le même `aria-label`/texte — `Button` du kit rend un `<button>` natif sous le capot, `getByRole("button", { name: ... })` continue de matcher)

- [ ] **Step 7: Commit**

```bash
git add src/map/FieldClassificationPicker.tsx
git commit -m "style(shell): tokenise FieldClassificationPicker.tsx et son bouton de recalcul (SP-34)"
```

---

## Task 3: `MapSymbologyEditor.tsx` Part A — les 5 boutons autonomes vers le kit `Button`

**Files:**
- Modify: `shell/src/map/MapSymbologyEditor.tsx`
- Test: `shell/src/map/MapSymbologyEditor.test.tsx`

**Interfaces:**
- Consomme : `Button` de `../ui/kit/Button` (nouveau import)
- Produit : aucun changement de signature — cette tâche ne touche à aucune fonction, seulement au JSX de 5 boutons

**Note de risque (cf. spec) :** ce fichier porte la plus haute densité d'invariants documentés du dépôt sur la carte (I2–I16, M2, M7). Chaque bloc ci-dessous est montré en entier (avant/après) précisément pour que rien d'autre que la balise et sa classe ne change — ne pas toucher aux commentaires adjacents, ils documentent des bugs déjà corrigés.

- [ ] **Step 1: Run the test file to confirm the green baseline**

Run: `npx vitest run src/map/MapSymbologyEditor.test.tsx`
Expected: PASS

- [ ] **Step 2: Add the Button import**

Après `import { LUCIDE_ICONS, type IconCategory } from "../builder/widgets/iconLibrary";`, ajouter :

```ts
import { Button } from "../ui/kit/Button";
```

- [ ] **Step 3: Convert "Recalculer la taille"**

Remplacer :

```tsx
          <button
            type="button"
            className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
            disabled={busy === "size"}
            onClick={() => void recomputeSize()}
          >
            {busy === "size" ? "Calcul…" : "Recalculer la taille"}
          </button>
```

par :

```tsx
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
```

- [ ] **Step 4: Convert "Ajouter un contour"**

Remplacer :

```tsx
      {!stroke && (
        <button
          type="button"
          className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs"
          onClick={() => setStroke({})}
        >
          Ajouter un contour
        </button>
      )}
```

par :

```tsx
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
```

- [ ] **Step 5: Convert "Ajouter des icônes"**

Remplacer :

```tsx
      {!icon && !iconDraft && (
        <button
          type="button"
          className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs"
          onClick={() => setIconDraft(true)}
        >
          Ajouter des icônes
        </button>
      )}
```

par :

```tsx
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
```

- [ ] **Step 6: Convert "Recalculer les valeurs" (icônes)**

Remplacer :

```tsx
          <button
            type="button"
            className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs disabled:opacity-50"
            disabled={iconBusy || !iconField}
            onClick={() => void recomputeIconDomain()}
          >
            {iconBusy ? "Calcul…" : "Recalculer les valeurs"}
          </button>
```

par :

```tsx
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
```

- [ ] **Step 7: Convert "Ajouter une étiquette"**

Remplacer :

```tsx
      {!value?.label && (
        <button
          type="button"
          className="self-start rounded-md border border-slate-300 px-2 py-1 text-xs"
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
        </button>
      )}
```

par :

```tsx
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
```

(`#1e293b`/`#ffffff` sont des valeurs de données — la couleur/halo par défaut de l'étiquette écrite dans la config — pas des classes CSS : ne pas les toucher.)

- [ ] **Step 8: Re-run the test file**

Run: `npx vitest run src/map/MapSymbologyEditor.test.tsx`
Expected: PASS sans modification du fichier de test (tous les boutons gardent leur texte accessible exact — `getByRole("button", { name: "Recalculer la taille" })` etc. continuent de matcher)

- [ ] **Step 9: Commit**

```bash
git add src/map/MapSymbologyEditor.tsx
git commit -m "style(shell): bascule les 5 actions autonomes de MapSymbologyEditor.tsx sur Button (SP-34)"
```

---

## Task 4: `MapSymbologyEditor.tsx` Part B — couleurs restantes

**Files:**
- Modify: `shell/src/map/MapSymbologyEditor.tsx`
- Test: `shell/src/map/MapSymbologyEditor.test.tsx`

**Interfaces:**
- Consomme : rien de nouveau (Task 3 déjà appliquée dans ce même fichier)
- Produit : rien de nouveau

**Dépend de Task 3** (les boutons convertis en `Button` ne portent plus `rounded-md border border-slate-300 ...` — cette tâche traite uniquement ce qu'il reste après cette conversion).

- [ ] **Step 1: Run the test file to confirm the baseline (post-Task-3)**

Run: `npx vitest run src/map/MapSymbologyEditor.test.tsx`
Expected: PASS

- [ ] **Step 2: Replace the 5 identical "Retirer …" links (replace_all)**

Chaîne exacte, 5 occurrences identiques (Retirer la couleur/taille/contour/icônes/étiquette) :

Remplacer (replace_all) :
```
className="self-start text-xs text-red-700 underline"
```
par :
```
className="self-start text-xs text-danger underline"
```

- [ ] **Step 3: Replace the 2 identical "computed at" hints (replace_all)**

Remplacer (replace_all) :
```
className="text-xs text-slate-500"
```
par :
```
className="text-xs text-ink-3"
```

- [ ] **Step 4: Replace the 3 identical stroke/icon/label section containers (replace_all)**

Remplacer (replace_all) :
```
className="flex flex-col gap-2 border-l-2 border-slate-200 pl-2"
```
par :
```
className="flex flex-col gap-2 border-l-2 border-rule-2 pl-2"
```

- [ ] **Step 5: Replace the 2 identical icon-grid swatch buttons (replace_all)**

Remplacer (replace_all) :
```
className="h-6 w-6 rounded border border-slate-200"
```
par :
```
className="h-6 w-6 rounded border border-rule-2"
```

- [ ] **Step 6: Replace the 2 identical category headers (replace_all)**

Remplacer (replace_all) :
```
className="text-[10px] uppercase text-slate-500"
```
par :
```
className="text-[10px] uppercase text-ink-3"
```

- [ ] **Step 7: sizeError alert (unique)**

Remplacer :
```tsx
            <p role="alert" className="text-xs text-red-600">
```
par :
```tsx
            <p role="alert" className="text-xs text-danger">
```

- [ ] **Step 8: size "not computed" warning (unique)**

Remplacer :
```tsx
            <p className="text-xs text-amber-600">
              Taille non calculée — cliquez sur « Recalculer la taille ».
            </p>
```
par :
```tsx
            <p className="text-xs text-warn">
              Taille non calculée — cliquez sur « Recalculer la taille ».
            </p>
```

- [ ] **Step 9: stroke color mode toggle — "fixed" button (unique)**

Remplacer :
```tsx
            <button
              type="button"
              className={`rounded-md border border-slate-300 px-2 py-1 text-xs ${
                strokeColorIsFixed ? "bg-slate-200" : ""
              }`}
```
par :
```tsx
            <button
              type="button"
              className={`rounded-md border border-rule px-2 py-1 text-xs ${
                strokeColorIsFixed ? "bg-sunken" : ""
              }`}
```

- [ ] **Step 10: stroke color mode toggle — "attribute" button (unique)**

Remplacer :
```tsx
            <button
              type="button"
              className={`rounded-md border border-slate-300 px-2 py-1 text-xs ${
                !strokeColorIsFixed ? "bg-slate-200" : ""
              }`}
```
par :
```tsx
            <button
              type="button"
              className={`rounded-md border border-rule px-2 py-1 text-xs ${
                !strokeColorIsFixed ? "bg-sunken" : ""
              }`}
```

- [ ] **Step 11: "Choisir l'icône de …" per-value button (unique, reste natif — dense)**

Remplacer :
```tsx
                  className="rounded-md border border-slate-300 px-2 py-1 text-xs"
```
par :
```tsx
                  className="rounded-md border border-rule px-2 py-1 text-xs"
```

- [ ] **Step 12: iconError (unique, sans "self-start"/"underline")**

Remplacer :
```tsx
          {iconError && <p className="text-xs text-red-700">{iconError}</p>}
```
par :
```tsx
          {iconError && <p className="text-xs text-danger">{iconError}</p>}
```

- [ ] **Step 13: "Supprimer l'icône …" (unique)**

Remplacer :
```tsx
                            className="text-[10px] text-red-700 underline"
```
par :
```tsx
                            className="text-[10px] text-danger underline"
```

- [ ] **Step 14: Grep-check the whole file**

Run: `grep -n "slate\|red-[0-9]\|amber-[0-9]\|blue-700\|bg-white" src/map/MapSymbologyEditor.tsx`
Expected: no output

- [ ] **Step 15: Re-run the test file**

Run: `npx vitest run src/map/MapSymbologyEditor.test.tsx`
Expected: PASS, sans modification du fichier de test

- [ ] **Step 16: Commit**

```bash
git add src/map/MapSymbologyEditor.tsx
git commit -m "style(shell): tokenise les couleurs restantes de MapSymbologyEditor.tsx (SP-34)"
```

---

## Task 5: `PopupEditor.tsx` — styles partagés + tokens + Button

**Files:**
- Modify: `shell/src/map/PopupEditor.tsx`
- Test: `shell/src/map/PopupEditor.test.tsx`

**Interfaces:**
- Consomme : `Button` de `../ui/kit/Button` (nouveau import), `labelCls`/`inputCls` de `./formFieldStyles` (nouveau import, remplace la copie locale)
- Produit : aucun changement de signature (`PopupEditorProps` inchangée)

**Décision de la spec appliquée ici** : la ligne de champ répétée (`Libellé de {f}`, une fois par champ disponible) reste `h-8` — elle ne doit PAS hériter du nouveau `inputCls` partagé (désormais `h-9`). Un style dense local dédié la couvre.

- [ ] **Step 1: Run the test file to confirm the green baseline**

Run: `npx vitest run src/map/PopupEditor.test.tsx`
Expected: PASS

- [ ] **Step 2: Replace the local style constants with the shared import + a dense-row variant**

Remplacer :

```tsx
import { useId, useState } from "react";
import type { PopupConfig, PopupField } from "../api/types";
import { validateExpression } from "../builder/expr";
import { closingBrace } from "./popupTemplate";

const labelCls = "flex flex-col gap-1";
const inputCls = "h-8 rounded-md border border-slate-300 px-2 text-sm";
```

par :

```tsx
import { useId, useState } from "react";
import type { PopupConfig, PopupField } from "../api/types";
import { validateExpression } from "../builder/expr";
import { closingBrace } from "./popupTemplate";
import { Button } from "../ui/kit/Button";
import { labelCls, inputCls } from "./formFieldStyles";

// Contrôle répété une fois par champ disponible dans une liste dense
// (`PopupEditor` ci-dessous) : reste en h-8 par exception, comme les
// contrôles denses équivalents de QueryFilterBuilder.tsx/
// CrossFilterLinkEditor.tsx (convention tranchée le 2026-09-01, CLAUDE.md).
const denseInputCls = "h-8 rounded-md border border-rule px-2 text-sm";
```

- [ ] **Step 3: Use `denseInputCls` on the two per-field "Libellé de …" inputs**

Ces deux blocs sont quasi identiques (l'un pour les champs connus du schéma, l'autre pour les champs orphelins déjà sélectionnés) — les traiter un par un, chacun unique dans le fichier par son `aria-label` englobant.

Premier bloc — remplacer :

```tsx
                  {entry && (
                    <input
                      aria-label={`Libellé de ${f}`}
                      className={`${inputCls} w-28`}
                      value={entry.label ?? ""}
```

par :

```tsx
                  {entry && (
                    <input
                      aria-label={`Libellé de ${f}`}
                      className={`${denseInputCls} w-28`}
                      value={entry.label ?? ""}
```

Second bloc — remplacer :

```tsx
                  <input
                    aria-label={`Libellé de ${f.name}`}
                    className={`${inputCls} w-28`}
                    value={f.label ?? ""}
```

par :

```tsx
                  <input
                    aria-label={`Libellé de ${f.name}`}
                    className={`${denseInputCls} w-28`}
                    value={f.label ?? ""}
```

- [ ] **Step 4: Tokenize the "Sans sélection…" hint and the Markdown hint (replace_all — identical className)**

Remplacer (replace_all) :
```
className="text-xs text-slate-500"
```
par :
```
className="text-xs text-ink-3"
```

(Cette classe apparaît deux fois dans ce fichier : sur le `<p>` "Sans sélection, tous les champs sont affichés." et sur le `<span>` d'aide au gabarit Markdown — les deux passent à `text-ink-3` identiquement, aucune distinction de sens entre les deux.)

- [ ] **Step 5: Convert "Ajouter le champ" to the kit Button**

Remplacer :

```tsx
            <button
              type="button"
              className="rounded-md border border-slate-300 px-2 py-1 text-xs"
              onClick={addDraftField}
            >
              Ajouter le champ
            </button>
```

par :

```tsx
            <Button type="button" size="sm" variant="outline" onClick={addDraftField}>
              Ajouter le champ
            </Button>
```

- [ ] **Step 6: Tokenize the "Avancé (gabarit)" / "Liste de champs" toggle link**

Remplacer :

```tsx
          className="self-start text-xs text-blue-700 underline"
```

par :

```tsx
          className="self-start text-xs text-accent underline"
```

- [ ] **Step 7: Tokenize the template textarea border**

Remplacer :

```tsx
            className="min-h-24 rounded-md border border-slate-300 p-2 font-mono text-xs"
```

par :

```tsx
            className="min-h-24 rounded-md border border-rule p-2 font-mono text-xs"
```

- [ ] **Step 8: Tokenize the template error alert**

Remplacer :

```tsx
        <p role="alert" className="text-xs text-red-600">
```

par :

```tsx
        <p role="alert" className="text-xs text-danger">
```

- [ ] **Step 9: Grep-check**

Run: `grep -n "slate\|red-[0-9]\|amber-[0-9]\|blue-700\|bg-white" src/map/PopupEditor.tsx`
Expected: no output

- [ ] **Step 10: Re-run the test file**

Run: `npx vitest run src/map/PopupEditor.test.tsx`
Expected: PASS, sans modification du fichier de test

- [ ] **Step 11: Commit**

```bash
git add src/map/PopupEditor.tsx
git commit -m "style(shell): PopupEditor.tsx importe formFieldStyles.ts et tokenise ses couleurs (SP-34)"
```

---

## Task 6: `LayersPanel.tsx` — séparateur `border-t`

**Files:**
- Modify: `shell/src/map/LayersPanel.tsx`
- Test: `shell/src/map/LayersPanel.test.tsx`

**Interfaces:**
- Consomme : rien de nouveau
- Produit : rien de nouveau

Rappel spec : les 4 boutons ↑/↓/👁/✕ par couche restent natifs (répétés par ligne, cas dense explicitement exempté) — cette tâche ne touche qu'au séparateur non tokenisé déjà noté par le suivi SP-30c.

- [ ] **Step 1: Run the test file to confirm the green baseline**

Run: `npx vitest run src/map/LayersPanel.test.tsx`
Expected: PASS

- [ ] **Step 2: Tokenize the separator**

Remplacer :

```tsx
      <div className="border-t pt-2">
```

par :

```tsx
      <div className="border-t border-rule pt-2">
```

- [ ] **Step 3: Grep-check**

Run: `grep -n "slate\|red-[0-9]\|amber-[0-9]\|blue-700\|bg-white" src/map/LayersPanel.tsx`
Expected: no output (ce fichier n'avait de toute façon aucune de ces couleurs — seul le `border-t` sans couleur explicite était noté)

- [ ] **Step 4: Re-run the test file**

Run: `npx vitest run src/map/LayersPanel.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/map/LayersPanel.tsx
git commit -m "style(shell): tokenise le séparateur border-t de LayersPanel.tsx (SP-34)"
```

---

## Task 7: `MapMeasureSketchToolbar.tsx` — tokens

**Files:**
- Modify: `shell/src/map/MapMeasureSketchToolbar.tsx`
- Test: `shell/src/map/MapMeasureSketchToolbar.test.tsx`

**Interfaces:**
- Consomme : rien de nouveau (aucun bouton converti — barre d'outils compacte à état `aria-pressed`, exemptée par la spec)
- Produit : rien de nouveau

- [ ] **Step 1: Run the test file to confirm the green baseline**

Run: `npx vitest run src/map/MapMeasureSketchToolbar.test.tsx`
Expected: PASS

- [ ] **Step 2: Tokenize the shared button class constant**

Remplacer :

```tsx
  const buttonCls = "rounded border border-slate-300 px-2 py-1";
```

par :

```tsx
  const buttonCls = "rounded border border-rule px-2 py-1";
```

- [ ] **Step 3: Tokenize the floating panel background**

Remplacer :

```tsx
    <div className="absolute left-2 top-2 z-10 flex flex-col gap-1 rounded-md bg-white/90 p-2 text-xs shadow">
```

par :

```tsx
    <div className="absolute left-2 top-2 z-10 flex flex-col gap-1 rounded-md bg-surface/90 p-2 text-xs shadow">
```

- [ ] **Step 4: Tokenize the "click second point" hint**

Remplacer :

```tsx
      {pendingCorner && <p className="text-slate-500">Cliquez le second point…</p>}
```

par :

```tsx
      {pendingCorner && <p className="text-ink-3">Cliquez le second point…</p>}
```

- [ ] **Step 5: Grep-check**

Run: `grep -n "slate\|red-[0-9]\|amber-[0-9]\|blue-700\|bg-white" src/map/MapMeasureSketchToolbar.tsx`
Expected: no output

- [ ] **Step 6: Re-run the test file**

Run: `npx vitest run src/map/MapMeasureSketchToolbar.test.tsx`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/map/MapMeasureSketchToolbar.tsx
git commit -m "style(shell): tokenise MapMeasureSketchToolbar.tsx (SP-34)"
```

---

## Task 8: `MapPopup.tsx` — tokens

**Files:**
- Modify: `shell/src/map/MapPopup.tsx`
- Test: `shell/src/map/MapPopup.test.tsx`

**Interfaces:**
- Consomme : rien de nouveau
- Produit : rien de nouveau

- [ ] **Step 1: Run the test file to confirm the green baseline**

Run: `npx vitest run src/map/MapPopup.test.tsx`
Expected: PASS

- [ ] **Step 2: Tokenize the popup background**

Remplacer :

```tsx
      className="absolute z-20 max-h-64 max-w-xs -translate-x-1/2 -translate-y-full overflow-auto rounded-md bg-white p-2 text-xs shadow-lg"
```

par :

```tsx
      className="absolute z-20 max-h-64 max-w-xs -translate-x-1/2 -translate-y-full overflow-auto rounded-md bg-surface p-2 text-xs shadow-lg"
```

- [ ] **Step 3: Tokenize the close button**

Remplacer :

```tsx
        className="absolute right-1 top-1 px-1 text-slate-400"
```

par :

```tsx
        className="absolute right-1 top-1 px-1 text-ink-3"
```

- [ ] **Step 4: Tokenize the attribute label (`<dt>`)**

Remplacer :

```tsx
              <dt className="text-slate-500">{r.label}</dt>
```

par :

```tsx
              <dt className="text-ink-3">{r.label}</dt>
```

- [ ] **Step 5: Tokenize the "Aucun attribut" placeholder**

Remplacer :

```tsx
      {empty && <p className="text-slate-400">Aucun attribut</p>}
```

par :

```tsx
      {empty && <p className="text-ink-3">Aucun attribut</p>}
```

- [ ] **Step 6: Grep-check**

Run: `grep -n "slate\|red-[0-9]\|amber-[0-9]\|blue-700\|bg-white" src/map/MapPopup.tsx`
Expected: no output

- [ ] **Step 7: Re-run the test file**

Run: `npx vitest run src/map/MapPopup.test.tsx`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/map/MapPopup.tsx
git commit -m "style(shell): tokenise MapPopup.tsx (SP-34)"
```

---

## Task 9: `MapLegend.tsx` — tokens

**Files:**
- Modify: `shell/src/map/MapLegend.tsx`
- Test: `shell/src/map/MapLegend.test.tsx`

**Interfaces:**
- Consomme : rien de nouveau
- Produit : rien de nouveau

- [ ] **Step 1: Run the test file to confirm the green baseline**

Run: `npx vitest run src/map/MapLegend.test.tsx`
Expected: PASS

- [ ] **Step 2: Tokenize the legend background**

Remplacer :

```tsx
    <ul className="absolute bottom-2 left-2 z-10 rounded-md bg-white/90 p-2 text-xs shadow">
```

par :

```tsx
    <ul className="absolute bottom-2 left-2 z-10 rounded-md bg-surface/90 p-2 text-xs shadow">
```

- [ ] **Step 3: Grep-check**

Run: `grep -n "slate\|red-[0-9]\|amber-[0-9]\|blue-700\|bg-white" src/map/MapLegend.tsx`
Expected: no output

- [ ] **Step 4: Re-run the test file**

Run: `npx vitest run src/map/MapLegend.test.tsx`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/map/MapLegend.tsx
git commit -m "style(shell): tokenise MapLegend.tsx (SP-34)"
```

---

## Task 10: Vérification finale + clôture

**Files:**
- Read-only sur les 8 fichiers ci-dessus
- Modify: `CLAUDE.md` (entrée `### Livré`)

**Interfaces:** aucune (tâche de vérification et de documentation)

- [ ] **Step 1: Grep sweep on all 8 files at once, including the `text-white`/`text-black` blind spot noted by SP-30f**

Run:
```bash
cd /home/lenen/projets/geostudio/shell
grep -rn "slate\|red-[0-9]\|amber-[0-9]\|blue-700\|bg-white\|text-white\b\|text-black\b" \
  src/map/formFieldStyles.ts src/map/FieldClassificationPicker.tsx src/map/MapSymbologyEditor.tsx \
  src/map/PopupEditor.tsx src/map/LayersPanel.tsx src/map/MapMeasureSketchToolbar.tsx \
  src/map/MapPopup.tsx src/map/MapLegend.tsx
```
Expected: no output (empty)

- [ ] **Step 2: Full Vitest suite**

Run: `npm run test`
Expected: PASS, 0 failed (référence avant ce plan : 223 fichiers/1848 tests, cf. CLAUDE.md SP-33 — le compte de tests ne doit pas baisser, aucun test n'a été supprimé par ce plan)

- [ ] **Step 3: TypeScript check**

Run: `npm run build`
Expected: PASS (tsc --noEmit propre + build Vite réussi)

- [ ] **Step 4: Full E2E suite**

Run: `npm run e2e`
Expected: le même total que la référence pré-plan (138 passed/5 skipped/0 failed selon la dernière clôture SP-33) — aucune régression, aucun nouveau spec attendu par ce plan (pure passe visuelle, aucun sélecteur changé)

- [ ] **Step 5: Manual visual check (dev server, both ambiances)**

Run: `npm run dev` (ou la stack complète via `docker compose up -d` si un backend réel est nécessaire pour peupler des couches)

Ouvrir l'éditeur de carte, onglet Inspecter → sélectionner une couche `vector`/`feature` → vérifier visuellement, dans les DEUX ambiances (basculer `prefers-color-scheme` via les DevTools du navigateur, Rendering → Emulate CSS media feature) :
- l'éditeur de symbologie complet (couleur classée + contour + icônes + étiquette) reste lisible et cohérent en clair et en sombre ;
- l'éditeur de popup (liste de champs + gabarit avancé) idem ;
- sur la carte elle-même : la légende (bas-gauche), la barre de mesure/croquis (haut-gauche), et une popup au clic sur une entité — les trois superpositions doivent suivre l'ambiance sans devenir illisibles sur aucun fond de carte testé.

Documenter le résultat de ce contrôle manuel dans le rapport de tâche (aucun test automatisé ne le couvre, cf. spec).

- [ ] **Step 6: Update CLAUDE.md — `### Livré` entry**

Ajouter une entrée `**SP-34**` dans la section `### Livré` de `/home/lenen/projets/geostudio/CLAUDE.md`, juste après l'entrée SP-33 existante, dans le même style que les entrées voisines (résumé du périmètre exact touché, décisions prises en brainstorming — inclusion des 3 superpositions carte tokénisées complètement, exclusions de `LayerPicker.tsx`/`Select`/`Combobox`/`Segmented` —, résultat des suites de tests, tout défaut trouvé en vérification finale). Retirer la ligne correspondante de la section `### À venir` / « Dette de tokens `LayersPanel`/`MapSymbologyEditor.tsx` et voisins » si elle y est encore listée comme suivi ouvert.

- [ ] **Step 7: Commit the CLAUDE.md update**

```bash
cd /home/lenen/projets/geostudio
git add CLAUDE.md
git commit -m "docs: clôt SP-34 — dette de tokens LayersPanel/MapSymbologyEditor dans CLAUDE.md"
```

---

## Self-Review (fait par l'auteur du plan avant transmission)

**Couverture de la spec** : les 8 fichiers du périmètre sont chacun couverts par au moins une tâche (Task 1↔formFieldStyles.ts, Task 2↔FieldClassificationPicker.tsx, Task 3+4↔MapSymbologyEditor.tsx, Task 5↔PopupEditor.tsx, Task 6↔LayersPanel.tsx, Task 7↔MapMeasureSketchToolbar.tsx, Task 8↔MapPopup.tsx, Task 9↔MapLegend.tsx). Le nombre total d'occurrences de couleur brute traitées (1+4+28+7+0+3+4+1 = 48) correspond exactement au grep de périmètre effectué pendant le brainstorming. Les exclusions de la spec (LayerPicker.tsx, Select/Combobox, Segmented, comportement) sont répétées dans les Global Constraints et jamais contredites par une étape. La vérification finale (Task 10) couvre les 4 points listés par la section « Vérification & garde-fous » de la spec (grep, Vitest complet, E2E complet, contrôle visuel manuel) plus la mise à jour de `CLAUDE.md` requise par son propre paragraphe « Comment on travaille ».

**Pas de placeholder** : chaque step montre le texte avant/après complet, aucun « TODO »/« similaire à la tâche N ».

**Cohérence des types/noms** : `Button`/`size="sm"`/`variant="outline"` utilisés identiquement dans les Tasks 2/3/5, sur le même idiome que `CameraControls.tsx` existant. `denseInputCls` n'est introduit qu'en Task 5 et n'est consommé que par les deux blocs qu'elle cible dans le même fichier — pas de fuite vers un autre fichier.
