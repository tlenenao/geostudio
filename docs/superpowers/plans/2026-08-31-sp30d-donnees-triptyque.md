# SP-30d — Données sur le socle triptyque (DatasetEditPage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Basculer la famille **Données** (`docs/superpowers/specs/2026-08-30-sp30-bascule-triptyque-design.md` §6.1, famille 4) sur `TriptychLayout` : `DatasetEditPage`, avec trois onglets propres à cette page — « Catalogue » (retour, même idiome qu'`ItemDetailPage`), « Dataset » (métadonnées, colonnes, cross-filter — le contenu éditable), « Réglages » (export, alertes, historique, requête source, Enregistrer — même regroupement que « Inspecter » sur `MapEditorPage`, SP-30c).

**Important — ce que ce plan NE fait PAS, parce que c'est déjà livré** : le §4 de la spec (« Extension des permissions aux collections », `CollectionPermissions` cœur + consommation shell) a été implémenté comme prérequis du chrome dans **SP-30a**, pas dans ce plan — vérifié par lecture directe du code avant d'écrire ce plan (piège n°3, ne jamais se fier au texte de la spec/CLAUDE.md seul) :
- `core/app/collections/schemas.py` a déjà `CollectionPermissions` ; `core/app/collections/repository.py` a déjà `collection_permissions_by_id()` (batché, anti-N+1, testé par `core/tests/test_collections_no_nplus1.py`) ; `_collection_json()` dans `core/app/collections/routes.py` sert déjà `permissions`, plus `canWrite` — commit `dfafc3f`, sous le plan `docs/superpowers/plans/2026-08-30-sp30a-chrome-triptyque.md` Task 1.
- `shell/src/builder/pipeline/CollectionParamSelect.tsx` consomme déjà `hasPermission(c, "write")` (plus de `canWrite`).
- `openapi.json`/`core-schema.d.ts` régénérés dans SP-30a (commit `31468bc`).

Il ne reste donc, pour clore la famille 4, que la bascule de l'écran `DatasetEditPage` lui-même et de ses deux composants enfants exclusifs.

**Périmètre explicitement hors de ce plan** (familles 5 à 8 du §6.1, à traiter dans des plans SP-30e+ séparés) : `AppBuilderPage` (Apps & sites), `PipelineBuilderPage`/`ReportEditPage`/`VisualQueryWizardPage` (Automatisation), `SqlLabPage` (Analytique), `AdminExtensionsPage`/`CollectionsAdminPage`/`HarvestSourcesAdminPage` (Administration). Également hors de ce plan : les 9 occurrences de comparaison de droits en dur encore présentes dans `SqlLabPage.tsx`/`AdminExtensionsPage.tsx`/`HarvestSourcesAdminPage.tsx`/`CollectionsAdminPage.tsx`/`AppLayout.tsx` (aucun de ces fichiers n'est touché ici) ; la dette de tokens des éditeurs de symbologie/popup imbriqués dans `LayersPanel` (héritée de SP-30c, famille Cartes, sans rapport avec Données) ; `Tileset3DUploadButton`/`NewItemButton`/`ImportFileButton` (chrome, `Dialog` non éliminé, dette documentée depuis SP-30a) ; `AppExportPanel.tsx` (scope Apps & sites).

**Architecture:** `DatasetEditPage` s'enveloppe dans `<div className="-m-6 flex flex-1 flex-col overflow-hidden">` (même technique de transition locale que `CatalogPage`/`ItemDetailPage`/`MapEditorPage`) et instancie `TriptychLayout` avec trois volets : **browse** = « Catalogue » (lien de retour + `<dl>` Type/Modifié, exactement le même idiome qu'`ItemDetailPage.tsx:79-95` — cette page n'a pas de liste-métier équivalente à `LayersPanel`, donc pas de raison de s'en écarter) ; **work** = « Dataset » (le titre de page, `MetadataForm`, le tableau des colonnes, le champ temporel, la case « Réagir au déplacement de la carte », les liens cross-filter) ; **inspect** = « Réglages » (Export, `AlertRuleEditor`, `ConfigHistoryPanel`, le bouton « Modifier la requête » conditionnel, le bouton Enregistrer — même regroupement fonctionnel que le volet « Inspecter » de `MapEditorPage`, SP-30c). `AlertRuleEditor` et `CrossFilterLinkEditor` (vérifié par grep : consommés **uniquement** par `DatasetEditPage`, aucune autre page) gagnent une passe de tokens et, pour `AlertRuleEditor`, le bouton `Button` du kit — aucun des deux n'importe `ui/dialog`, rien à convertir côté modal.

**Tech Stack:** React 19, `@tanstack/react-query`, react-router-dom, kit de primitives SP-29b (`shell/src/ui/kit/`), Vitest + Testing Library, Playwright.

## Global Constraints

- Docs et identifiants de test en français ; code/identifiants en anglais (CLAUDE.md).
- Aucune couleur Tailwind en dur (`slate-*`, `red-*`, `blue-*`, `amber-*`, `white`, `black`) dans les fichiers touchés par ce plan : tokens uniquement (`bg-surface`, `text-ink`, `text-ink-2`, `text-ink-3`, `border-rule`, `bg-raised`, `bg-sunken`, `text-danger`, `text-accent`, `text-warn` — `shell/src/styles/tokens.css`).
- Aucun `<Dialog>` (ancien `ui/dialog.tsx` ou `ui/kit/Dialog`) n'apparaît dans les trois fichiers touchés par ce plan, avant comme après (vérifié par grep en Task 3) — rien à convertir, à la différence de la famille Cartes (SP-30c) qui avait `ExportPanel`/`Terrain3DUploadButton`.
- `-m-6` est une technique de transition **locale à `DatasetEditPage.tsx` seul** dans ce plan, jamais un changement à `AppLayout.tsx`.
- Régressions jsdom (piège n°10) : `window.matchMedia` n'existe pas sous jsdom — `TriptychLayout` l'appelle via `useNarrowViewport`. Stub local à `DatasetEditPage.test.tsx` (copier le patron exact de `MapEditorPage.test.tsx`/`ItemDetailPage.test.tsx`, `matches: false` par défaut), jamais dans `shell/src/test/setup.ts`.
- Pas de changement au cœur (`core/`) dans ce plan — le travail `CollectionPermissions` était déjà livré par SP-30a (cf. note en tête). Aucune régénération OpenAPI/TS attendue, diff vide légitime (piège n°1 — vide parce qu'aucun schéma ne change, pas parce qu'une surface est derrière un flag) ; vérifié en Task 3 par `git status --short core/`.
- E2E : `shell/e2e/datasets-shared.spec.ts`, `dataset-export.spec.ts`, `dataset-arcgis.spec.ts`, `alert-rule.spec.ts`, `visual-query.spec.ts` sont le filet de non-régression comportementale de cette famille — vérifié par lecture (Playwright, `getByRole`/`getByLabel` uniquement, aucune dépendance à la structure DOM du layout) et doivent rester verts **sans modification de leur texte** (Task 2).

---

## Task 1: Shell — kit-ifier `AlertRuleEditor` et `CrossFilterLinkEditor` (tokens + Button)

**Files:**
- Modify: `shell/src/builder/AlertRuleEditor.tsx`
- Modify: `shell/src/builder/CrossFilterLinkEditor.tsx`
- Test: `shell/src/builder/AlertRuleEditor.test.tsx` (baseline, doit passer sans modification)
- Test: `shell/src/builder/CrossFilterLinkEditor.test.tsx` (baseline, doit passer sans modification)

**Interfaces:**
- Consumes: `Button` de `shell/src/ui/kit/Button.tsx` (`variant: "default"|"outline"|"ghost"|"danger"`, `size: "default"|"sm"|"icon"`).
- Produces: aucune API publique changée — `AlertRuleEditor({datasetItemId, owner})` et `CrossFilterLinkEditor({link, sourceFields, targetOptions, onChange, onRemove})` inchangées, consommées telles quelles par Task 2.

Ni l'un ni l'autre n'importe `ui/dialog`/`ui/button`/`ui/input` — seules des couleurs Tailwind en dur doivent devenir des tokens, plus un vrai bouton d'action (« Créer la règle ») à faire passer sur le kit `Button` (même distinction qu'en SP-30c : un bouton d'action autonome devient `Button`, un lien texte inline — « Supprimer le lien » — reste natif avec des tokens, même patron que le lien « réessayer » de `LayerPicker.tsx`).

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/builder/AlertRuleEditor.test.tsx src/builder/CrossFilterLinkEditor.test.tsx
```

Expected: PASS (4 tests + 6 tests).

- [ ] **Step 2: `AlertRuleEditor.tsx` — import Button + tokens**

Ajouter l'import, après les imports existants :
```tsx
import { PipelineScheduleEditor } from "./pipeline/PipelineScheduleEditor";
import type { PipelineRefreshPolicy } from "../api/types";
```
devient :
```tsx
import { PipelineScheduleEditor } from "./pipeline/PipelineScheduleEditor";
import type { PipelineRefreshPolicy } from "../api/types";
import { Button } from "../ui/kit/Button";
```

Remplacer dans `AlertRuleRow` :
```tsx
    <div className="flex items-center justify-between border-t border-slate-200 py-1 text-xs">
      <span>{rule.title}</span>
      <span
        className={latest?.state === "firing" ? "font-semibold text-red-600" : "text-slate-500"}
      >
```
par :
```tsx
    <div className="flex items-center justify-between border-t border-rule py-1 text-xs">
      <span>{rule.title}</span>
      <span
        className={latest?.state === "firing" ? "font-semibold text-danger" : "text-ink-2"}
      >
```

Remplacer :
```tsx
      <p className="text-xs font-medium text-slate-500">Alertes</p>
      {rulesQuery.isError && (
        <p role="alert" className="text-sm text-red-600">
```
par :
```tsx
      <p className="text-xs font-medium text-ink-2">Alertes</p>
      {rulesQuery.isError && (
        <p role="alert" className="text-sm text-danger">
```

Remplacer les trois champs (trois des quatre occurrences de `border-slate-300` du fichier — `grep -c border-slate-300 shell/src/builder/AlertRuleEditor.tsx` renvoie 4 : ces trois champs plus le bouton « Créer la règle » ci-dessous, dont la conversion en `Button` du kit fait disparaître la quatrième en même temps que l'élément `<button>` natif) :
```tsx
      <div className="flex flex-col gap-2 border-t border-slate-200 pt-2 text-xs">
        <label className="flex flex-col gap-1">
          Nom de la règle
          <input
            aria-label="Nom de la règle"
            className="h-8 rounded border border-slate-300 px-2"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          Condition (expression)
          <input
            aria-label="Condition (expression)"
            className="h-8 rounded border border-slate-300 px-2 font-mono"
            placeholder="value > 100"
            value={expr}
            onChange={(e) => setExpr(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          URL du webhook
          <input
            aria-label="URL du webhook"
            className="h-8 rounded border border-slate-300 px-2"
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
          />
        </label>
```
par :
```tsx
      <div className="flex flex-col gap-2 border-t border-rule pt-2 text-xs">
        <label className="flex flex-col gap-1">
          Nom de la règle
          <input
            aria-label="Nom de la règle"
            className="h-8 rounded border border-rule bg-surface px-2 text-ink"
            value={name}
            onChange={(e) => setName(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          Condition (expression)
          <input
            aria-label="Condition (expression)"
            className="h-8 rounded border border-rule bg-surface px-2 font-mono text-ink"
            placeholder="value > 100"
            value={expr}
            onChange={(e) => setExpr(e.target.value)}
          />
        </label>
        <label className="flex flex-col gap-1">
          URL du webhook
          <input
            aria-label="URL du webhook"
            className="h-8 rounded border border-rule bg-surface px-2 text-ink"
            value={webhookUrl}
            onChange={(e) => setWebhookUrl(e.target.value)}
          />
        </label>
```

Remplacer le bouton natif par le `Button` du kit :
```tsx
        <PipelineScheduleEditor value={refreshPolicy} onChange={setRefreshPolicy} />
        <button
          type="button"
          className="self-start rounded border border-slate-300 px-2 py-1 hover:bg-slate-100"
          onClick={() => void handleCreate()}
          disabled={createRule.isPending}
        >
          Créer la règle
        </button>
        {createError && (
          <p role="alert" className="text-red-600">
            {createError}
          </p>
        )}
```
par :
```tsx
        <PipelineScheduleEditor value={refreshPolicy} onChange={setRefreshPolicy} />
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="self-start"
          onClick={() => void handleCreate()}
          disabled={createRule.isPending}
        >
          Créer la règle
        </Button>
        {createError && (
          <p role="alert" className="text-danger">
            {createError}
          </p>
        )}
```

- [ ] **Step 3: `CrossFilterLinkEditor.tsx` — tokens seuls**

Remplacer le conteneur :
```tsx
    <div className="flex flex-col gap-2 rounded border border-slate-200 p-2 text-xs">
```
par :
```tsx
    <div className="flex flex-col gap-2 rounded border border-rule p-2 text-xs">
```

Remplacer, une par une, les occurrences de `className="h-8 rounded border border-slate-300 px-2"` (vérifier le compte exact avant d'éditer) :
```bash
grep -c 'border-slate-300' shell/src/builder/CrossFilterLinkEditor.tsx
```
Expected: 5 (les cinq `<select>` : Dataset cible, Mode du lien, Champ source, Champ cible dans la branche attribute, Précision spatiale du lien dans la branche spatial).

Chaque occurrence de :
```tsx
          className="h-8 rounded border border-slate-300 px-2"
```
devient :
```tsx
          className="h-8 rounded border border-rule bg-surface px-2 text-ink"
```

Remplacer le bouton de suppression :
```tsx
      <button type="button" className="self-start text-red-600 underline" onClick={onRemove}>
```
par :
```tsx
      <button type="button" className="self-start text-danger underline" onClick={onRemove}>
```

- [ ] **Step 4: Vérifier qu'aucune couleur Tailwind en dur ni ancien import ne subsiste**

```bash
grep -nE 'text-(red|slate|blue|gray|black|amber)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/AlertRuleEditor.tsx shell/src/builder/CrossFilterLinkEditor.tsx
grep -n 'ui/dialog"\|ui/button"\|ui/input"\|ui/card"' \
  shell/src/builder/AlertRuleEditor.tsx shell/src/builder/CrossFilterLinkEditor.tsx
```

Expected: aucune sortie pour les deux commandes.

- [ ] **Step 5: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/AlertRuleEditor.test.tsx src/builder/CrossFilterLinkEditor.test.tsx
```

Expected: PASS (4 tests + 6 tests, sans aucune modification aux deux fichiers de test — aucun n'affirme sur une classe CSS ou un rôle changé par ce refactor).

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/AlertRuleEditor.tsx shell/src/builder/CrossFilterLinkEditor.tsx
git commit -m "feat(shell): alertRuleEditor/crossFilterLinkEditor — kit Button + tokens"
```

---

## Task 2: Shell — `DatasetEditPage` sur `TriptychLayout` (« Catalogue / Dataset / Réglages »)

**Files:**
- Modify: `shell/src/pages/DatasetEditPage.tsx`
- Modify: `shell/src/pages/DatasetEditPage.test.tsx`

**Interfaces:**
- Consumes: `TriptychLayout` (`shell/src/shell/chrome/TriptychLayout.tsx`, `{browse,work,inspect,defaultTabId}` — SP-30a) ; `Panel`/`Button` du kit ; `AlertRuleEditor`/`CrossFilterLinkEditor` (Task 1, API inchangées) ; `MetadataForm`/`ConfigHistoryPanel` (déjà kit-ifiés, API inchangées).
- Produces: `DatasetEditPage({ pk: string })` — API publique inchangée, `DatasetEditRoute` dans `shell/src/shell/routes.tsx` ne change pas.

Le volet **browse** reprend littéralement l'idiome d'`ItemDetailPage.tsx:79-95` (lien de retour + `<dl>` Type/Modifié) : cette page n'a pas de panneau-liste métier (contrairement à `LayersPanel` pour les cartes), donc pas de raison d'inventer un contenu différent. Le volet **work** porte tout le contenu directement éditable (métadonnées, colonnes, champ temporel, cross-filter). Le volet **inspect** regroupe export/alertes/historique/requête-source/enregistrer, même logique que le volet « Inspecter » de `MapEditorPage` (SP-30c) : tout ce qui n'est ni la navigation ni l'édition directe du contenu.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/pages/DatasetEditPage.test.tsx
```

Expected: PASS (11 tests).

- [ ] **Step 2: Ajouter le stub `matchMedia` et le test de dégradation en onglets**

Dans `shell/src/pages/DatasetEditPage.test.tsx`, remplacer la ligne d'import vitest :
```tsx
import { expect, test, vi } from "vitest";
```
par :
```tsx
import { beforeEach, expect, test, vi } from "vitest";
```

Ajouter, juste après la fonction `VisualQueryEditProbe` et avant `function renderPage(...)` :

```tsx
// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. Stub local au fichier, jamais dans
// shell/src/test/setup.ts. matches: false => le layout "large" (3 volets
// simultanés), pas les onglets — la valeur par défaut de tous les tests
// existants de ce fichier, qui n'affirment pas sur la largeur.
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

beforeEach(() => {
  stubMatchMedia(false);
});
```

Ajouter, en fin de fichier, un nouveau test :

```tsx
test("sous viewport étroit, affiche trois onglets Catalogue/Dataset/Réglages avec Dataset actif par défaut", async () => {
  stubMatchMedia(true);
  renderPage({
    getItem: vi.fn().mockResolvedValue(item),
    getDatasetConfig: vi.fn().mockResolvedValue(datasetConfig),
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
  });
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Dataset", "Réglages"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Dataset");
});
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec du nouveau test (les 11 existants doivent encore passer)**

```bash
cd shell && npx vitest run src/pages/DatasetEditPage.test.tsx
```

Expected: le nouveau test « sous viewport étroit… » FAIL (`DatasetEditPage` ne rend encore aucun `role="tab"`) ; les 11 tests existants PASS (le stub `matchMedia(false)` du `beforeEach` ne change le comportement d'aucun d'eux tant que `DatasetEditPage` ne consomme pas encore `useNarrowViewport`).

- [ ] **Step 4: Réécrire `DatasetEditPage.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useDatasetConfig, useItem, useItems, useSaveDataset, useUpdateItem } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { CrossFilterLink, DatasetColumnMeta, DatasetConfig } from "../api/types";
import { mergeDatasetSchema } from "../lib/datasetSchema";
import { MetadataForm } from "../ui/MetadataForm";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { CrossFilterLinkEditor } from "../builder/CrossFilterLinkEditor";
import { AlertRuleEditor } from "../builder/AlertRuleEditor";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

export function DatasetEditPage({ pk }: { pk: string }) {
  const itemQuery = useItem(pk);
  const configQuery = useDatasetConfig(pk);
  const save = useSaveDataset(pk);
  const updateItem = useUpdateItem(pk);
  const client = useItemClient();
  const navigate = useNavigate();
  const [draft, setDraft] = useState<DatasetConfig | null>(null);
  const [exportError, setExportError] = useState<string | null>(null);
  const [exportingFormat, setExportingFormat] = useState<string | null>(null);

  useEffect(() => {
    if (configQuery.data) setDraft((d) => d ?? configQuery.data);
  }, [configQuery.data]);

  const draftCollectionId = draft && draft.source === "collection" ? draft.collectionId : undefined;
  const schemaQuery = useQuery({
    queryKey: ["collection-schema", draftCollectionId],
    queryFn: () => client.getCollectionSchema(draftCollectionId!),
    enabled: Boolean(draftCollectionId),
  });
  const otherDatasetsQuery = useItems({ type: "dataset", pageSize: 100 });

  if (itemQuery.isLoading || configQuery.isLoading || (!draft && !configQuery.isError))
    return <p role="status">Chargement…</p>;
  if (itemQuery.isError || configQuery.isError || !draft || !itemQuery.data)
    return (
      <p role="alert" className="text-sm text-danger">
        Dataset partagé introuvable.
      </p>
    );

  const item = itemQuery.data;

  function setColumn(name: string, patch: DatasetColumnMeta) {
    setDraft((d) =>
      d ? { ...d, columns: { ...d.columns, [name]: { ...d.columns[name], ...patch } } } : d,
    );
  }

  const targetOptions = (otherDatasetsQuery.data?.items ?? [])
    .filter((d) => d.pk !== pk)
    .map((d) => ({ pk: d.pk, title: d.title }));

  function addCrossFilterLink() {
    setDraft((d) =>
      d
        ? {
            ...d,
            crossFilterLinks: [
              ...(d.crossFilterLinks ?? []),
              { targetDatasetId: "", mode: "attribute" as const, sourceField: "", targetField: "" },
            ],
          }
        : d,
    );
  }
  function updateCrossFilterLink(index: number, next: CrossFilterLink) {
    setDraft((d) => {
      if (!d) return d;
      const links = [...(d.crossFilterLinks ?? [])];
      links[index] = next;
      return { ...d, crossFilterLinks: links };
    });
  }
  function removeCrossFilterLink(index: number) {
    setDraft((d) => {
      if (!d) return d;
      const links = (d.crossFilterLinks ?? []).filter((_, i) => i !== index);
      return { ...d, crossFilterLinks: links };
    });
  }

  const merged = schemaQuery.data ? mergeDatasetSchema(schemaQuery.data, draft.columns) : [];

  const hasGeometry = draft.source === "arcgis" ? true : Boolean(schemaQuery.data?.geometry);
  const exportFormats = hasGeometry ? ["csv", "xlsx", "geojson", "gpkg"] : ["csv", "xlsx"];

  async function handleExport(format: string) {
    const source = {
      id: "__dataset-export__",
      type: "features" as const,
      service: "core",
      layer: "",
      datasetId: pk,
      query: {},
    };
    setExportError(null);
    setExportingFormat(format);
    try {
      const { blob, filename } = await client.exportDataSource(source, format);
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
      URL.revokeObjectURL(url);
    } catch (err) {
      setExportError(err instanceof Error ? err.message : "Échec de l'export.");
    } finally {
      setExportingFormat(null);
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="dataset"
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
              <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs text-ink-2">
                <dt>Type</dt>
                <dd>Dataset</dd>
                <dt>Modifié</dt>
                <dd>{item.date || "—"}</dd>
              </dl>
            </Panel>
          ),
        }}
        work={{
          id: "dataset",
          label: "Dataset",
          content: (
            <div className="flex flex-col gap-4 p-4">
              <h2 className="text-xl font-semibold text-ink">Dataset partagé — {item.title}</h2>
              <MetadataForm
                initial={{
                  title: item.title,
                  abstract: item.abstract,
                  keywords: item.keywords ?? [],
                }}
                onSubmit={(v) => updateItem.mutate(v)}
                onCancel={() => {}}
                pending={updateItem.isPending}
              />
              <div>
                <p className="mb-1 text-xs font-medium text-ink-2">Colonnes</p>
                {schemaQuery.isLoading && <p role="status">Chargement du schéma…</p>}
                {schemaQuery.isError && (
                  <p role="alert" className="text-sm text-danger">
                    Collection source introuvable.
                  </p>
                )}
                {merged.length > 0 && (
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-left text-xs text-ink-2">
                        <th className="p-1">Colonne</th>
                        <th className="p-1">Libellé</th>
                        <th className="p-1">Description</th>
                        <th className="p-1">Format</th>
                      </tr>
                    </thead>
                    <tbody>
                      {merged.map((f) => (
                        <tr key={f.name} className="border-t border-rule">
                          <td className="p-1 font-mono text-xs">{f.name}</td>
                          <td className="p-1">
                            <input
                              aria-label={`Libellé de ${f.name}`}
                              className="h-8 w-full rounded border border-rule bg-surface px-2 text-xs text-ink"
                              value={f.label ?? ""}
                              onChange={(e) => setColumn(f.name, { label: e.target.value })}
                            />
                          </td>
                          <td className="p-1">
                            <input
                              aria-label={`Description de ${f.name}`}
                              className="h-8 w-full rounded border border-rule bg-surface px-2 text-xs text-ink"
                              value={f.description ?? ""}
                              onChange={(e) => setColumn(f.name, { description: e.target.value })}
                            />
                          </td>
                          <td className="p-1">
                            <input
                              aria-label={`Format de ${f.name}`}
                              className="h-8 w-full rounded border border-rule bg-surface px-2 text-xs text-ink"
                              value={f.format ?? ""}
                              onChange={(e) => setColumn(f.name, { format: e.target.value })}
                            />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                <label className="mt-2 flex flex-col gap-1 text-xs">
                  Colonne temporelle
                  <select
                    aria-label="Colonne temporelle"
                    className="h-8 w-full rounded border border-rule bg-surface px-2 text-xs text-ink"
                    value={draft.timeField ?? ""}
                    onChange={(e) =>
                      setDraft((d) => (d ? { ...d, timeField: e.target.value || null } : d))
                    }
                  >
                    <option value="">— aucune —</option>
                    {merged.map((f) => (
                      <option key={f.name} value={f.name}>
                        {f.name}
                      </option>
                    ))}
                  </select>
                </label>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    aria-label="Réagir au déplacement de la carte"
                    checked={Boolean(draft.reactsToExtent)}
                    onChange={(e) =>
                      setDraft((d) => (d ? { ...d, reactsToExtent: e.target.checked } : d))
                    }
                  />
                  Réagir au déplacement de la carte
                </label>
                <div className="mt-2 flex flex-col gap-2">
                  <p className="text-xs font-medium text-ink-2">Liens cross-filter</p>
                  {(draft.crossFilterLinks ?? []).map((link, i) => (
                    <CrossFilterLinkEditor
                      key={i}
                      link={link}
                      sourceFields={merged.map((f) => f.name)}
                      targetOptions={targetOptions}
                      onChange={(next) => updateCrossFilterLink(i, next)}
                      onRemove={() => removeCrossFilterLink(i)}
                    />
                  ))}
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    className="w-fit"
                    onClick={addCrossFilterLink}
                  >
                    Ajouter un lien
                  </Button>
                </div>
              </div>
            </div>
          ),
        }}
        inspect={{
          id: "settings",
          label: "Réglages",
          content: (
            <div className="flex flex-col gap-4 p-3">
              <div className="flex flex-col gap-2">
                <p className="text-xs font-medium text-ink-2">Export</p>
                <div className="flex gap-2">
                  {exportFormats.map((format) => (
                    <button
                      key={format}
                      type="button"
                      aria-label={`Exporter en ${format.toUpperCase()}`}
                      disabled={exportingFormat === format}
                      className="rounded border border-rule px-2 py-1 text-xs text-ink hover:bg-sunken disabled:opacity-50"
                      onClick={() => void handleExport(format)}
                    >
                      {format.toUpperCase()}
                    </button>
                  ))}
                </div>
                {exportError && (
                  <p role="alert" className="text-sm text-danger">
                    {exportError}
                  </p>
                )}
              </div>
              <AlertRuleEditor datasetItemId={pk} owner={item.owner} />
              <ConfigHistoryPanel
                pk={pk}
                currentVersion={null}
                onRestored={async () => setDraft(await client.getDatasetConfig(pk))}
              />
              {draft.sourcePipelineId && (
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="w-fit"
                  onClick={() => navigate(`/datasets/visual-query/${draft.sourcePipelineId}/edit`)}
                >
                  Modifier la requête
                </Button>
              )}
              <Button
                size="sm"
                className="w-fit"
                disabled={save.isPending}
                onClick={() => save.mutate(draft)}
              >
                Enregistrer les colonnes
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

- [ ] **Step 5: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/pages/DatasetEditPage.test.tsx
```

Expected: PASS — les 11 tests existants (aucun ne cherche une structure DOM particulière hors des rôles/labels déjà stables : `getByLabelText`, `getByRole("button", ...)`, `getByRole("alert")`, texte `/Dataset partagé/`) plus le nouveau test des onglets, soit 12 au total.

- [ ] **Step 6: `tsc --noEmit` + build**

```bash
cd shell && npm run build
```

Expected: PASS. Si le build échoue sur une référence résiduelle à `ui/button`/`ui/dialog`/`ui/input` dans un fichier de cette famille, c'est un oubli de Task 1 — corriger avant de continuer, ne pas committer un build rouge.

- [ ] **Step 7: E2E — specs de la famille Données**

```bash
cd shell && npx playwright test datasets-shared.spec.ts dataset-export.spec.ts dataset-arcgis.spec.ts alert-rule.spec.ts visual-query.spec.ts
```

Expected: PASS, sans modification à aucun de ces cinq fichiers `.spec.ts` — ils interagissent par rôle/label, pas par structure de layout, et ne référencent aucun contenu déplacé entre volets par son wrapper DOM.

- [ ] **Step 8: Commit**

```bash
git add shell/src/pages/DatasetEditPage.tsx shell/src/pages/DatasetEditPage.test.tsx
git commit -m "feat(shell): datasetEditPage sur TriptychLayout (Catalogue/Dataset/Réglages)"
```

---

## Task 3: Vérification finale — suite complète + portes de qualité

**Files:** aucun changement de fichier — tâche de vérification uniquement.

- [ ] **Step 1: Suite Vitest complète**

```bash
cd shell && npm run test
```

Expected: PASS, aucune régression sur les fichiers non touchés par ce plan.

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

Expected: PASS — 118 passed / 4 skipped / 0 failed (référence SP-30c) ou mieux (ce plan n'ajoute aucun nouveau spec Playwright, seulement des tests unitaires). Si un total différent apparaît, diagnostiquer contre le fichier `.spec.ts` précis en échec avant de conclure — ne jamais réajuster silencieusement le nombre attendu dans un rapport.

- [ ] **Step 4: Lint + format + contrat de couches**

```bash
cd shell && npm run lint && npm run format:check
cd core && uv run lint-imports
```

Expected: PASS, aucune nouvelle entrée de contrat de couches (aucun changement au cœur dans ce plan).

- [ ] **Step 5: Confirmer l'absence de tout changement côté cœur**

```bash
git status --short core/
```

Expected: aucune sortie — ce plan ne touche pas `core/` (le travail `CollectionPermissions` était déjà livré par SP-30a, cf. note en tête de plan).

- [ ] **Step 6: Recherche exhaustive de couleurs Tailwind en dur résiduelles dans les trois fichiers touchés par ce plan**

```bash
grep -rnE 'text-(red|slate|blue|gray|black|amber)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/AlertRuleEditor.tsx shell/src/builder/CrossFilterLinkEditor.tsx \
  shell/src/pages/DatasetEditPage.tsx
```

Expected: aucune sortie.

- [ ] **Step 7: Recherche exhaustive de `ui/dialog`/`ui/button`/`ui/input`/`ui/card` résiduels dans les trois fichiers touchés**

```bash
grep -rn 'ui/dialog"\|ui/button"\|ui/input"\|ui/card"' \
  shell/src/builder/AlertRuleEditor.tsx shell/src/builder/CrossFilterLinkEditor.tsx \
  shell/src/pages/DatasetEditPage.tsx
```

Expected: aucune sortie.

Ce plan ne se termine pas par un commit propre — c'est une tâche de vérification. Si un des steps échoue, revenir à la tâche responsable (identifiable par le fichier en cause) pour corriger, jamais par un correctif générique en Task 3.
