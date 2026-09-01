# SP-30g — Automatisation, volet 2 (ReportEditPage) sur le socle triptyque Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Basculer `ReportEditPage` (deuxième page de la famille 6
« Automatisation », `docs/superpowers/specs/2026-08-30-sp30-bascule-triptyque-design.md`
§6.1, dans l'ordre où la spec les énumère : PipelineBuilderPage — SP-30f — puis
ReportEditPage puis VisualQueryWizardPage) sur `TriptychLayout` : trois
onglets — « Catalogue » (retour au catalogue + fiche `<dl>` Type/Modifié,
absente tant que le rapport est un brouillon non enregistré), « Rapport »
(titre local + `ReportScheduleEditor`), « Réglages » (`ReportRunPanel` si
`pk !== null`, `ConfigHistoryPanel` si `pk !== null`, Enregistrer + erreur de
sauvegarde).

**Ce que ce plan NE fait PAS** : famille 6 compte trois pages
(`PipelineBuilderPage` — SP-30f, livré — `ReportEditPage` — ce plan —,
`VisualQueryWizardPage`). Comme SP-30f l'annonçait déjà, la granularité reste
une page par plan (comme SP-30c/d/e) : `VisualQueryWizardPage` reste pour un
plan SP-30h séparé. `QueryFilterBuilder.tsx`/`QuerySummaryBuilder.tsx`/
`QueryJoinPicker.tsx` (utilisés par `VisualQueryWizardPage`, importent
encore `ui/button`/`ui/input`) restent hors de ce plan — vérifié : aucun
d'eux n'importe `ReportScheduleEditor` ni `ReportRunPanel`, et
`VisualQueryWizardPage.tsx` consomme directement `PipelineScheduleEditor`/
`PipelineRunPanel` (déjà kit-ifiés par SP-30f), jamais les équivalents
`Report*` — les deux familles de composants ne se recoupent pas, ce plan ne
crée aucune dette pour SP-30h.

**Décisions explicites de ce plan (à ne pas re-débattre en exécution)** :

1. **Aucune maquette de référence pour cette page.** Les huit écrans de
   `docs/design/triptyque-geostudio.html` sont CATALOGUE, CARTE, BUILDER,
   SQL LAB, PIPELINE, TACHES, ADMIN/AUDIT, PARAMETRES (vérifié par grep des
   commentaires `<!-- ... -->` avant d'écrire ce plan) — aucun écran RAPPORT.
   `ReportEditPage` est une page de réglages simple, sans canevas ni panneau
   de liste métier (pas de `LayersPanel`/`PipelinePalette`/`PageManager`
   équivalent) : elle suit donc le patron de `DatasetEditPage` (SP-30d), pas
   celui de `PipelineBuilderPage`/`MapEditorPage` — volet `browse` =
   « Catalogue » (retour + `<dl>`), pas un panneau-liste dédié.
2. **`pk` est nullable ici** (`/reports/new` : brouillon local, même
   justification que `PipelineBuilderPage` SP-15b §2.2, déjà écrite dans le
   commentaire de tête du fichier — préservée telle quelle) — à la différence
   de `DatasetEditPage` où `pk` est toujours défini. Il n'existe donc pas
   toujours un `Item` à afficher dans le volet Catalogue. Décision : le volet
   Catalogue montre **toujours** le lien « ← Retour au catalogue », et la
   `<dl>` Type/Modifié **seulement si `pk !== null`** (rien à afficher avant
   le premier Enregistrer — même logique déjà en place dans ce fichier pour
   `ReportRunPanel`/`ConfigHistoryPanel`, gatés `pk !== null`). Pas de message
   de repli inventé pour l'absence de `<dl>` (piège n°4 : ne pas ajouter de
   fonctionnalité non demandée) — le lien seul suffit.
3. **`useItem` gagne un second paramètre optionnel `{ enabled?: boolean }`**
   (`shell/src/api/hooks.ts`), sur le patron exact déjà en place pour
   `useDatasetConfig`/`useReportScheduleConfig`/`useAppConfig` (toutes trois
   acceptent déjà `options?: { enabled?: boolean }`) — seule `useItem` ne
   l'avait pas encore, parce que ses trois call sites actuels
   (`ItemDetailPage`, `DatasetEditPage`, `AppRuntimePage`) ont toujours un
   `pk` non nul. Rétrocompatible : les trois n'ont besoin d'aucune
   modification (`options` est optionnel, absent = `enabled: true`, le
   comportement actuel). Alternative rejetée : dupliquer un `useQuery`
   `["item", pk]` directement dans `ReportEditPage.tsx` — casserait la source
   unique de la clé de requête déjà partagée par les trois pages existantes.
4. **Le `<dd>Type</dd>` utilise `RESOURCE_TYPE_LABELS[item.resourceType]`**
   (`shell/src/api/resourceTypes.ts`, idiome exact d'`ItemDetailPage.tsx:89`)
   — **pas** un littéral `"Rapport"` en dur. `CLAUDE.md` (suivi non bloquant
   de SP-30d) note que `DatasetEditPage` avait codé `<dd>Dataset</dd>` en dur
   au lieu de cet idiome ; ce plan ne répète pas ce défaut puisqu'il ajoute
   ici, pour la première fois dans cette famille, une vraie requête `useItem`
   dans une page qui n'en avait aucune.
5. **Dette de test `vi.stubGlobal` sans `vi.unstubAllGlobals()` refermée,
   pas répétée.** `ReportEditPage.test.tsx` ne rendait pas encore
   `TriptychLayout` avant ce plan (aucun stub `matchMedia` existant) — ce
   sera le 5ᵉ fichier de cette famille à en avoir besoin
   (`MapEditorPage.test.tsx`, `DatasetEditPage.test.tsx`,
   `AppBuilderPage.test.tsx` : stub sans nettoyage explicite ;
   `PipelineBuilderPage.test.tsx` : déjà nettoyé). Ce plan ajoute
   `afterEach(() => vi.unstubAllGlobals())` dès l'introduction du stub —
   referme la classe de dette plutôt que de l'ajouter une 4ᵉ fois.
6. **Titre local du volet Rapport : `<h2 className="text-lg font-semibold
   text-ink">`**, pas le `<h1 className="text-lg font-medium">` actuel — un
   seul niveau de titre `h1` a du sens par page rendue dans le chrome, et
   `PipelineBuilderPage` (même famille, même forme `pk` nullable) établit déjà
   `<h2 className="text-lg font-semibold text-ink">` comme le patron à suivre
   ici, pas les `text-xl` d'`ItemDetailPage`/`DatasetEditPage` (pages avec un
   `item.title` réel à afficher en grand, absent ici).
7. **`Button` « Enregistrer » gagne `size="sm" className="w-fit"`**, aligné
   sur `DatasetEditPage`/`PipelineBuilderPage` (actuellement taille par
   défaut, seule page de la famille pas encore alignée) — placé en bas du
   volet Réglages, comme les trois familles précédentes (pas de déplacement à
   faire ici : `ReportEditPage` n'avait pas de canevas avec un en-tête
   surchargé, le bouton était déjà hors d'un en-tête de volet de travail).

**Architecture:** `ReportEditPage` s'enveloppe dans
`<div className="-m-6 flex flex-1 flex-col overflow-hidden">` (même
technique de transition locale que les quatre familles précédentes) et
instancie `TriptychLayout` avec `defaultTabId="report"` et trois volets :
**browse** = « Catalogue » (`Panel` avec lien retour + `<dl>` conditionnelle
à `pk !== null`, patron `ItemDetailPage`/`DatasetEditPage`) ; **work** =
« Rapport » (titre local + `ReportScheduleEditor`, dans un conteneur
`overflow-y-auto` propre — le volet `work` de `TriptychLayout` est
`overflow-hidden` par construction, piège déjà documenté par SP-30d/e/f) ;
**inspect** = « Réglages » (`ReportRunPanel` si `pk !== null`,
`ConfigHistoryPanel` si `pk !== null`, puis Enregistrer + erreur).

**Tech Stack:** React 19, `@tanstack/react-query`, react-router-dom, kit de
primitives SP-29b (`shell/src/ui/kit/`), Vitest + Testing Library, Playwright.

## Global Constraints

- Docs et identifiants de test en français ; code/identifiants en anglais (CLAUDE.md).
- Aucune couleur Tailwind en dur (`slate-*`, `red-*`, `blue-*`, `gray-*`,
  `white`, `black`) dans les fichiers touchés : tokens uniquement
  (`bg-surface`, `text-ink`, `text-ink-2`, `border-rule`, `text-danger`,
  `text-accent` — `shell/src/styles/tokens.css`).
- Aucun ancien import `ui/button`/`ui/dialog`/`ui/input`/`ui/card` ne subsiste
  dans les fichiers touchés par ce plan après leur tâche respective.
- `-m-6` est une technique de transition **locale à `ReportEditPage.tsx`
  seule** dans ce plan, jamais un changement à `AppLayout.tsx`.
- Régression jsdom (piège n°10) : `window.matchMedia` n'existe pas sous
  jsdom — `TriptychLayout` l'appelle via `useNarrowViewport`. Stub local à
  `ReportEditPage.test.tsx`, **avec** `afterEach(() => vi.unstubAllGlobals())`
  dès son introduction (cf. décision explicite 5) — jamais dans
  `shell/src/test/setup.ts`.
- Pas de changement au cœur (`core/`) dans ce plan — aucun schéma de
  permissions ni de config concerné (`ReportSchedulePayload` inchangé). Diff
  vide attendu (piège n°1 — vide parce qu'aucun schéma ne change), vérifié en
  Task 5 par `git status --short core/`. Régénération OpenAPI/TS **non
  nécessaire** pour la même raison.
- E2E : suite **complète** exigée avant tout commit qui change la structure
  DOM de la page (Task 4, Task 5) — pas de liste de specs nommée dans ce
  plan (recommandation actée par SP-30e/f après trois occurrences
  consécutives du piège n°6).

---

## Task 1: Cœur shell — `useItem` gagne `options?: { enabled?: boolean }`

**Files:**
- Modify: `shell/src/api/hooks.ts`
- Test: `shell/src/api/hooks.test.tsx`

**Interfaces:**
- Consumes: rien de nouveau — patron déjà établi par `useDatasetConfig`
  (`shell/src/api/hooks.ts:259-266`).
- Produces: `useItem(pk: string, options?: { enabled?: boolean })` — les
  trois call sites existants (`ItemDetailPage.tsx:28`,
  `DatasetEditPage.tsx:18`, `AppRuntimePage.tsx:26`) n'appellent `useItem`
  qu'avec un seul argument : aucun changement requis chez eux, `options`
  optionnel se résout à `enabled: true` par défaut, comportement identique
  à aujourd'hui.

- [ ] **Step 1: Écrire le test qui échoue**

Dans `shell/src/api/hooks.test.tsx`, ajouter `useItem` à la liste d'imports
existante (ordre alphabétique, avant `useItems`) :

```tsx
import {
  useAppConfig,
  useCandidateTables,
  useCollectionSharing,
  useCollectionsAdmin,
  useCreateBookmark,
  useCreateHarvestSource,
  useCreateItem,
  useCreateMap,
  useDeleteItem,
  useGroups,
  useHarvestSources,
  useInstanceInfo,
  useItem,
  useItems,
  useMapConfig,
  useMe,
  useRunHarvestSource,
  useSaveApp,
  useSaveMap,
  useSharing,
  useUpdateItem,
} from "./hooks";
```

Ajouter, en fin de fichier :

```tsx
test("useItem: enabled false ne déclenche aucune requête", () => {
  // Aucun handler MSW enregistré pour GET /items/x : si enabled n'est pas
  // câblé, la requête réelle échouerait bruyamment (onUnhandledRequest:
  // "error", shell/src/test/setup.ts) — mais on la détecte plus tôt, de
  // façon synchrone, via fetchStatus : "fetching" démarre immédiatement si
  // la requête part, "idle" si elle est bien désactivée.
  const { result } = renderHook(() => useItem("x", { enabled: false }), { wrapper });
  expect(result.current.fetchStatus).toBe("idle");
  expect(result.current.data).toBeUndefined();
});
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

```bash
cd shell && npx vitest run src/api/hooks.test.tsx -t "useItem: enabled false"
```

Expected: FAIL — `result.current.fetchStatus` vaut `"fetching"` (la
signature actuelle de `useItem` ignore le second argument, la requête part
quand même).

- [ ] **Step 3: Implémenter**

Remplacer, dans `shell/src/api/hooks.ts` :
```ts
export function useItem(pk: string) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["item", pk],
    queryFn: () => client.getItem(pk),
  });
}
```
par :
```ts
export function useItem(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["item", pk],
    queryFn: () => client.getItem(pk),
    enabled: options?.enabled ?? true,
  });
}
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

```bash
cd shell && npx vitest run src/api/hooks.test.tsx
```

Expected: PASS — le nouveau test, plus tous les tests existants de ce
fichier (aucun des trois call sites actuels ne passe `options`, donc leur
comportement est inchangé).

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/hooks.ts shell/src/api/hooks.test.tsx
git commit -m "feat(shell): useItem — options.enabled optionnel"
```

---

## Task 2: Shell — kit-ifier `ReportRunPanel.tsx` (tokens)

**Files:**
- Modify: `shell/src/builder/report/ReportRunPanel.tsx`
- Test: `shell/src/builder/report/ReportRunPanel.test.tsx` (baseline, doit passer sans modification)

**Interfaces:**
- Consumes: aucun composant du kit — contrôles natifs uniquement, déjà
  vérifié (aucun import `ui/*` dans ce fichier).
- Produces: aucune API publique changée — `ReportRunPanel({ reportId })`
  inchangée, consommée telle quelle par Task 4.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/builder/report/ReportRunPanel.test.tsx
```

Expected: PASS (4 tests, aucune modification prévue à ce fichier de test).

- [ ] **Step 2: Tokeniser les cinq couleurs en dur**

Remplacer (ligne 71, erreur de chargement) :
```tsx
        <p role="alert" className="text-sm text-red-600">
```
par :
```tsx
        <p role="alert" className="text-sm text-danger">
```

Remplacer (ligne 76, état vide) :
```tsx
        <p className="text-sm text-slate-500">Aucune exécution pour l'instant.</p>
```
par :
```tsx
        <p className="text-sm text-ink-2">Aucune exécution pour l'instant.</p>
```

Remplacer (ligne 82, horodatage) :
```tsx
            <span className="text-slate-400">{new Date(run.createdAt).toLocaleString()}</span>
```
par :
```tsx
            <span className="text-ink-2">{new Date(run.createdAt).toLocaleString()}</span>
```

Remplacer (ligne 86, lien de téléchargement) :
```tsx
                className="text-blue-600 underline"
```
par :
```tsx
                className="text-accent underline"
```

Remplacer (ligne 93, erreur d'une exécution) :
```tsx
            {run.error && <span className="text-red-600">{run.error}</span>}
```
par :
```tsx
            {run.error && <span className="text-danger">{run.error}</span>}
```

- [ ] **Step 3: Vérifier qu'aucune couleur Tailwind en dur ne subsiste**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/report/ReportRunPanel.tsx
```

Expected: aucune sortie.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/report/ReportRunPanel.test.tsx
```

Expected: PASS, sans modification au fichier de test.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/report/ReportRunPanel.tsx
git commit -m "feat(shell): reportRunPanel — tokens"
```

---

## Task 3: Shell — kit-ifier `ReportScheduleEditor.tsx` (tokens)

**Files:**
- Modify: `shell/src/builder/report/ReportScheduleEditor.tsx`

**Interfaces:**
- Consumes: `PipelineScheduleEditor` (import relatif inchangé, déjà kit-ifié
  par SP-30f — aucune modification à ce composant).
- Produces: aucune API publique changée — `ReportScheduleEditor({ value,
  onChange, bookmarkLabel })` inchangée, consommée telle quelle par Task 4.

Aucun test dédié n'existe pour ce composant (son comportement est couvert
indirectement par `shell/src/pages/ReportEditPage.test.tsx`, étendu en
Task 4) — la baseline de cette tâche est donc la suite `ReportEditPage`
**avant** que Task 4 ne la modifie.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/pages/ReportEditPage.test.tsx
```

Expected: PASS (2 tests — état d'avant Task 4).

- [ ] **Step 2: Tokeniser les cinq couleurs en dur**

Remplacer (ligne 28, libellé « Vue ciblée ») :
```tsx
      <p className="text-sm text-slate-600">
```
par :
```tsx
      <p className="text-sm text-ink-2">
```

Remplacer (ligne 35, `<select>` de canal) :
```tsx
          className="rounded border border-slate-300 px-2 py-1"
```
par :
```tsx
          className="rounded border border-rule bg-surface px-2 py-1 text-ink"
```

Remplacer (ligne 51, `<input>` URL webhook) :
```tsx
            className="rounded border border-slate-300 px-2 py-1"
```
par :
```tsx
            className="rounded border border-rule bg-surface px-2 py-1 text-ink"
```

Remplacer (ligne 63, `<input>` destinataire e-mail) :
```tsx
              className="rounded border border-slate-300 px-2 py-1"
```
par :
```tsx
              className="rounded border border-rule bg-surface px-2 py-1 text-ink"
```

Remplacer (ligne 77, `<input>` secret SMTP) :
```tsx
              className="rounded border border-slate-300 px-2 py-1"
```
par :
```tsx
              className="rounded border border-rule bg-surface px-2 py-1 text-ink"
```

- [ ] **Step 3: Vérifier qu'aucune couleur Tailwind en dur ne subsiste**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/report/ReportScheduleEditor.tsx
```

Expected: aucune sortie.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/pages/ReportEditPage.test.tsx
```

Expected: PASS, sans modification à `ReportEditPage.test.tsx` (cette tâche
ne touche que des classes CSS, aucune assertion de test ne porte dessus).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/report/ReportScheduleEditor.tsx
git commit -m "feat(shell): reportScheduleEditor — tokens"
```

---

## Task 4: Shell — `ReportEditPage` sur `TriptychLayout` (« Catalogue / Rapport / Réglages »)

**Files:**
- Modify: `shell/src/pages/ReportEditPage.tsx`
- Modify: `shell/src/pages/ReportEditPage.test.tsx`

**Interfaces:**
- Consumes: `TriptychLayout` (`shell/src/shell/chrome/TriptychLayout.tsx`,
  `{browse,work,inspect,defaultTabId}` — SP-30a) ; `useItem` (Task 1,
  `{enabled}`) ; `RESOURCE_TYPE_LABELS` (`shell/src/api/resourceTypes.ts`) ;
  `Panel`/`Button` du kit ; `ReportScheduleEditor`/`ReportRunPanel` (Tasks
  2-3, API inchangées) ; `ConfigHistoryPanel` (déjà kit-ifié depuis SP-30c).
- Produces: `ReportEditPage({ pk, initialBookmarkItemId })` — API publique
  inchangée, aucune route dans `shell/src/shell/routes.tsx` ne change.

Cf. « Décisions explicites de ce plan » en tête de document pour la
justification des sept choix structurants.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/pages/ReportEditPage.test.tsx
```

Expected: PASS (2 tests).

- [ ] **Step 2: Réécrire `ReportEditPage.test.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Item, ItemClient, ReportSchedulePayload } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { OWNER_PERMISSIONS } from "../auth/permissions";
import { ReportEditPage } from "./ReportEditPage";

// ReportEditPage calls useAuth() for `username` on create — same mock as
// PipelineBuilderPage.test.tsx, needed because the real hook calls
// react-oidc-context's useAuth(), which throws without an AuthProvider.
vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({
    isLoading: false,
    isAuthenticated: true,
    username: "alice",
    getAccessToken: () => "t",
    signIn: vi.fn(),
    signOut: vi.fn(),
    error: null,
  }),
}));

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. ReportEditPage ne rendait pas
// TriptychLayout avant ce plan, donc ce stub est nouveau dans ce fichier —
// stub local, jamais dans shell/src/test/setup.ts. matches: false => le
// layout "large" (3 volets simultanés), pas les onglets — la valeur par
// défaut de tous les tests de ce fichier qui n'affirment pas sur la
// largeur. vi.unstubAllGlobals() en afterEach dès l'introduction du stub
// (contrairement à MapEditorPage.test.tsx/DatasetEditPage.test.tsx/
// AppBuilderPage.test.tsx, qui ne l'ont pas — dette non répétée ici).
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
afterEach(() => vi.unstubAllGlobals());

const item: Item = {
  pk: "r-1",
  resourceType: "report",
  title: "Rapport planifié",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-08-31",
  configId: "cfg-r1",
  isPublished: false,
  keywords: [],
  permissions: OWNER_PERMISSIONS,
};

function renderPage(pk: string | null, overrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    getReportRuns: vi.fn().mockResolvedValue([]),
    ...overrides,
  };
  render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ItemClientProvider client={client as ItemClient}>
          <ReportEditPage pk={pk} initialBookmarkItemId="bm-1" />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return { client };
}

test("persisted mode: affiche le panneau d'historique et la fiche Catalogue", async () => {
  const payload: ReportSchedulePayload = {
    bookmarkItemId: "bm-1",
    refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
    channels: [{ kind: "webhook", url: "" }],
  };
  renderPage("r-1", {
    getItem: vi.fn().mockResolvedValue(item),
    getReportScheduleConfig: () => Promise.resolve(payload),
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByText("Historique")).toBeInTheDocument();
  expect(await screen.findByText("Rapport")).toBeInTheDocument();
  expect(screen.getByText("2026-08-31")).toBeInTheDocument();
});

test("unsaved mode: no history panel before the first save (no report id yet)", async () => {
  renderPage(null);
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Programmer un rapport" })).toBeInTheDocument(),
  );
  expect(screen.queryByText("Historique")).not.toBeInTheDocument();
});

test("unsaved mode: le volet Catalogue ne montre aucune fiche d'item avant le premier Enregistrer", async () => {
  renderPage(null);
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Programmer un rapport" })).toBeInTheDocument(),
  );
  expect(screen.getByRole("link", { name: "← Retour au catalogue" })).toBeInTheDocument();
  expect(screen.queryByText("Type")).not.toBeInTheDocument();
});

test("sous viewport étroit, affiche trois onglets Catalogue/Rapport/Réglages avec Rapport actif par défaut", async () => {
  stubMatchMedia(true);
  renderPage(null);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Rapport", "Réglages"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Rapport");
});
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec des trois nouveaux/modifiés (le test « unsaved mode: no history » doit encore passer)**

```bash
cd shell && npx vitest run src/pages/ReportEditPage.test.tsx
```

Expected : « persisted mode: affiche le panneau d'historique et la fiche
Catalogue » FAIL (pas de `<dl>`, `screen.getByText("2026-08-31")` introuvable) ;
« unsaved mode: le volet Catalogue… » FAIL (le lien « ← Retour au catalogue »
n'existe pas encore) ; « sous viewport étroit… » FAIL (aucun `role="tab"`) ;
« unsaved mode: no history panel… » **PASS** (comportement déjà correct
aujourd'hui, inchangé par ce plan).

- [ ] **Step 4: Réécrire `ReportEditPage.tsx`**

```tsx
// shell/src/pages/ReportEditPage.tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  useCreateReportSchedule,
  useItem,
  useReportScheduleConfig,
  useSaveReportSchedule,
} from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import { useItemClient } from "../api/ItemClientProvider";
import type { ReportSchedulePayload } from "../api/types";
import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { ReportScheduleEditor } from "../builder/report/ReportScheduleEditor";
import { ReportRunPanel } from "../builder/report/ReportRunPanel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

function defaultPayload(bookmarkItemId: string): ReportSchedulePayload {
  return {
    bookmarkItemId,
    refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
    channels: [{ kind: "webhook", url: "" }],
  };
}

// pk === null : brouillon local (/reports/new) — reproduit exactement la
// séparation création/édition à pk nullable de PipelineBuilderPage (la
// justification de SP-15b §2.2 s'applique ici mot pour mot : rien n'est
// persisté avant le premier « Enregistrer »).
export function ReportEditPage({
  pk,
  initialBookmarkItemId,
}: {
  pk: string | null;
  initialBookmarkItemId?: string;
}) {
  const navigate = useNavigate();
  const { username } = useAuth();
  const client = useItemClient();
  const itemQuery = useItem(pk ?? "", { enabled: pk !== null });
  const configQuery = useReportScheduleConfig(pk ?? "", { enabled: pk !== null });
  const createReport = useCreateReportSchedule();
  const saveReport = useSaveReportSchedule(pk ?? "");

  const [draft, setDraft] = useState<ReportSchedulePayload>(
    defaultPayload(initialBookmarkItemId ?? ""),
  );
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (pk !== null && configQuery.data) setDraft(configQuery.data);
  }, [pk, configQuery.data]);

  if (pk !== null && configQuery.isLoading) return <p role="status">Chargement…</p>;

  async function onSave() {
    setSaveError(null);
    try {
      if (pk === null) {
        const item = await createReport.mutateAsync({
          title: "Rapport planifié",
          owner: username ?? "",
          report: draft,
        });
        navigate(`/reports/${item.pk}/edit`, { replace: true });
        return;
      }
      await saveReport.mutateAsync(draft);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Échec de l'enregistrement.");
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="report"
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
              {itemQuery.data && (
                <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs text-ink-2">
                  <dt>Type</dt>
                  <dd>{RESOURCE_TYPE_LABELS[itemQuery.data.resourceType]}</dd>
                  <dt>Modifié</dt>
                  <dd>{itemQuery.data.date || "—"}</dd>
                </dl>
              )}
            </Panel>
          ),
        }}
        work={{
          id: "report",
          label: "Rapport",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h2 className="text-lg font-semibold text-ink">
                {pk === null ? "Programmer un rapport" : "Modifier le rapport planifié"}
              </h2>
              <ReportScheduleEditor
                value={draft}
                onChange={setDraft}
                bookmarkLabel={draft.bookmarkItemId}
              />
            </div>
          ),
        }}
        inspect={{
          id: "settings",
          label: "Réglages",
          content: (
            <div className="flex flex-col gap-4 p-3">
              {pk !== null && <ReportRunPanel reportId={pk} />}
              {pk !== null && (
                <ConfigHistoryPanel
                  pk={pk}
                  currentVersion={null}
                  onRestored={async () => setDraft(await client.getReportScheduleConfig(pk))}
                />
              )}
              <div className="flex flex-col gap-2 border-t border-rule pt-3">
                <Button
                  size="sm"
                  className="w-fit"
                  onClick={() => void onSave()}
                  disabled={createReport.isPending || saveReport.isPending}
                >
                  Enregistrer
                </Button>
                {saveError && (
                  <p role="alert" className="text-sm text-danger">
                    {saveError}
                  </p>
                )}
              </div>
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
cd shell && npx vitest run src/pages/ReportEditPage.test.tsx
```

Expected: PASS — les 4 tests (2 existants + 2 nouveaux).

- [ ] **Step 6: `tsc --noEmit` + build**

```bash
cd shell && npm run build
```

Expected: PASS. Si le build échoue sur une référence résiduelle à
`ui/button`/`ui/dialog`/`ui/input` dans un fichier de cette famille, c'est un
oubli de Task 1-3 — corriger avant de continuer, ne pas committer un build rouge.

- [ ] **Step 7: E2E — suite complète**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed (référence SP-30f) ou
mieux. `shell/e2e/report-schedule.spec.ts` est le spec directement concerné
(navigue vers `/reports/new`, remplit « URL du webhook », clique
« Enregistrer », vérifie « Terminé »/« Télécharger » après redirection vers
`/reports/report-1/edit`) — sous viewport large (défaut Playwright), les
trois volets de `TriptychLayout` sont rendus simultanément, donc aucune
navigation d'onglet n'est nécessaire pour que ces assertions restent
valides. Si un total différent apparaît, diagnostiquer contre le fichier
`.spec.ts` précis en échec avant de conclure — ne jamais réajuster
silencieusement le nombre attendu dans un rapport (piège n°6).

- [ ] **Step 8: Commit**

```bash
git add shell/src/pages/ReportEditPage.tsx shell/src/pages/ReportEditPage.test.tsx
git commit -m "feat(shell): reportEditPage sur TriptychLayout (Catalogue/Rapport/Réglages)"
```

---

## Task 5: Vérification finale — suite complète + portes de qualité

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

Expected: seuil 88 respecté (piège documenté quatre fois : nettoyer
`dist/`/`dist-export/` avant de mesurer).

- [ ] **Step 3: Suite E2E complète (seconde exécution, après tous les commits de ce plan)**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed, ou mieux.

- [ ] **Step 4: Lint + format + contrat de couches**

```bash
cd shell && npm run lint && npm run format:check
cd core && uv run lint-imports
```

Expected: PASS, aucune nouvelle entrée de contrat de couches (aucun
changement au cœur dans ce plan).

- [ ] **Step 5: Confirmer l'absence de tout changement côté cœur**

```bash
git status --short core/
```

Expected: aucune sortie — ce plan ne touche pas `core/`.

- [ ] **Step 6: Recherche exhaustive de couleurs Tailwind en dur résiduelles dans les quatre fichiers touchés par ce plan**

```bash
grep -rnE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/report/ReportRunPanel.tsx shell/src/builder/report/ReportScheduleEditor.tsx \
  shell/src/pages/ReportEditPage.tsx shell/src/api/hooks.ts
```

Expected: aucune sortie.

- [ ] **Step 7: Recherche exhaustive de `ui/dialog`/`ui/button`/`ui/input`/`ui/card` résiduels dans les fichiers touchés**

```bash
grep -rn 'ui/dialog"\|ui/button"\|ui/input"\|ui/card"' \
  shell/src/builder/report/ReportRunPanel.tsx shell/src/builder/report/ReportScheduleEditor.tsx \
  shell/src/pages/ReportEditPage.tsx
```

Expected: aucune sortie.

Ce plan ne se termine pas par un commit propre — c'est une tâche de
vérification. Si un des steps échoue, revenir à la tâche responsable
(identifiable par le fichier en cause) pour corriger, jamais par un
correctif générique en Task 5.
