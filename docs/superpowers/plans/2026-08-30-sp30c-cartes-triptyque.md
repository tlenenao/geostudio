# SP-30c — Cartes sur le socle triptyque (MapEditorPage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Basculer la famille **Cartes** (`docs/superpowers/specs/2026-08-30-sp30-bascule-triptyque-design.md` §6.1, famille 3) sur `TriptychLayout` : `MapEditorPage`, avec les libellés d'onglet donnés par la spec elle-même (§2.1 point 4) — « Couches / Carte / Inspecter ». Élimine les deux derniers `ui/dialog.tsx` (modaux) de cette famille : `ExportPanel` et `Terrain3DUploadButton` deviennent des panneaux en ligne, jamais des fenêtres flottantes.

**Périmètre explicitement hors de ce plan** (familles 4 à 8 du §6.1, à traiter dans des plans SP-30d+ séparés) : `DatasetEditPage` + `CollectionPermissions` shell-side (Données), `AppBuilderPage` (Apps & sites), `PipelineBuilderPage`/`ReportEditPage`/`VisualQueryWizardPage` (Automatisation), `SqlLabPage` (Analytique), `AdminExtensionsPage`/`CollectionsAdminPage`/`HarvestSourcesAdminPage` (Administration), `Tileset3DUploadButton`/`NewItemButton`/`ImportFileButton` (chrome, laissés « inchangés, relocalisés » par le plan SP-30a lui-même — leurs `Dialog` restent une dette documentée, pas un blocage pour cette famille).

Également hors de ce plan, en dette documentée (§8) : les éditeurs de symbologie/popup profondément imbriqués dans `LayersPanel` — `MapSymbologyEditor.tsx` (797 lignes, 27 couleurs Tailwind en dur), `PopupEditor.tsx`, `FieldClassificationPicker.tsx`, `MapMeasureSketchToolbar.tsx`, `MapPopup.tsx`, `MapLegend.tsx`, `formFieldStyles.ts`. Vérifié par grep (`grep -rl 'ui/dialog"'`) : **aucun** de ces sept fichiers n'importe `ui/dialog.tsx` — leur dette est purement cosmétique (couleurs Tailwind en dur), jamais une fenêtre modale qui violerait A7/A8. Les convertir en un seul plan aurait rendu SP-30c aussi gros que SP-30a+SP-30b réunis (spec §11 : « le plus gros bloc du chantier », découpage par famille non négociable) ; ils n'empêchent pas la bascule de `MapEditorPage` elle-même sur `TriptychLayout`.

**Architecture:** `MapEditorPage` s'enveloppe dans `<div className="-m-6 flex flex-1 flex-col overflow-hidden">` (même technique de transition locale que `CatalogPage`/`ItemDetailPage`, SP-30b) et instancie `TriptychLayout` avec trois volets : **browse** = « Couches » (`LayersPanel`, qui embarque déjà `LayerPicker` pour l'ajout — vérifié, aucun nouveau composant à créer) ; **work** = « Carte » (`MapView` seul, plein volet) ; **inspect** = « Inspecter » (fond de carte, terrain, caméra, mise en page d'impression, historique, export, bouton Enregistrer — tout ce qui n'est ni la liste des couches ni le canevas). La branche `isExportRender` (rendu nu pour le worker Playwright, SP-17a) reste un retour anticipé **avant** `TriptychLayout`, totalement inchangée — elle ne doit jamais porter de chrome triptyque. `ExportPanel` et `Terrain3DUploadButton` perdent leur `<Dialog>` : chacun devient un bouton qui bascule un `<Panel>` en ligne (même idiome que le menu déroulant maison d'`ItemActions`, SP-30a Task 5 — « pas le `Dialog` du kit, un composant en ligne dédié »), avec un bouton Annuler explicite puisqu'il n'y a plus d'Escape/backdrop à intercepter.

**Tech Stack:** React 19, `@tanstack/react-query`, kit de primitives SP-29b (`shell/src/ui/kit/`), Vitest + Testing Library, Playwright.

## Global Constraints

- Docs et identifiants de test en français ; code/identifiants en anglais (CLAUDE.md).
- Aucune couleur Tailwind en dur (`slate-*`, `red-*`, `blue-*`, `amber-*`, `white`, `black`) dans les fichiers touchés par ce plan : tokens uniquement (`bg-surface`, `text-ink`, `text-ink-2`, `text-ink-3`, `border-rule`, `bg-raised`, `bg-sunken`, `text-danger`, `text-accent`, `text-warn` — `shell/src/styles/tokens.css`, confirmés définis dans le bloc `@theme inline`). **Exception assumée** : les trois `bg-white/90` de la branche `isExportRender` de `MapEditorPage.tsx` restent en dur — c'est un habillage de capture d'impression (papier), pas du chrome d'interface, au même titre que la carte qui reste toujours claire en ambiance sombre (spec §2.2) ; ne pas y toucher.
- Aucun `<Dialog>` (ancien `ui/dialog.tsx` ou `ui/kit/Dialog`) ne doit apparaître dans les fichiers touchés par ce plan à l'issue des Tasks 4/5 — seul `ui/kit/ConfirmDialog` (confirmation destructive) a le droit de survivre dans tout le dépôt (spec §2.1). Chaque conversion de Dialog ajoute un test qui vérifie `screen.queryByRole("dialog")` est `null` après ouverture du panneau — un filet falsifiable, pas une simple relecture visuelle (piège n°10 : vérifier qu'un filet de test détecte bien la régression qu'il prétend couvrir).
- `-m-6` est une technique de transition **locale à `MapEditorPage.tsx` seul** dans ce plan, jamais un changement à `AppLayout.tsx` (même règle que SP-30b Global Constraints) — les pages encore sur l'ancien layout (SP-30d+) dépendent du `p-6` d'`AppLayout`.
- Régressions jsdom (piège n°10) : `window.matchMedia` n'existe pas sous jsdom — stub local à `MapEditorPage.test.tsx` (copier le patron exact de `CatalogPage.test.tsx`/`ItemDetailPage.test.tsx`, `matches: false` par défaut), jamais dans `shell/src/test/setup.ts`.
- `ExportPanel` (`builder/print/ExportPanel.tsx`) est aussi consommé par `AppRuntimePage.tsx` (public, hors périmètre de toute la bascule SP-30 — spec §2.2). C'est un composant-feuille à API inchangée (`{ itemId: string }`) : sa conversion Dialog→panneau en ligne s'y propage automatiquement, un effet de bord non-cassant assumé (même logique que le kit-ification des feuilles partagées en SP-30b Task 1). Vérifier que `AppRuntimePage.test.tsx` passe toujours sans modification (Task 4).
- `ConfigHistoryPanel` (`builder/ConfigHistoryPanel.tsx`) est partagé par **cinq** éditeurs (`MapEditorPage`, `DatasetEditPage`, `AppBuilderPage`, `PipelineBuilderPage`, `ReportEditPage`) — Task 1 n'y touche que l'import `Button` et deux couleurs, API et comportement strictement inchangés. Vérifier que les quatre autres pages non concernées par SP-30c passent toujours leurs tests sans modification.
- Pas de changement au cœur (`core/`) dans ce plan : aucune régénération OpenAPI/TS attendue, diff vide légitime (piège n°1 — vide parce qu'aucun schéma ne change, pas parce qu'une surface est derrière un flag).
- E2E : `shell/e2e/map-editor.spec.ts` (2 tests) est le filet de non-régression comportementale directe de cette famille ; `map-symbology.spec.ts`, `map-symbology-advanced.spec.ts`, `map-popup.spec.ts`, `map-measure-sketch.spec.ts`, `map-feature-layer-symbology.spec.ts` rendent tous `MapEditorPage` en amont et doivent rester verts sans modification de leur texte (Task 6).

---

## Task 1: Shell — kit-ifier `CameraControls`, `ConfigHistoryPanel` (Button seul)

**Files:**
- Modify: `shell/src/map/CameraControls.tsx`
- Modify: `shell/src/builder/ConfigHistoryPanel.tsx`
- Test: `shell/src/map/CameraControls.test.tsx` (baseline, doit passer sans modification)
- Test: `shell/src/builder/ConfigHistoryPanel.test.tsx` (baseline, doit passer sans modification)

**Interfaces:**
- Consumes: `Button` de `shell/src/ui/kit/Button.tsx` (`variant: "default"|"outline"|"ghost"|"danger"`, `size: "default"|"sm"|"icon"` — signature lue, compatible sans changement avec les usages `variant="outline" size="sm"` des deux fichiers).
- Produces: aucune API publique changée — feuilles pures, consommées telles quelles par Task 6.

Ces deux fichiers n'utilisent l'ancien `ui/button.tsx` que pour un seul bouton chacun, sans `Dialog`/`Input`/`card` — le risque le plus bas du plan, à traiter en premier.

- [ ] **Step 1: Baseline — lancer les tests existants**

```bash
cd shell && npx vitest run src/map/CameraControls.test.tsx src/builder/ConfigHistoryPanel.test.tsx
```

Expected: PASS (les deux fichiers, avant toute modification).

- [ ] **Step 2: `CameraControls.tsx` — import + token**

Remplacer la ligne d'import :
```tsx
import { Button } from "../ui/button";
```
par :
```tsx
import { Button } from "../ui/kit/Button";
```

Remplacer :
```tsx
<p className="mb-1 mt-3 text-xs font-medium text-slate-500">Caméra</p>
```
par :
```tsx
<p className="mb-1 mt-3 text-xs font-medium text-ink-2">Caméra</p>
```

- [ ] **Step 3: `ConfigHistoryPanel.tsx` — import + tokens**

Remplacer la ligne d'import :
```tsx
import { Button } from "../ui/button";
```
par :
```tsx
import { Button } from "../ui/kit/Button";
```

Remplacer les deux blocs d'erreur :
```tsx
      {loadError && (
        <p role="alert" className="text-sm text-red-600">
          Impossible de charger l'historique des versions.
        </p>
      )}
      {restoreError && (
        <p role="alert" className="text-sm text-red-600">
          Impossible de restaurer cette version.
        </p>
      )}
```
par :
```tsx
      {loadError && (
        <p role="alert" className="text-sm text-danger">
          Impossible de charger l'historique des versions.
        </p>
      )}
      {restoreError && (
        <p role="alert" className="text-sm text-danger">
          Impossible de restaurer cette version.
        </p>
      )}
```

Remplacer les deux occurrences de `text-slate-500` :
```tsx
        <p className="text-sm text-slate-500">Aucune version enregistrée.</p>
```
→
```tsx
        <p className="text-sm text-ink-2">Aucune version enregistrée.</p>
```
et :
```tsx
              <span className="text-xs text-slate-500">(courante)</span>
```
→
```tsx
              <span className="text-xs text-ink-2">(courante)</span>
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/map/CameraControls.test.tsx src/builder/ConfigHistoryPanel.test.tsx
```

Expected: PASS, sans aucune modification aux deux fichiers de test (aucun test n'affirme sur la classe CSS ou l'import).

- [ ] **Step 5: Vérifier que les quatre autres pages consommant `ConfigHistoryPanel` passent toujours**

```bash
cd shell && npx vitest run src/pages/DatasetEditPage.test.tsx src/pages/AppBuilderPage.test.tsx src/pages/PipelineBuilderPage.test.tsx src/pages/ReportEditPage.test.tsx
```

Expected: PASS (aucune de ces quatre pages n'est modifiée par ce plan — ce test confirme que le changement de `ConfigHistoryPanel` est bien non-cassant pour elles).

- [ ] **Step 6: Commit**

```bash
git add shell/src/map/CameraControls.tsx shell/src/builder/ConfigHistoryPanel.tsx
git commit -m "feat(shell): cameraControls/configHistoryPanel — kit Button + tokens"
```

---

## Task 2: Shell — kit-ifier `LayerPicker` (Button + tokens, pas de Dialog)

**Files:**
- Modify: `shell/src/map/LayerPicker.tsx`
- Test: `shell/src/map/LayerPicker.test.tsx` (baseline, doit passer sans modification)

**Interfaces:**
- Consumes: `Button` de `shell/src/ui/kit/Button.tsx`.
- Produces: aucune API publique changée (`LayerPicker({ onAdd })`) — consommé tel quel par `LayersPanel` (déjà le cas aujourd'hui, aucun changement à `LayersPanel.tsx` requis pour cette relation).

`LayerPicker` n'importe pas `ui/dialog.tsx` — c'est un panneau en ligne depuis toujours (recherche de source + formulaires d'ajout par URL), seuls l'import `Button` et 13 couleurs Tailwind en dur (confirmé par grep) doivent changer.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/map/LayerPicker.test.tsx
```

Expected: PASS.

- [ ] **Step 2: Réécrire les imports et les couleurs**

Remplacer la ligne d'import :
```tsx
import { Button } from "../ui/button";
```
par :
```tsx
import { Button } from "../ui/kit/Button";
```

Remplacer chaque occurrence, une par une, dans le fichier :

```tsx
        className="h-8 rounded-md border border-slate-300 px-2 text-sm"
```
(les quatre occurrences — champ de recherche, titre tileset3d, URL tileset3d, titre GeoJSON, URL GeoJSON — soit 5 occurrences réelles, à vérifier par `grep -n 'border-slate-300' src/map/LayerPicker.tsx` avant d'éditer, ne pas deviner le nombre) par :
```tsx
        className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
```

```tsx
      {isLoading && <p className="text-sm text-slate-500">Chargement des sources…</p>}
```
→
```tsx
      {isLoading && <p className="text-sm text-ink-2">Chargement des sources…</p>}
```

```tsx
        <div className="text-sm text-red-600">
```
→
```tsx
        <div className="text-sm text-danger">
```

```tsx
      {!isLoading && !isError && (!data || data.length === 0) && (
        <p className="text-sm text-slate-500">Aucune source disponible.</p>
      )}
```
→
```tsx
      {!isLoading && !isError && (!data || data.length === 0) && (
        <p className="text-sm text-ink-2">Aucune source disponible.</p>
      )}
```

```tsx
                className="w-full rounded-md px-2 py-1 text-left text-sm hover:bg-slate-100"
```
→
```tsx
                className="w-full rounded-md px-2 py-1 text-left text-sm text-ink hover:bg-sunken"
```

```tsx
                <span className="ml-2 text-xs text-slate-400">{source.kind}</span>
                {typeof source.featureCount === "number" && (
                  <span className="ml-2 text-xs text-slate-400">{source.featureCount} entités</span>
                )}
```
→
```tsx
                <span className="ml-2 text-xs text-ink-3">{source.kind}</span>
                {typeof source.featureCount === "number" && (
                  <span className="ml-2 text-xs text-ink-3">{source.featureCount} entités</span>
                )}
```

```tsx
        <p className="mb-1 text-xs font-medium text-slate-500">Ajouter un tileset 3D par URL</p>
```
→
```tsx
        <p className="mb-1 text-xs font-medium text-ink-2">Ajouter un tileset 3D par URL</p>
```

```tsx
        <p className="mb-1 text-xs font-medium text-slate-500">
          Ajouter une couche par URL GeoJSON
        </p>
```
→
```tsx
        <p className="mb-1 text-xs font-medium text-ink-2">
          Ajouter une couche par URL GeoJSON
        </p>
```

```tsx
            <p role="alert" className="text-xs text-amber-600">
```
→
```tsx
            <p role="alert" className="text-xs text-warn">
```

Après ces remplacements, vérifier qu'aucune couleur Tailwind en dur ne subsiste :
```bash
grep -nE 'text-(red|slate|blue|gray|black|amber)-[0-9]+|bg-(white|black|slate|gray)|border-(slate|gray)-[0-9]+' shell/src/map/LayerPicker.tsx
```
Expected: aucune sortie.

- [ ] **Step 3: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/map/LayerPicker.test.tsx
```

Expected: PASS, sans modification au fichier de test (aucun test n'affirme sur une classe CSS).

- [ ] **Step 4: Commit**

```bash
git add shell/src/map/LayerPicker.tsx
git commit -m "feat(shell): layerPicker — kit Button + tokens"
```

---

## Task 3: Shell — tokens seuls (`BasemapSelect`, `TerrainPanel`, `PrintLayoutPanel`, `LayersPanel`)

**Files:**
- Modify: `shell/src/map/BasemapSelect.tsx`
- Modify: `shell/src/map/TerrainPanel.tsx`
- Modify: `shell/src/builder/print/PrintLayoutPanel.tsx`
- Modify: `shell/src/map/LayersPanel.tsx`
- Test: les quatre fichiers `.test.tsx` correspondants (baseline, doivent passer sans modification)

**Interfaces:**
- Produces: aucune API publique changée sur les quatre fichiers — cosmétique uniquement.

Ces quatre fichiers n'importent aucun ancien primitif (`ui/button`, `ui/dialog`, `ui/input`, `ui/card`) — seules des couleurs Tailwind en dur (1 à 3 occurrences chacun) doivent devenir des tokens.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/map/BasemapSelect.test.tsx src/map/TerrainPanel.test.tsx src/builder/print/PrintLayoutPanel.test.tsx src/map/LayersPanel.test.tsx
```

Expected: PASS (ajuster les noms de fichiers si l'un d'eux n'existe pas encore — vérifier par `ls shell/src/map/*.test.tsx shell/src/builder/print/*.test.tsx` avant de lancer ; s'il manque un test pour l'un de ces quatre composants, ce step se contente de le noter, aucun nouveau test n'est requis par cette tâche purement cosmétique).

- [ ] **Step 2: `BasemapSelect.tsx`**

Remplacer :
```tsx
        className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
```
par :
```tsx
        className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
```

- [ ] **Step 3: `TerrainPanel.tsx`**

Remplacer :
```tsx
      <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Terrain 3D</p>
```
par :
```tsx
      <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Terrain 3D</p>
```

- [ ] **Step 4: `PrintLayoutPanel.tsx`**

Remplacer :
```tsx
      <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Mise en page d&apos;impression</p>
```
par :
```tsx
      <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Mise en page d&apos;impression</p>
```

- [ ] **Step 5: `LayersPanel.tsx`**

Trouver les trois occurrences précises avant d'éditer (le texte exact autour peut différer légèrement de la lecture initiale) :
```bash
grep -n 'text-red-600\|text-slate-400\|text-slate-500' shell/src/map/LayersPanel.tsx
```

Remplacer `className="px-1 text-red-600"` par `className="px-1 text-danger"` ; `className="text-xs text-slate-400"` (« Aucune couche. ») par `className="text-xs text-ink-3"` ; `className="mb-1 text-xs font-medium text-slate-500"` (« Ajouter une couche ») par `className="mb-1 text-xs font-medium text-ink-2"`.

- [ ] **Step 6: Vérifier qu'aucune couleur en dur ne subsiste dans les quatre fichiers**

```bash
grep -nE 'text-(red|slate|blue|gray|black|amber)-[0-9]+|bg-(white|black|slate|gray)|border-(slate|gray)-[0-9]+' \
  shell/src/map/BasemapSelect.tsx shell/src/map/TerrainPanel.tsx \
  shell/src/builder/print/PrintLayoutPanel.tsx shell/src/map/LayersPanel.tsx
```

Expected: aucune sortie.

- [ ] **Step 7: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/map/BasemapSelect.test.tsx src/map/TerrainPanel.test.tsx src/builder/print/PrintLayoutPanel.test.tsx src/map/LayersPanel.test.tsx
```

Expected: PASS, sans modification aux fichiers de test.

- [ ] **Step 8: Commit**

```bash
git add shell/src/map/BasemapSelect.tsx shell/src/map/TerrainPanel.tsx shell/src/builder/print/PrintLayoutPanel.tsx shell/src/map/LayersPanel.tsx
git commit -m "style(shell): basemapSelect/terrainPanel/printLayoutPanel/layersPanel — tokens"
```

---

## Task 4: Shell — `ExportPanel` sans `Dialog` (panneau en ligne)

**Files:**
- Modify: `shell/src/builder/print/ExportPanel.tsx`
- Modify: `shell/src/builder/print/ExportPanel.test.tsx`

**Interfaces:**
- Consumes: `Button`/`Panel` de `shell/src/ui/kit/`.
- Produces: `ExportPanel({ itemId: string })` — API publique inchangée, consommé tel quel par `MapEditorPage` (Task 6) et `AppRuntimePage` (inchangé, hors périmètre — cf. Global Constraints).

Le sélecteur de format (PNG/PDF) devient un `<Panel>` affiché sous le bouton « Exporter » au lieu d'un `<Dialog>` flottant, avec un bouton Annuler explicite (le `Dialog` retiré gérait la fermeture par Escape/backdrop — un panneau en ligne n'a ni l'un ni l'autre).

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/builder/print/ExportPanel.test.tsx
```

Expected: PASS (5 tests + 1 dans la seconde `describe`, 6 au total).

- [ ] **Step 2: Écrire les deux nouveaux tests (Annuler, absence de `role=dialog`)**

Ajouter à `shell/src/builder/print/ExportPanel.test.tsx`, dans le `describe("ExportPanel", ...)` existant, après le dernier `it`:

```tsx
  it("annuler referme le sélecteur de format sans lancer d'export", async () => {
    const createExport = vi.fn();
    renderPanel({ createExport, getExportJob: vi.fn() });

    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    expect(screen.getByText("Choisir le format d'export")).toBeInTheDocument();

    await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
    expect(screen.queryByText("Choisir le format d'export")).not.toBeInTheDocument();
    expect(createExport).not.toHaveBeenCalled();
  });

  it("le sélecteur de format n'est jamais une fenêtre modale (pas de role=dialog)", async () => {
    renderPanel({ createExport: vi.fn(), getExportJob: vi.fn() });
    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    expect(screen.getByText("Choisir le format d'export")).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec**

```bash
cd shell && npx vitest run src/builder/print/ExportPanel.test.tsx -t "Annuler referme|jamais une fenêtre modale"
```

Expected: FAIL — le bouton « Annuler » n'existe pas encore dans le `Dialog` actuel.

- [ ] **Step 4: Réécrire `ExportPanel.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/hooks";
import type { ExportFormat, ExportJob } from "../../api/types";
import { Button } from "../../ui/kit/Button";
import { Panel } from "../../ui/kit/Panel";

const POLL_INTERVAL_MS = 1500;
// Fix round (finding I7) : ni PipelineRunPanel ni ImportFileButton (les deux
// autres implémentations de ce patron de poll) n'ont de plafond — mais un
// job d'export peut rester bloqué "running" pour de bon si export-worker
// (Chromium) crashe en cours de rendu (OOM notamment), et il n'existe encore
// aucun balayage de reclaim côté serveur pour ce cas précis (cf.
// app/export/repository.py::reclaim_stuck_jobs, TODO périodicité). Sans
// plafond ici, l'onglet du navigateur pollerait toutes les 1.5s pour
// toujours. 200 tentatives × 1.5s = 5 minutes, un budget large pour un rendu
// Playwright réel mais fini.
const MAX_POLL_ATTEMPTS = 200;

// Patron de poll identique à PipelineRunPanel (SP-15a) / ImportFileButton
// (SP-6a) : boucle récursive manuelle via le client, jamais un
// refetchInterval react-query (cf. plan Global Constraints). Garde de
// montage supplémentaire par rapport à ces deux précédents : ce panneau
// peut être démonté pendant qu'un poll est en vol (fermeture de page,
// navigation), donc chaque `setState` après un `await` est gardé par
// `mountedRef`, et le timer en attente est explicitement annulé au
// démontage pour ne rien laisser en suspens.
export function ExportPanel({ itemId }: { itemId: string }) {
  const client = useItemClient();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [job, setJob] = useState<ExportJob | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const mountedRef = useRef(true);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      mountedRef.current = false;
      if (timerRef.current) clearTimeout(timerRef.current);
    },
    [],
  );

  async function poll(jobId: string, attempt = 0): Promise<void> {
    if (!mountedRef.current) return;
    const latest = await client.getExportJob(jobId);
    if (!mountedRef.current) return;
    setJob(latest);
    if (latest.status !== "pending" && latest.status !== "running") return;
    if (attempt + 1 >= MAX_POLL_ATTEMPTS) {
      setError("Export toujours en cours, réessayer plus tard.");
      return;
    }
    await new Promise<void>((resolve) => {
      timerRef.current = setTimeout(resolve, POLL_INTERVAL_MS);
    });
    if (!mountedRef.current) return;
    await poll(jobId, attempt + 1);
  }

  async function onExport(format: ExportFormat) {
    setPickerOpen(false);
    setRunning(true);
    setError(null);
    setJob(null);
    try {
      const { jobId } = await client.createExport(itemId, format);
      await poll(jobId);
    } catch {
      // Message générique volontaire : ne pas répéter le texte brut d'une
      // erreur réseau/HTTP (potentiellement peu lisible) que ce soit
      // `createExport` ou une itération de `poll` qui a échoué — les deux
      // remontent ici via le même try/catch.
      if (mountedRef.current) setError("Échec de l'export.");
    } finally {
      if (mountedRef.current) setRunning(false);
    }
  }

  return (
    <div className="flex flex-col gap-2">
      <Button
        size="sm"
        variant="outline"
        onClick={() => setPickerOpen((open) => !open)}
        disabled={running}
      >
        Exporter
      </Button>
      {pickerOpen && (
        // Panneau en ligne, pas une fenêtre modale (spec §2.1, ConfirmDialog
        // seul survit) : pas d'Escape/backdrop à intercepter, Annuler ferme
        // explicitement sans exporter.
        <Panel className="flex flex-col gap-2">
          <p className="text-sm font-medium text-ink">Choisir le format d'export</p>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setPickerOpen(false)}>
              Annuler
            </Button>
            <Button type="button" variant="outline" size="sm" onClick={() => void onExport("png")}>
              PNG
            </Button>
            <Button type="button" size="sm" onClick={() => void onExport("pdf")}>
              PDF
            </Button>
          </div>
        </Panel>
      )}
      {job?.status === "done" && job.resultUrl && (
        <a href={job.resultUrl} download className="text-sm text-accent underline">
          Télécharger l&apos;export
        </a>
      )}
      {(error || job?.status === "error") && (
        <p role="alert" className="text-sm text-danger">
          {error ?? job?.error ?? "Échec de l'export."}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/print/ExportPanel.test.tsx
```

Expected: PASS (8 tests — les 6 d'origine, inchangés dans leur comportement, plus les 2 nouveaux).

- [ ] **Step 6: Vérifier `AppRuntimePage` (consommateur non touché par ce plan)**

```bash
cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx
```

Expected: PASS, sans modification à ce fichier — confirme que l'effet de bord sur cette page publique est non-cassant (cf. Global Constraints).

- [ ] **Step 7: Vérifier qu'aucune trace de `ui/dialog` ne subsiste dans ce fichier**

```bash
grep -n 'ui/dialog\|from "\.\./\.\./ui/dialog"' shell/src/builder/print/ExportPanel.tsx
```

Expected: aucune sortie.

- [ ] **Step 8: Commit**

```bash
git add shell/src/builder/print/ExportPanel.tsx shell/src/builder/print/ExportPanel.test.tsx
git commit -m "feat(shell): exportPanel — panneau en ligne, plus de Dialog modal"
```

---

## Task 5: Shell — `Terrain3DUploadButton` sans `Dialog` (panneau en ligne)

**Files:**
- Modify: `shell/src/map/Terrain3DUploadButton.tsx`
- Modify: `shell/src/map/Terrain3DUploadButton.test.tsx`

**Interfaces:**
- Consumes: `Button`/`Input`/`Panel` de `shell/src/ui/kit/`.
- Produces: `Terrain3DUploadButton({ onUploaded, pollIntervalMs? })` — API publique inchangée, consommé tel quel par `TerrainPanel` (Task 6, via `MapEditorPage`).

Même idiome que Task 4 : le formulaire d'upload (fichier + titre + phases uploading/converting/error) devient un `<Panel>` affiché sous le bouton « Nouveau DEM », plus de `<Dialog>`. La garde `busy` sur Annuler (interdire la fermeture pendant l'envoi/la conversion) est conservée — elle ne dépend pas du `Dialog`, juste de l'état `phase`.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/map/Terrain3DUploadButton.test.tsx
```

Expected: PASS (4 tests).

- [ ] **Step 2: Adapter le test « blocks Annuler/Escape/backdrop » et ajouter le test anti-régression `role=dialog`**

Le test existant `"blocks Annuler/Escape/backdrop while an upload is in progress"` (ligne 84) n'a jamais réellement exercé Escape/backdrop — seule l'assertion sur le bouton Annuler désactivé compte, et elle reste valide telle quelle avec un panneau en ligne. Renommer son titre pour ne plus promettre une couverture Escape/backdrop qui n'existe plus dans ce composant (une garde-fou n°10 : un titre de test qui ment sur ce qu'il couvre est un piège pour la prochaine lecture) :

Remplacer :
```tsx
test("blocks Annuler/Escape/backdrop while an upload is in flight", async () => {
```
par :
```tsx
test("désactive Annuler pendant un envoi en cours (plus d'Escape/backdrop à gérer — panneau en ligne)", async () => {
```

Ajouter, à la fin du fichier, un nouveau test :

```tsx
test("le formulaire n'est jamais une fenêtre modale (pas de role=dialog)", async () => {
  renderButton(vi.fn());
  await userEvent.click(screen.getByRole("button", { name: /nouveau dem/i }));
  expect(await screen.findByLabelText(/fichier dem/i)).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec du nouveau test**

```bash
cd shell && npx vitest run src/map/Terrain3DUploadButton.test.tsx -t "jamais une fenêtre modale"
```

Expected: FAIL — le composant actuel rend encore un `<Dialog>` (donc `role="dialog"` existe).

- [ ] **Step 4: Réécrire `Terrain3DUploadButton.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useItemClient } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Panel } from "../ui/kit/Panel";

const DEFAULT_POLL_INTERVAL_MS = 1500;
// Un job de conversion qui n'atteint jamais un état terminal ne doit pas
// laisser le panneau définitivement infermable — même garde-fou que
// Tileset3DUploadButton (design tileset3d hosting, leçon Task 12/I3).
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

type Phase = "form" | "uploading" | "converting" | "error";

// pollIntervalMs is injectable for tests only (this file's suite is
// MSW-based with real timers, where fake timers would fight userEvent's
// own scheduler) — mirrors Tileset3DUploadButton's pollTimeoutMs param.
export function Terrain3DUploadButton({
  onUploaded,
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
}: {
  onUploaded: (itemId: string) => void;
  pollIntervalMs?: number;
}) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [error, setError] = useState("");
  const client = useItemClient();

  function close() {
    setOpen(false);
    setFile(null);
    setTitle("");
    setPhase("form");
    setError("");
  }

  async function poll(jobId: string) {
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    for (;;) {
      const job = await client.getTerrain3DUploadJob(jobId);
      if (job.status === "done" && job.itemId) {
        onUploaded(job.itemId);
        close();
        return;
      }
      if (job.status === "error") {
        setPhase("error");
        setError(job.errorMessage ?? "Échec de la conversion du DEM.");
        return;
      }
      if (Date.now() >= deadline) {
        setPhase("error");
        setError("La conversion du DEM prend trop de temps. Réessayez plus tard.");
        return;
      }
      await new Promise((r) => setTimeout(r, pollIntervalMs));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !title.trim()) return;
    setPhase("uploading");
    setError("");
    try {
      // Route dédiée (jamais presignUpload générique) : elle signe dans le
      // bucket terrain3d, le seul que le worker de conversion lit. Le type
      // est celui que le navigateur enverra réellement — fetch(PUT, body:
      // File) envoie File.type, et un type signé différent fait échouer S3
      // en 403 SignatureDoesNotMatch (même traitement qu'ImportFileButton).
      const { uploadUrl, key } = await client.presignTerrain3DUpload(
        file.name,
        file.type || "application/octet-stream",
      );
      await client.uploadToPresignedUrl(uploadUrl, file);
      setPhase("converting");
      const { jobId } = await client.createTerrain3DUpload({
        key,
        filename: file.name,
        title: title.trim(),
      });
      await poll(jobId);
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Échec de l'envoi du DEM.");
    }
  }

  const busy = phase === "uploading" || phase === "converting";

  // Panneau en ligne, pas une fenêtre modale (spec §2.1) : plus d'Escape ni
  // de backdrop à intercepter. Seul le bouton Annuler ferme, et reste
  // désactivé pendant l'envoi/la conversion — fermer laisserait submit()/
  // poll() tourner en arrière-plan sans rien pour le refléter.
  return (
    <div className="flex flex-col gap-2">
      <Button size="sm" variant="outline" className="w-fit" onClick={() => setOpen((o) => !o)}>
        Nouveau DEM
      </Button>
      {open && (
        <Panel className="flex flex-col gap-3">
          <h4 className="text-sm font-semibold text-ink">Nouveau DEM</h4>
          <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
            <label className="flex flex-col gap-1 text-sm text-ink">
              Fichier DEM (GeoTIFF)
              <input
                aria-label="Fichier DEM (GeoTIFF)"
                type="file"
                accept=".tif,.tiff"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-ink">
              Titre
              <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
            </label>
            {phase === "uploading" && <p className="text-sm text-ink-2">Envoi du fichier…</p>}
            {phase === "converting" && <p className="text-sm text-ink-2">Conversion en COG…</p>}
            {phase === "error" && (
              <p role="alert" className="text-sm text-danger">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <Button type="button" variant="outline" size="sm" onClick={close} disabled={busy}>
                Annuler
              </Button>
              <Button type="submit" size="sm" disabled={busy || !file || !title.trim()}>
                {busy ? "Envoi…" : "Importer"}
              </Button>
            </div>
          </form>
        </Panel>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/map/Terrain3DUploadButton.test.tsx
```

Expected: PASS (5 tests — les 4 d'origine, comportement inchangé, plus le nouveau).

- [ ] **Step 6: Vérifier `TerrainPanel` (consommateur direct)**

```bash
cd shell && npx vitest run src/map/TerrainPanel.test.tsx
```

Expected: PASS, sans modification (l'API de `Terrain3DUploadButton` n'a pas changé).

- [ ] **Step 7: Vérifier qu'aucune trace de `ui/dialog`/`ui/input`/`ui/button` ne subsiste**

```bash
grep -n 'ui/dialog\|ui/input"\|ui/button"' shell/src/map/Terrain3DUploadButton.tsx
```

Expected: aucune sortie.

- [ ] **Step 8: Commit**

```bash
git add shell/src/map/Terrain3DUploadButton.tsx shell/src/map/Terrain3DUploadButton.test.tsx
git commit -m "feat(shell): terrain3DUploadButton — panneau en ligne, plus de Dialog modal"
```

---

## Task 6: Shell — `MapEditorPage` sur `TriptychLayout` (« Couches / Carte / Inspecter »)

**Files:**
- Modify: `shell/src/pages/MapEditorPage.tsx`
- Modify: `shell/src/pages/MapEditorPage.test.tsx`

**Interfaces:**
- Consumes: `TriptychLayout` (`shell/src/shell/chrome/TriptychLayout.tsx`, `{browse,work,inspect,defaultTabId}` — SP-30a) ; `LayersPanel`/`BasemapSelect`/`TerrainPanel`/`CameraControls` (Tasks 1-3, API inchangées) ; `ExportPanel`/`ConfigHistoryPanel`/`PrintLayoutPanel` (Tasks 1/4, API inchangées) ; `Button` du kit.
- Produces: `MapEditorPage({ pk: string })` — API publique inchangée, `MapEditorRoute` dans `shell/src/shell/routes.tsx` ne change pas.

Le libellé des trois onglets — « Couches », « Carte », « Inspecter » — est donné littéralement par la spec (§2.1 point 4, exemple pour la carte), pas une invention de ce plan. `LayersPanel` embarque déjà `LayerPicker` (vérifié par lecture : `import { LayerPicker } from "./LayerPicker"` dans `LayersPanel.tsx`) — le volet **browse** « Couches » est donc `LayersPanel` seul, sans nouveau composant. La branche `isExportRender` reste un retour anticipé avant tout chrome triptyque, totalement inchangée.

- [ ] **Step 1: Écrire le stub `matchMedia` et le test de dégradation en onglets**

Ajouter en tête de `shell/src/pages/MapEditorPage.test.tsx`, juste après les `vi.mock(...)` existants et avant `beforeEach` :

```tsx
// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. Stub local au fichier, jamais dans
// shell/src/test/setup.ts. matches: false => le layout "large" (3 volets
// simultanés), pas les onglets — la valeur par défaut de la plupart des
// tests existants de ce fichier, qui n'affirment pas sur la largeur.
function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
}
```

Dans le `beforeEach` existant (celui qui réinitialise `mapInstances`/`overlayInstances`/`fetch`), ajouter en première ligne :

```tsx
beforeEach(() => {
  stubMatchMedia(false);
  mapInstances.length = 0;
  overlayInstances.length = 0;
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("not mocked in this test")));
});
```

Ajouter, en fin de fichier, un nouveau test qui vérifie la dégradation en onglets sous viewport étroit :

```tsx
test("sous viewport étroit, affiche trois onglets Couches/Carte/Inspecter avec Carte active par défaut", async () => {
  stubMatchMedia(true);
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Couches", "Carte", "Inspecter"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Carte");
});
```

- [ ] **Step 2: Lancer les tests, vérifier l'échec du nouveau test (les anciens doivent encore passer — comportement inchangé jusqu'ici)**

```bash
cd shell && npx vitest run src/pages/MapEditorPage.test.tsx
```

Expected: le nouveau test « sous viewport étroit… » FAIL (`MapEditorPage` ne rend encore aucun `role="tab"`) ; les 8 tests existants PASS (le stub `matchMedia(false)` ajouté au `beforeEach` ne change le comportement d'aucun d'eux tant que `MapEditorPage` ne consomme pas encore `useNarrowViewport`).

- [ ] **Step 3: Réécrire `MapEditorPage.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef, useState } from "react";
import { useInstanceInfo, useMapConfig, useSaveMap } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { MapConfig, MapLayer, MapTerrainConfig, PrintLayoutConfig } from "../api/types";
import { MapView, type MapViewHandle } from "../map/MapView";
import { LayersPanel } from "../map/LayersPanel";
import { BasemapSelect } from "../map/BasemapSelect";
import { TerrainPanel } from "../map/TerrainPanel";
import { CameraControls } from "../map/CameraControls";
import { PrintLayoutPanel } from "../builder/print/PrintLayoutPanel";
import { ExportPanel } from "../builder/print/ExportPanel";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { Button } from "../ui/kit/Button";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { useIsExportRender } from "../shell/useIsExportRender";
import { markExportReady } from "../shell/exportReady";

export function MapEditorPage({ pk }: { pk: string }) {
  const client = useItemClient();
  const query = useMapConfig(pk);
  const save = useSaveMap(pk);
  const [draft, setDraft] = useState<MapConfig | null>(null);
  const mapViewRef = useRef<MapViewHandle>(null);
  const isExportRender = useIsExportRender();
  const instanceQuery = useInstanceInfo();
  const exportEnabled = instanceQuery.data?.exportEnabled === true;

  useEffect(() => {
    if (query.data) setDraft(query.data);
  }, [query.data]);

  // `draft` lags one render behind a successful load (it is synced in the
  // effect above), so keep showing the loader during that gap instead of
  // flashing the error.
  if (query.isLoading || (!draft && !query.isError)) return <p role="status">Chargement…</p>;
  if (query.isError || !draft)
    return (
      <p role="alert" className="text-sm text-danger">
        Carte introuvable.
      </p>
    );

  const setLayers = (layers: MapLayer[]) => setDraft({ ...draft, layers });
  const setStyle = (style: string) => setDraft({ ...draft, basemap: { style } });
  const setView = (view: {
    center: [number, number];
    zoom: number;
    pitch: number;
    bearing: number;
  }) => setDraft((d) => (d ? { ...d, view } : d));
  function setPrintLayout(printLayout: PrintLayoutConfig | null) {
    setDraft((d) => (d ? { ...d, printLayout } : d));
  }
  function setTerrain(terrain: MapTerrainConfig | null) {
    setDraft((d) => (d ? { ...d, terrain } : d));
  }
  const currentDraft = draft;
  function setCamera(next: { pitch: number; bearing: number }) {
    setDraft((d) => (d ? { ...d, view: { ...d.view, ...next } } : d));
    mapViewRef.current?.flyTo({
      center: currentDraft.view.center,
      zoom: currentDraft.view.zoom,
      ...next,
    });
  }

  // Export/print chrome (SP-17a Task 10): the Playwright worker (Task 6)
  // navigates here with ?exportRender=1 to capture a clean shot of the map
  // plus the PrintLayoutConfig overlays — no builder aside, no editor UI, no
  // triptyque chrome. Ready signal = MapLibre "idle" (map.once), relayed via
  // MapView's onReady. showScaleBar/showNorthArrow are intentionally not
  // rendered yet (known limitation, tracked in the Task 10 report — not a
  // silent no-op). bg-white/90 stays hardcoded here on purpose (a print
  // artifact meant to look like paper, not UI chrome — spec §2.2, the map
  // itself also always stays light regardless of ambiance).
  if (isExportRender) {
    return (
      <div className="relative h-full w-full">
        <MapView
          config={draft}
          onReady={markExportReady}
          hideLegend
          getAuthToken={client.getAuthToken}
          getCoreUrl={client.getCoreUrl}
          loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}
        />
        {draft.printLayout?.title && (
          <div className="absolute left-2 top-2 rounded bg-white/90 px-2 py-1 text-sm font-medium">
            {draft.printLayout.title}
          </div>
        )}
        {draft.printLayout?.showLegend && (
          <ul className="absolute bottom-2 left-2 rounded bg-white/90 px-2 py-1 text-xs">
            {draft.layers
              .filter((l) => l.visible)
              .map((l) => (
                <li key={l.id}>{l.title}</li>
              ))}
          </ul>
        )}
        {draft.printLayout?.cartouche && (
          <div className="absolute bottom-2 right-2 rounded bg-white/90 px-2 py-1 text-xs">
            {draft.printLayout.cartouche}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="map"
        browse={{
          id: "layers",
          label: "Couches",
          content: (
            <div className="p-3">
              <LayersPanel layers={draft.layers} onChange={setLayers} />
            </div>
          ),
        }}
        work={{
          id: "map",
          label: "Carte",
          content: (
            <div className="relative h-full w-full">
              <MapView
                ref={mapViewRef}
                config={draft}
                onViewChange={setView}
                getAuthToken={client.getAuthToken}
                getCoreUrl={client.getCoreUrl}
                loadCustomIcon={(iconId) => client.fetchMapIconBlob(iconId)}
              />
            </div>
          ),
        }}
        inspect={{
          id: "settings",
          label: "Inspecter",
          content: (
            <div className="flex flex-col gap-4 p-3">
              <BasemapSelect value={draft.basemap.style} onChange={setStyle} />
              <TerrainPanel value={draft.terrain ?? null} onChange={setTerrain} />
              <CameraControls
                pitch={draft.view.pitch ?? 0}
                bearing={draft.view.bearing ?? 0}
                onChange={setCamera}
              />
              <PrintLayoutPanel value={draft.printLayout ?? null} onChange={setPrintLayout} />
              <ConfigHistoryPanel
                pk={pk}
                currentVersion={null}
                onRestored={async () => setDraft(await client.getMapConfig(pk))}
              />
              {exportEnabled && <ExportPanel itemId={pk} />}
              <Button
                size="sm"
                className="w-fit"
                disabled={save.isPending}
                onClick={() => save.mutate(draft)}
              >
                Enregistrer
              </Button>
              {save.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec de l'enregistrement.
                </p>
              )}
            </div>
          ),
        }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/pages/MapEditorPage.test.tsx
```

Expected: PASS — les 8 tests existants (aucun ne cherche une structure DOM particulière hors des rôles/labels déjà stables : boutons « Retirer Couche A »/« Enregistrer »/« Réinitialiser en 2D », labels des champs terrain/caméra, texte « Historique », comportement `exportRender=1`) plus le nouveau test des onglets.

- [ ] **Step 5: `tsc --noEmit` + build**

```bash
cd shell && npm run build
```

Expected: PASS. Si le build échoue sur une référence résiduelle à `ui/button`/`ui/dialog`/`ui/input` dans un fichier de cette famille, c'est un oubli d'une tâche précédente — corriger avant de continuer, ne pas committer un build rouge.

- [ ] **Step 6: E2E — specs de la famille Cartes**

```bash
cd shell && npx playwright test map-editor.spec.ts map-symbology.spec.ts map-symbology-advanced.spec.ts map-popup.spec.ts map-measure-sketch.spec.ts map-feature-layer-symbology.spec.ts
```

Expected: PASS, sans modification à aucun de ces fichiers `.spec.ts` — ils interagissent par rôle/label, pas par structure de layout, et ne référencent ni `ExportPanel` ni `Terrain3DUploadButton` par leur ancien comportement modal.

- [ ] **Step 7: Commit**

```bash
git add shell/src/pages/MapEditorPage.tsx shell/src/pages/MapEditorPage.test.tsx
git commit -m "feat(shell): mapEditorPage sur TriptychLayout (Couches/Carte/Inspecter)"
```

---

## Task 7: Vérification finale — suite complète + portes de qualité

**Files:** aucun changement de fichier — tâche de vérification uniquement.

- [ ] **Step 1: Suite Vitest complète**

```bash
cd shell && npm run test
```

Expected: PASS, aucune régression sur les fichiers non touchés par ce plan (en particulier les quatre autres pages consommant `ConfigHistoryPanel` et `AppRuntimePage` consommant `ExportPanel`, déjà vérifiées individuellement aux Tasks 1/4 mais revérifiées ici dans le run complet).

- [ ] **Step 2: Couverture**

```bash
rm -rf shell/dist shell/dist-export
cd shell && npm run build
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```

Expected: seuil 88 respecté (piège documenté quatre fois : nettoyer `dist/`/`dist-export/` avant de mesurer).

- [ ] **Step 3: Suite E2E complète**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed (référence SP-30b) ou mieux (les nouveaux tests unitaires de ce plan ne s'ajoutent pas au compte E2E, aucun nouveau spec Playwright n'est créé par ce plan). Si un total différent apparaît, diagnostiquer contre le fichier `.spec.ts` précis en échec avant de conclure — ne jamais réajuster silencieusement le nombre attendu dans un rapport.

- [ ] **Step 4: Lint + format + contrat de couches**

```bash
cd shell && npm run lint && npm run format:check
cd core && uv run lint-imports
```

Expected: PASS, aucune nouvelle entrée de contrat de couches (aucun changement au cœur dans ce plan).

- [ ] **Step 5: Recherche exhaustive de couleurs Tailwind en dur résiduelles dans les fichiers touchés par ce plan**

```bash
grep -rnE 'text-(red|slate|blue|gray|black|amber)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/map/CameraControls.tsx shell/src/builder/ConfigHistoryPanel.tsx \
  shell/src/map/LayerPicker.tsx shell/src/map/BasemapSelect.tsx shell/src/map/TerrainPanel.tsx \
  shell/src/builder/print/PrintLayoutPanel.tsx shell/src/map/LayersPanel.tsx \
  shell/src/builder/print/ExportPanel.tsx shell/src/map/Terrain3DUploadButton.tsx \
  shell/src/pages/MapEditorPage.tsx
```

Expected: aucune sortie (l'exception documentée `bg-white/90` de la branche `isExportRender` n'est pas dans cette liste de patterns — vérifier qu'elle n'apparaît que là par une seconde passe si le grep ci-dessus remonte quelque chose d'inattendu).

- [ ] **Step 6: Recherche exhaustive de `ui/dialog`/`ui/button`/`ui/input`/`ui/card` résiduels dans les dix fichiers touchés**

```bash
grep -rn 'ui/dialog"\|ui/button"\|ui/input"\|ui/card"' \
  shell/src/map/CameraControls.tsx shell/src/builder/ConfigHistoryPanel.tsx \
  shell/src/map/LayerPicker.tsx shell/src/map/BasemapSelect.tsx shell/src/map/TerrainPanel.tsx \
  shell/src/builder/print/PrintLayoutPanel.tsx shell/src/map/LayersPanel.tsx \
  shell/src/builder/print/ExportPanel.tsx shell/src/map/Terrain3DUploadButton.tsx \
  shell/src/pages/MapEditorPage.tsx
```

Expected: aucune sortie.

Ce plan ne se termine pas par un commit propre — c'est une tâche de vérification. Si un des steps échoue, revenir à la tâche responsable (identifiable par le fichier en cause) pour corriger, jamais par un correctif générique en Task 7.

---

## Suivis non bloquants pour SP-30d+

- **Éditeurs de symbologie/popup profondément imbriqués** (`MapSymbologyEditor.tsx` 797 lignes/27 couleurs, `PopupEditor.tsx`, `FieldClassificationPicker.tsx`, `MapMeasureSketchToolbar.tsx`, `MapPopup.tsx`, `MapLegend.tsx`, `formFieldStyles.ts`) : dette de tokens purement cosmétique, aucun `Dialog` modal, ne bloque pas la bascule de `MapEditorPage`. À traiter dans un plan dédié plus tard (potentiellement hors SP-30 lui-même, vu leur volume).
- **`Tileset3DUploadButton`/`NewItemButton`/`ImportFileButton`** : `Dialog` non éliminé, dette héritée de SP-30a (« inchangés, relocalisés » dans le chrome) — hors périmètre de la famille Cartes, à couvrir par le plan qui traitera le dernier `Dialog` résiduel du dépôt.
- **`AppExportPanel.tsx`** (export d'apps, distinct d'`ExportPanel`) : même patron de `Dialog` de choix de format (commentaire en tête de fichier : « Même patron de dialogue de choix de mode qu'ExportPanel »), non touché par ce plan — scope Apps & sites (famille 5, SP-30d+).
