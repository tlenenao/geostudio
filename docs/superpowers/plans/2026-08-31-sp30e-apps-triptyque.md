# SP-30e — Apps & sites sur le socle triptyque (AppBuilderPage) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Basculer la famille **Apps & sites** (`docs/superpowers/specs/2026-08-30-sp30-bascule-triptyque-design.md` §6.1, famille 5) sur `TriptychLayout` : `AppBuilderPage`, avec trois onglets — « Structure » (palette de widgets + gestion des pages), « Canevas » (barre d'outils d'édition + `AppRenderer`), « Propriétés » (propriétés du widget sélectionné + tout le reste : sources de données, actions, navigation, interactions, variables, thème, impression, export standalone, historique, copilote, Enregistrer).

**Ce que ce plan NE fait PAS** : les familles 6 à 8 du §6.1 (`PipelineBuilderPage`/`ReportEditPage`/`VisualQueryWizardPage`, `SqlLabPage`, `AdminExtensionsPage`/`CollectionsAdminPage`/`HarvestSourcesAdminPage`) restent dans des plans SP-30f+ séparés. Également hors de ce plan : les panneaux enfants qui n'importent ni `ui/dialog` ni `ui/button` (`WidgetPalette.tsx`, `PageManager.tsx`, `DataSourcePanel.tsx`, `ActionsPanel.tsx`, `NavigationPanel.tsx`, `VariablesPanel.tsx`, `ThemePanel.tsx`, `PropsPanel.tsx` — 22 occurrences de couleurs Tailwind en dur cumulées, vérifiées par grep en préparation de ce plan, aucune ne bloque la bascule de `AppBuilderPage` elle-même) — dette de tokens reportée en suivi non bloquant, même traitement que la dette des éditeurs de symbologie laissée par SP-30c ; `AppRuntimePage`/`SitePublicPage` (hors périmètre SP-30, §2.2 de la spec) ; `LayoutEditor.tsx` et les widgets conteneurs (`drawer.tsx`/`modal.tsx`/`tabs.tsx`) qui l'utilisent — partagés avec le runtime d'app (`AppRuntimePage`), pas exclusifs à `AppBuilderPage`, donc hors de la règle de kit-ification par famille ; la suppression définitive de `ui/dialog.tsx`/`ui/button.tsx` (encore utilisés par les familles 6 à 8, non retirés avant la dernière famille bascule).

**Décisions explicites de ce plan (à ne pas re-débattre en exécution)** :

1. **L'inspecteur ne se scinde pas en « propriétés du widget sélectionné » / « réglages de l'app » comme le suggère la maquette** (`docs/design/triptyque-geostudio.html` lignes 559-637, note de bas de mock : « quand rien n'est sélectionné — l'inspecteur affiche l'app elle-même »). La suite de tests unitaires existante (21 tests, `AppBuilderPage.test.tsx`) exige `ActionsPanel` et `DataSourcePanel` accessibles **alors qu'un widget est sélectionné** — ex. le test « composes an action between two widgets » (lignes 90-121) clique deux fois sur la palette (chaque clic sélectionne le widget ajouté) puis interagit immédiatement avec `getByLabelText("Widget émetteur")` d'`ActionsPanel`, sans jamais désélectionner. Réécrire ce comportement en un inspecteur conditionnel serait un changement de UX plus large que « faire tenir l'écran existant dans trois volets » (piège n°4 : ne pas mélanger bascule de layout et changement de comportement dans le même plan). L'onglet **Propriétés** empile donc, toujours, dans cet ordre : `PropsPanel` (widget sélectionné, ou son propre message « Aucun widget sélectionné » sinon — comportement déjà existant, inchangé), puis Sources de données, Actions, Navigation, Interactions, Variables, Thème, Impression, Historique, Export standalone (si activé), Copilote (si activé), Enregistrer.
2. **Le mode « Aperçu » ne masque plus les volets Structure/Propriétés.** Le chrome actuel masque les deux `<aside>` quand `mode === "preview"` pour donner un aperçu plein cadre. Le socle triptyque garde ses trois volets en permanence sur viewport large (c'est le principe même du chrome, cf. maquette BUILDER qui montre le sélecteur Édition/Aperçu **à l'intérieur** d'un layout à trois volets déjà fixe). Aucun test, unitaire ou E2E, ne clique jamais sur le bouton « Aperçu » puis n'interroge la présence/absence des volets (vérifié par grep sur `AppBuilderPage.test.tsx` et sur `e2e/*.spec.ts` avant d'écrire ce plan) — le mode continue de changer le comportement de `AppRenderer` (désactive la sélection/l'édition sur le canevas) via la prop `mode` déjà threadée, seule la disparition visuelle des volets latéraux est abandonnée.
3. **Annuler/Rétablir restent une commande locale au volet Canevas**, pas remontés dans `StatusBar` malgré la maquette (ligne 634 : `<div class="statusbar">Annuler ⌘Z · Rétablir ⇧⌘Z…`). La spec SP-30 §2.1.3 réserve explicitement `StatusBar` à « version + tenant seulement » dans ce SP — l'étendre pour une seule famille créerait une surface que SP-31 (résumé de tâches dans la barre d'état) redessinerait de toute façon. Annuler/Rétablir/sélecteur de rupture/Édition-Aperçu/Capturer une miniature forment l'en-tête local du volet **Canevas**, à la manière du `<h2>` local que `DatasetEditPage` (SP-30d) place dans son volet « Dataset ».

**Architecture:** `AppBuilderPage` s'enveloppe dans `<div className="-m-6 flex flex-1 flex-col overflow-hidden">` (même technique de transition locale que les quatre familles précédentes) et instancie `TriptychLayout` avec trois volets : **browse** = « Structure » (gestion des pages puis palette de widgets — reprend l'ordre de la maquette BUILDER, Pages avant Widgets) ; **work** = « Canevas » (en-tête local : Édition/Aperçu, Annuler/Rétablir, sélecteur de rupture, Capturer une miniature + son message d'erreur ; puis `<main>` défilant contenant `AppRenderer` — le volet `work` de `TriptychLayout` est `overflow-hidden` par construction, donc ce plan fournit explicitement son propre conteneur de défilement autour d'`AppRenderer`, piège documenté par la revue finale de SP-30d) ; **inspect** = « Propriétés » (cf. décision explicite n°1 ci-dessus, empilement complet se terminant par Enregistrer + bannières d'erreur). `AppExportPanel` (Dialog→panneau en ligne, seul composant de cette famille qui importe encore `ui/dialog`) et `CopilotPanel` (import `ui/button` seul) sont kit-ifiés en amont, Task 1 et 2, avant la bascule de la page elle-même — même séquencement que SP-30d (kit-ifier les enfants exclusifs d'abord, basculer la page ensuite).

**Tech Stack:** React 19, `@tanstack/react-query`, react-router-dom, kit de primitives SP-29b (`shell/src/ui/kit/`), Vitest + Testing Library, Playwright.

## Global Constraints

- Docs et identifiants de test en français ; code/identifiants en anglais (CLAUDE.md).
- Aucune couleur Tailwind en dur (`slate-*`, `red-*`, `blue-*`, `amber-*`, `white`, `black`) dans les fichiers touchés par ce plan : tokens uniquement (`bg-surface`, `text-ink`, `text-ink-2`, `text-ink-3`, `border-rule`, `bg-raised`, `bg-sunken`, `text-danger`, `text-accent`, `text-warn`, `border-warn-soft`, `bg-warn-soft` — `shell/src/styles/tokens.css`).
- Aucun `<Dialog>` (ancien `ui/dialog.tsx` ou `ui/kit/Dialog`) n'apparaît dans les trois fichiers touchés par ce plan **après** Task 1 (avant Task 1, `AppExportPanel.tsx` en importe un — c'est précisément ce que Task 1 retire, même patron que `ExportPanel`/`Terrain3DUploadButton` en SP-30c : panneau en ligne, bouton déclencheur désactivé pendant l'envoi — busy guard vérifié explicitement, piège n°10/finding de revue finale SP-30c où l'un des deux convertis avait oublié cette garde).
- `-m-6` est une technique de transition **locale à `AppBuilderPage.tsx` seule** dans ce plan, jamais un changement à `AppLayout.tsx`.
- Régressions jsdom (piège n°10) : `window.matchMedia` n'existe pas sous jsdom — `TriptychLayout` l'appelle via `useNarrowViewport`. `AppBuilderPage.tsx` ne rendait pas `TriptychLayout` avant ce plan, donc `AppBuilderPage.test.tsx` n'a **jamais** stubé `matchMedia` : Task 3 l'introduit pour la première fois dans ce fichier, stub local (jamais dans `shell/src/test/setup.ts`), copié du patron exact de `MapEditorPage.test.tsx`/`DatasetEditPage.test.tsx` (`matches: false` par défaut).
- Pas de changement au cœur (`core/`) dans ce plan — famille Apps & sites, aucun schéma de permissions concerné. Diff vide attendu (piège n°1 — vide parce qu'aucun schéma ne change), vérifié en Task 4 par `git status --short core/`.
- E2E : `shell/e2e/app-builder.spec.ts`, `copilot.spec.ts`, `responsive.spec.ts`, `publication.spec.ts`, `config-history.spec.ts` sont le filet de non-régression comportementale de cette famille (les cinq seuls specs qui naviguent vers `/apps/:pk/edit`, vérifié par grep sur `e2e/*.spec.ts` avant d'écrire ce plan — `static-export.spec.ts`/`connected-export.spec.ts`/`containers.spec.ts` exercent l'app exportée ou `/apps/:pk` en exécution, pas l'écran d'édition) et doivent rester verts **sans modification de leur texte** (Task 3) : ils interagissent par rôle/label, aucun ne dépend de la structure DOM du layout ni d'un ordre visuel entre panneaux.
- Aucun test, unitaire ou E2E, n'exerce l'ouverture du panneau de choix de mode d'`AppExportPanel` (« Choisir le mode d'export ») — vérifié par grep sur `AppExportPanel.test.tsx` (5 tests, tous par `getByRole("button", ...)`) et sur `e2e/*.spec.ts` avant d'écrire ce plan. La conversion Dialog→panneau de Task 1 ne touche donc aucun test existant, à la différence de SP-30c où le filet E2E avait dû être corrigé après coup pour deux composants similaires (piège n°6) — vérifié à nouveau en Task 4.

---

## Task 1: Shell — kit-ifier `AppExportPanel` (Dialog → panneau en ligne, Button, tokens)

**Files:**
- Modify: `shell/src/builder/appexport/AppExportPanel.tsx`
- Test: `shell/src/builder/appexport/AppExportPanel.test.tsx` (baseline, doit passer sans modification)

**Interfaces:**
- Consumes: `Button`/`Panel` de `shell/src/ui/kit/` (mêmes signatures que dans `shell/src/builder/print/ExportPanel.tsx`, SP-30c).
- Produces: aucune API publique changée — `AppExportPanel({ itemId, config })` inchangée, consommée telle quelle par Task 3.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx
```

Expected: PASS (5 tests).

- [ ] **Step 2: Réécrire `AppExportPanel.tsx`**

Remplacer le fichier entier par :

```tsx
// SPDX-License-Identifier: Apache-2.0
// Même patron de poll que shell/src/builder/print/ExportPanel.tsx (SP-17a) :
// boucle récursive manuelle via le client, jamais un refetchInterval
// react-query — cf. plan Global Constraints (superpowers writing-plans).
// Même patron de panneau en ligne qu'ExportPanel/Terrain3DUploadButton
// (SP-30c) : pas de fenêtre modale, bouton déclencheur désactivé pendant
// l'envoi (busy guard — SP-30c a trouvé cette garde absente sur l'un des
// deux composants convertis, revue finale de branche, fix vérifié depuis).
import { useEffect, useRef, useState } from "react";
import { useItemClient } from "../../api/ItemClientProvider";
import type { AppConfig, AppExportJobStatus, AppExportMode } from "../../api/types";
import { Button } from "../../ui/kit/Button";
import { Panel } from "../../ui/kit/Panel";
import { collectWidgetTypes, WRITE_CAPABLE_WIDGET_TYPES } from "./collectWidgetTypes";

const POLL_INTERVAL_MS = 1500;
const MAX_POLL_ATTEMPTS = 200;

export function AppExportPanel({ itemId, config }: { itemId: string; config: AppConfig }) {
  const client = useItemClient();
  const [pickerOpen, setPickerOpen] = useState(false);
  const [job, setJob] = useState<AppExportJobStatus | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [pendingWarningMode, setPendingWarningMode] = useState<AppExportMode | null>(null);
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
    const latest = await client.getAppExportJob(itemId, jobId);
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

  async function runExport(mode: AppExportMode) {
    setPendingWarningMode(null);
    setPickerOpen(false);
    setRunning(true);
    setError(null);
    setJob(null);
    try {
      const { jobId } = await client.createAppExport(itemId, mode);
      await poll(jobId);
    } catch {
      if (mountedRef.current) setError("Échec de l'export.");
    } finally {
      if (mountedRef.current) setRunning(false);
    }
  }

  // Le choix de mode ne déclenche l'export réel que si la config ne
  // contient aucun widget d'écriture (formulaire) — sinon on bloque sur un
  // avertissement explicite, franchissable seulement par un second clic
  // conscient ("Exporter quand même").
  function onChooseMode(mode: AppExportMode) {
    const hasWriteWidget = [...collectWidgetTypes(config)].some((t) =>
      WRITE_CAPABLE_WIDGET_TYPES.has(t),
    );
    if (hasWriteWidget) {
      setPickerOpen(false);
      setPendingWarningMode(mode);
      return;
    }
    void runExport(mode);
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
          <p className="text-sm font-medium text-ink">Choisir le mode d'export</p>
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setPickerOpen(false)}>
              Annuler
            </Button>
            <Button type="button" size="sm" onClick={() => onChooseMode("static")}>
              Statique
            </Button>
            <Button type="button" size="sm" onClick={() => onChooseMode("connected")}>
              Connecté
            </Button>
            <Button type="button" size="sm" onClick={() => onChooseMode("standalone")}>
              Autoporté
            </Button>
          </div>
        </Panel>
      )}
      {pendingWarningMode && (
        <div
          role="alert"
          className="rounded border border-warn-soft bg-warn-soft p-2 text-sm text-warn"
        >
          <p>
            Cette app contient un widget Formulaire — toute écriture sera désactivée dans
            l&apos;export faute de session authentifiée.
          </p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" onClick={() => void runExport(pendingWarningMode)}>
              Exporter quand même
            </Button>
            <Button size="sm" variant="outline" onClick={() => setPendingWarningMode(null)}>
              Annuler
            </Button>
          </div>
        </div>
      )}
      {job?.status === "done" && job.resultUrl && (
        <a href={job.resultUrl} download className="text-sm text-accent underline">
          Télécharger le bundle
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

- [ ] **Step 3: Vérifier qu'aucune couleur Tailwind en dur, ancien import ou `Dialog` ne subsiste**

```bash
grep -nE 'text-(red|slate|blue|gray|black|amber)-[0-9]+|bg-(white|black|slate|gray|amber)(/[0-9]+)?|border-(slate|gray|amber)-[0-9]+' \
  shell/src/builder/appexport/AppExportPanel.tsx
grep -n 'ui/dialog"\|ui/button"\|ui/input"\|ui/card"' shell/src/builder/appexport/AppExportPanel.tsx
```

Expected: aucune sortie pour les deux commandes.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/appexport/AppExportPanel.test.tsx
```

Expected: PASS (5 tests, sans aucune modification au fichier de test — les 5 tests interagissent uniquement par `getByRole("button", ...)`/`getByRole("link", ...)`, jamais par `getByRole("dialog")`).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/appexport/AppExportPanel.tsx
git commit -m "feat(shell): appExportPanel — panneau en ligne + kit Button + tokens"
```

---

## Task 2: Shell — kit-ifier `CopilotPanel` (Button, tokens)

**Files:**
- Modify: `shell/src/builder/copilot/CopilotPanel.tsx`
- Test: `shell/src/builder/copilot/CopilotPanel.test.tsx` (baseline, doit passer sans modification)

**Interfaces:**
- Consumes: `Button` de `shell/src/ui/kit/Button.tsx`.
- Produces: aucune API publique changée — `CopilotPanel({ itemId, config, activePageId, setDraft })` inchangée, consommée telle quelle par Task 3.

`CopilotPanel` n'importe pas `ui/dialog` — seul le `Button` et quatre couleurs Tailwind en dur à tokeniser.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/builder/copilot/CopilotPanel.test.tsx
```

Expected: PASS (4 tests).

- [ ] **Step 2: `CopilotPanel.tsx` — import Button du kit**

Remplacer :
```tsx
import { Button } from "../../ui/button";
```
par :
```tsx
import { Button } from "../../ui/kit/Button";
```

- [ ] **Step 3: Tokeniser les quatre couleurs en dur**

Remplacer :
```tsx
          <p key={i} className={m.role === "user" ? "font-medium" : "text-slate-600"}>
```
par :
```tsx
          <p key={i} className={m.role === "user" ? "font-medium" : "text-ink-2"}>
```

Remplacer :
```tsx
          className="min-h-16 rounded-md border border-slate-300 p-2 text-sm"
```
par :
```tsx
          className="min-h-16 rounded-md border border-rule bg-surface p-2 text-sm text-ink"
```

Remplacer :
```tsx
        <ul className="text-xs text-slate-500">
```
par :
```tsx
        <ul className="text-xs text-ink-2">
```

Remplacer :
```tsx
        <p role="alert" className="text-xs text-red-600">
```
par :
```tsx
        <p role="alert" className="text-xs text-danger">
```

- [ ] **Step 4: Vérifier qu'aucune couleur Tailwind en dur ni ancien import ne subsiste**

```bash
grep -nE 'text-(red|slate|blue|gray|black|amber)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/copilot/CopilotPanel.tsx
grep -n 'ui/dialog"\|ui/button"\|ui/input"\|ui/card"' shell/src/builder/copilot/CopilotPanel.tsx
```

Expected: aucune sortie pour les deux commandes.

- [ ] **Step 5: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/copilot/CopilotPanel.test.tsx
```

Expected: PASS (4 tests, sans modification au fichier de test).

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/copilot/CopilotPanel.tsx
git commit -m "feat(shell): copilotPanel — kit Button + tokens"
```

---

## Task 3: Shell — `AppBuilderPage` sur `TriptychLayout` (« Structure / Canevas / Propriétés »)

**Files:**
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Modify: `shell/src/pages/AppBuilderPage.test.tsx`

**Interfaces:**
- Consumes: `TriptychLayout` (`shell/src/shell/chrome/TriptychLayout.tsx`, `{browse,work,inspect,defaultTabId}` — SP-30a) ; `Button` du kit ; `AppExportPanel`/`CopilotPanel` (Task 1/2, API inchangées) ; `ConfigHistoryPanel`/`PrintLayoutPanel` (déjà kit-ifiés depuis SP-30c) ; `ActionsPanel`/`NavigationPanel`/`DataSourcePanel`/`PageManager`/`WidgetPalette`/`PropsPanel`/`ThemePanel`/`VariablesPanel` (API inchangées, non modifiés par ce plan — cf. « Ce que ce plan NE fait PAS »).
- Produces: `AppBuilderPage({ pk: string })` — API publique inchangée, `AppBuilderRoute` dans `shell/src/shell/routes.tsx` ne change pas.

Cf. « Décisions explicites de ce plan » en tête de document pour la justification des trois choix structurants (inspecteur non conditionnel, Aperçu ne masque plus les volets, Annuler/Rétablir restent locaux au volet Canevas).

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx
```

Expected: PASS (21 tests).

- [ ] **Step 2: Ajouter le stub `matchMedia` et le test de dégradation en onglets**

Dans `shell/src/pages/AppBuilderPage.test.tsx`, remplacer la ligne d'import vitest :
```tsx
import { expect, test, vi } from "vitest";
```
par :
```tsx
import { beforeEach, expect, test, vi } from "vitest";
```

Ajouter, juste après la déclaration de `config` (`const config: AppConfig = { ... };`) et avant `function renderPage(...)` :

```tsx
// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. AppBuilderPage ne rendait pas
// TriptychLayout avant ce plan, donc ce stub est nouveau dans ce fichier —
// stub local, jamais dans shell/src/test/setup.ts. matches: false => le
// layout "large" (3 volets simultanés), pas les onglets — la valeur par
// défaut de tous les tests existants de ce fichier, qui n'affirment pas
// sur la largeur.
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
test("sous viewport étroit, affiche trois onglets Structure/Canevas/Propriétés avec Canevas actif par défaut", async () => {
  stubMatchMedia(true);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config) });
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Structure", "Canevas", "Propriétés"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Canevas");
});
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec du nouveau test (les 21 existants doivent encore passer)**

```bash
cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx
```

Expected: le nouveau test « sous viewport étroit… » FAIL (`AppBuilderPage` ne rend encore aucun `role="tab"`) ; les 21 tests existants PASS (le stub `matchMedia(false)` du `beforeEach` ne change le comportement d'aucun d'eux tant que `AppBuilderPage` ne consomme pas encore `useNarrowViewport`).

- [ ] **Step 4: Réécrire `AppBuilderPage.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useMemo, useRef, useState } from "react";
import { useUndoableDraft } from "../builder/useUndoableDraft";
import { toBlob } from "html-to-image";
import {
  useAppConfig,
  useCreateDataset,
  useInstanceInfo,
  useSaveApp,
  useUploadThumbnail,
} from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { PrintLayoutConfig, RenderMode, WidgetItem } from "../api/types";
import { ActionsPanel } from "../builder/ActionsPanel";
import { AppExportPanel } from "../builder/appexport/AppExportPanel";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { CopilotPanel } from "../builder/copilot/CopilotPanel";
import { PrintLayoutPanel } from "../builder/print/PrintLayoutPanel";
import { AppRenderer } from "../builder/AppRenderer";
import { NavigationPanel } from "../builder/NavigationPanel";
import { DataSourcePanel } from "../builder/DataSourcePanel";
import { DataSourcesEditProvider } from "../builder/DataSourcesEditContext";
import { PageManager } from "../builder/PageManager";
import { WidgetPalette } from "../builder/WidgetPalette";
import { PropsPanel } from "../builder/PropsPanel";
import { ThemePanel } from "../builder/ThemePanel";
import { VariablesPanel } from "../builder/VariablesPanel";
import { registerBuiltinWidgets } from "../builder/widgets";
import { registerCounterExampleWidget } from "../builder/examples/counterWidget";
import { registerCounterWcExampleWidget } from "../builder/examples/counterWidgetWc";
import { useActiveExtensions } from "../api/hooks";
import { registerExtensionWidget } from "../builder/extensions/registerExtensionWidget";
import { getWidget } from "../builder/registry";
import { BREAKPOINTS, nextFreePosition, type Breakpoint } from "../builder/grid";
import { getPages, getPageLayout, setPageLayout } from "../builder/pages";
import { getConfigExpressionErrors } from "../builder/configExpressionErrors";
import { Button } from "../ui/kit/Button";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { useAuth } from "../auth/useAuth";

registerBuiltinWidgets();
registerCounterExampleWidget();
registerCounterWcExampleWidget();

export function AppBuilderPage({ pk }: { pk: string }) {
  const client = useItemClient();
  const query = useAppConfig(pk);
  const save = useSaveApp(pk);
  const thumbnail = useUploadThumbnail(pk);
  const instanceQuery = useInstanceInfo();
  const appExportEnabled = instanceQuery.data?.appExportEnabled === true;
  const copilotEnabled = instanceQuery.data?.copilotEnabled === true;
  const { username } = useAuth();
  const createDataset = useCreateDataset();
  const [promotingId, setPromotingId] = useState<string | null>(null);
  const mainRef = useRef<HTMLElement>(null);
  const { draft, setDraft, seedDraft, resetDraft, undo, redo, canUndo, canRedo } =
    useUndoableDraft();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<RenderMode>("edit");
  const [breakpoint, setBreakpoint] = useState<Breakpoint>("lg");
  const [activePageId, setActivePageId] = useState<string | null>(null);

  const extensionsQuery = useActiveExtensions();
  const [extensionsRegistered, setExtensionsRegistered] = useState(false);

  useEffect(() => {
    if (extensionsQuery.isLoading) return;
    (extensionsQuery.data ?? []).forEach(registerExtensionWidget);
    setExtensionsRegistered(true);
    // Se déclenche une fois les données arrivées OU en erreur (fail-open :
    // un /extensions en échec ne doit pas rendre le builder inutilisable) —
    // jamais tant que isLoading est vrai.
  }, [extensionsQuery.isLoading, extensionsQuery.data]);

  useEffect(() => {
    // Seed the draft once on first load. Re-seeding on every query.data change
    // (e.g. the refetch after a save) would clobber in-flight local edits.
    // seedDraft (not setDraft) — this is the session's starting point, not
    // an edit, and must not create an undo step (SP-19).
    if (query.data) seedDraft(query.data);
  }, [query.data, seedDraft]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = document.activeElement;
      const isTextField =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        (target instanceof HTMLElement && target.isContentEditable);
      if (isTextField) return;
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [undo, redo]);

  const pages = useMemo(() => (draft ? getPages(draft) : []), [draft]);
  // Validate activePageId against the current draft's pages rather than
  // trusting it blindly: undoing a page addition (Ctrl+Z) reverts `draft`
  // but `activePageId` is a plain useState, not part of the undo stack, so
  // it keeps pointing at a page that no longer exists. setPageLayout()
  // silently no-ops for an unknown pageId (see builder/pages.ts), so every
  // edit made while activePageId is stale was previously a silent no-op —
  // SP-19 final-branch-review fix pass, finding C2.
  const activePage =
    activePageId && pages.some((p) => p.id === activePageId)
      ? activePageId
      : (pages[0]?.id ?? null);
  const activeLayout = useMemo(
    () => (draft && activePage ? getPageLayout(draft, activePage) : null),
    [draft, activePage],
  );

  const selected = useMemo(
    () => activeLayout?.items.find((i) => i.id === selectedId) ?? null,
    [activeLayout, selectedId],
  );

  // Same class of bug as C2 above, for the other piece of state that lives
  // outside the undo stack: undoing a widget addition leaves `selectedId`
  // pointing at a removed item. `selected` above already resolves to null
  // in that case, but the stale id itself should not linger indefinitely —
  // reconcile it explicitly once the item it points to stops existing in
  // the active layout (SP-19 final-branch-review fix pass, finding M2).
  useEffect(() => {
    if (selectedId && activeLayout && !activeLayout.items.some((i) => i.id === selectedId)) {
      setSelectedId(null);
    }
  }, [selectedId, activeLayout]);

  if (query.isLoading || !extensionsRegistered || (!draft && !query.isError))
    return <p role="status">Chargement…</p>;
  if (query.isError || !draft || !activeLayout || !activePage)
    return (
      <p role="alert" className="text-sm text-danger">
        Application introuvable.
      </p>
    );

  function addWidget(type: string) {
    const def = getWidget(type);
    if (!def || !activePage) return;
    const id = crypto.randomUUID();
    // Functional updater (like setSources/setMessages/… below): a plain
    // `setDraft(newValue)` here would read the `draft` closed over at render
    // time, silently dropping any other setDraft call batched in the same
    // event (e.g. DataSourceSelect's onAdd via DataSourcesEditContext when a
    // newly-added widget is bound to a shared dataset in the same handler).
    setDraft((d) => {
      if (!d) return d;
      const layout = getPageLayout(d, activePage);
      const { x, y } = nextFreePosition(layout.items);
      const item: WidgetItem = {
        id,
        widget: type,
        x,
        y,
        w: def.defaultSize.w,
        h: def.defaultSize.h,
        props: { ...def.defaultProps },
      };
      return setPageLayout(d, activePage, { ...layout, items: [...layout.items, item] });
    });
    setSelectedId(id);
  }

  async function captureThumbnail() {
    if (!mainRef.current) return;
    const blob = await toBlob(mainRef.current);
    if (!blob) return;
    const file = new File([blob], "thumbnail.png", { type: "image/png" });
    try {
      await thumbnail.mutateAsync(file);
    } catch {
      /* surfaced via thumbnail.isError */
    }
  }

  function updateSelectedProps(props: Record<string, unknown>) {
    if (!selectedId || !activePage) return;
    // Functional updater — see addWidget's comment: DataSourceSelect fires
    // this (via PropsPanel's onChange) right after DataSourcesEditContext's
    // onAdd in the same handler when binding a new shared dataset, so both
    // setDraft calls land in one React batch.
    setDraft((d) => {
      if (!d) return d;
      const layout = getPageLayout(d, activePage);
      return setPageLayout(d, activePage, {
        ...layout,
        items: layout.items.map((i) => (i.id === selectedId ? { ...i, props } : i)),
      });
    });
  }

  function updateSelectedVisibleWhen(expr: string) {
    if (!selectedId || !activePage) return;
    setDraft((d) => {
      if (!d) return d;
      const layout = getPageLayout(d, activePage);
      return setPageLayout(d, activePage, {
        ...layout,
        items: layout.items.map((i) =>
          i.id === selectedId ? { ...i, visibleWhen: expr || undefined } : i,
        ),
      });
    });
  }

  const setSources = (dataSources: typeof draft.dataSources) =>
    setDraft((d) => (d ? { ...d, dataSources } : d));

  async function promoteSource(id: string) {
    if (!draft) return;
    const source = draft.dataSources.find((s) => s.id === id);
    if (!source || !source.layer) return;
    setPromotingId(id);
    try {
      const item = await createDataset.mutateAsync({
        title: source.layer,
        owner: username ?? "",
        source: "collection",
        collectionId: source.layer,
      });
      setSources(draft.dataSources.map((s) => (s.id === id ? { ...s, datasetId: item.pk } : s)));
    } catch {
      /* surfaced via createDataset.isError */
    } finally {
      setPromotingId(null);
    }
  }

  const setMessages = (messages: typeof draft.messages) =>
    setDraft((d) => (d ? { ...d, messages } : d));

  const setTheme = (theme: typeof draft.theme) => setDraft((d) => (d ? { ...d, theme } : d));

  const setPages = (nextPages: typeof pages) =>
    setDraft((d) => (d ? { ...d, pages: nextPages, layout: nextPages[0]?.layout ?? d.layout } : d));

  const setNavigationMode = (navigationMode: "tabs" | "story") =>
    setDraft((d) => (d ? { ...d, navigationMode } : d));

  const setInteractions = (interactions: "auto" | "manual") =>
    setDraft((d) => (d ? { ...d, interactions } : d));

  const setActivePageOnEnter = (updated: (typeof pages)[number]) =>
    setDraft((d) =>
      d ? { ...d, pages: getPages(d).map((p) => (p.id === updated.id ? updated : p)) } : d,
    );

  const setVariables = (variables: typeof draft.variables) =>
    setDraft((d) => (d ? { ...d, variables } : d));

  function setPrintLayout(printLayout: PrintLayoutConfig | null) {
    setDraft((d) => (d ? { ...d, printLayout } : d));
  }

  const expressionErrors = draft ? getConfigExpressionErrors(draft) : [];

  return (
    <DataSourcesEditProvider onAdd={(source) => setSources([...draft.dataSources, source])}>
      <div className="-m-6 flex flex-1 flex-col overflow-hidden">
        <TriptychLayout
          defaultTabId="canvas"
          browse={{
            id: "structure",
            label: "Structure",
            content: (
              <div className="flex flex-col gap-1 p-2">
                <p className="mb-1 text-xs font-medium text-ink-2">Pages</p>
                <PageManager
                  pages={pages}
                  activePageId={activePage}
                  onChange={setPages}
                  onSelectPage={setActivePageId}
                />
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Widgets</p>
                <WidgetPalette onAdd={addWidget} />
              </div>
            ),
          }}
          work={{
            id: "canvas",
            label: "Canevas",
            content: (
              <div className="flex h-full flex-col overflow-hidden">
                <div className="flex flex-wrap items-center gap-2 border-b border-rule p-2">
                  <Button
                    size="sm"
                    variant={mode === "edit" ? "default" : "outline"}
                    onClick={() => setMode("edit")}
                  >
                    Édition
                  </Button>
                  <Button
                    size="sm"
                    variant={mode === "preview" ? "default" : "outline"}
                    onClick={() => setMode("preview")}
                  >
                    Aperçu
                  </Button>
                  <div className="ml-2 flex items-center gap-1">
                    <Button size="sm" variant="outline" disabled={!canUndo} onClick={undo}>
                      Annuler
                    </Button>
                    <Button size="sm" variant="outline" disabled={!canRedo} onClick={redo}>
                      Rétablir
                    </Button>
                  </div>
                  <div className="ml-2 flex items-center gap-1">
                    {BREAKPOINTS.map((bp) => (
                      <Button
                        key={bp}
                        size="sm"
                        variant={breakpoint === bp ? "default" : "outline"}
                        aria-label={`Éditer en ${bp}`}
                        onClick={() => setBreakpoint(bp)}
                      >
                        {bp}
                      </Button>
                    ))}
                  </div>
                  <div className="flex-1" />
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={thumbnail.isPending}
                    onClick={() => void captureThumbnail()}
                  >
                    Capturer une miniature
                  </Button>
                  {thumbnail.isError && (
                    <span role="alert" className="text-sm text-danger">
                      Échec de la capture.
                    </span>
                  )}
                </div>
                <main ref={mainRef} className="flex-1 overflow-auto p-2">
                  <AppRenderer
                    config={draft}
                    mode={mode}
                    onChange={setDraft}
                    selectedId={selectedId}
                    onSelect={setSelectedId}
                    breakpoint={breakpoint}
                    pageId={activePage}
                    onNavigate={setActivePageId}
                  />
                </main>
              </div>
            ),
          }}
          inspect={{
            id: "props",
            label: "Propriétés",
            content: (
              <div className="flex flex-col gap-1 p-2">
                <p className="mb-1 text-xs font-medium text-ink-2">Propriétés</p>
                <PropsPanel
                  item={selected}
                  dataSources={draft.dataSources}
                  theme={draft.theme}
                  onChange={updateSelectedProps}
                  onVisibleWhenChange={updateSelectedVisibleWhen}
                />
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Sources de données</p>
                <DataSourcePanel
                  sources={draft.dataSources}
                  onChange={setSources}
                  onPromote={(id) => void promoteSource(id)}
                  promotingId={promotingId}
                />
                {createDataset.isError && (
                  <p role="alert" className="text-xs text-danger">
                    Échec de la promotion.
                  </p>
                )}
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Actions</p>
                <ActionsPanel
                  items={activeLayout.items}
                  variables={draft.variables ?? []}
                  messages={draft.messages}
                  onChange={setMessages}
                />
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Navigation</p>
                <NavigationPanel
                  navigationMode={draft.navigationMode ?? "tabs"}
                  onNavigationModeChange={setNavigationMode}
                  page={pages.find((p) => p.id === activePage) ?? pages[0]}
                  onPageChange={setActivePageOnEnter}
                />
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Interactions</p>
                <label className="flex items-center gap-2 text-xs">
                  <input
                    type="checkbox"
                    aria-label="Interactions automatiques (cross-filter)"
                    checked={draft.interactions === "auto"}
                    onChange={(e) => setInteractions(e.target.checked ? "auto" : "manual")}
                  />
                  Interactions automatiques (cross-filter)
                </label>
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Variables</p>
                <VariablesPanel variables={draft.variables ?? []} onChange={setVariables} />
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Thème</p>
                <ThemePanel theme={draft.theme} onChange={setTheme} />
                <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Impression</p>
                <PrintLayoutPanel value={draft.printLayout ?? null} onChange={setPrintLayout} />
                <div className="mt-3">
                  <ConfigHistoryPanel
                    pk={pk}
                    currentVersion={null}
                    onRestored={async () => {
                      const restored = await client.getAppConfig(pk);
                      // resetDraft, pas setDraft : la pile undo ne peut pas défaire
                      // une écriture serveur (cf. useUndoableDraft.resetDraft).
                      resetDraft(restored);
                    }}
                  />
                </div>
                {appExportEnabled && (
                  <>
                    <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Export standalone</p>
                    <AppExportPanel itemId={pk} config={draft} />
                  </>
                )}
                {copilotEnabled && (
                  <>
                    <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Copilote</p>
                    <CopilotPanel
                      itemId={pk}
                      config={draft}
                      activePageId={activePage}
                      setDraft={setDraft}
                    />
                  </>
                )}
                <div className="mt-3 flex flex-col gap-2 border-t border-rule pt-3">
                  <Button
                    size="sm"
                    className="w-fit"
                    disabled={save.isPending || expressionErrors.length > 0}
                    onClick={() => save.mutate(draft)}
                  >
                    Enregistrer
                  </Button>
                  {expressionErrors.length > 0 && (
                    <span
                      role="alert"
                      aria-label="Erreur de condition d'affichage"
                      className="text-sm text-danger"
                    >
                      {expressionErrors[0]}
                    </span>
                  )}
                  {save.isError && (
                    <span role="alert" className="text-sm text-danger">
                      Échec de l'enregistrement.
                    </span>
                  )}
                </div>
              </div>
            ),
          }}
        />
      </div>
    </DataSourcesEditProvider>
  );
}
```

- [ ] **Step 5: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx
```

Expected: PASS — les 21 tests existants (aucun ne cherche une structure DOM particulière hors des rôles/labels déjà stables) plus le nouveau test des onglets, soit 22 au total.

- [ ] **Step 6: `tsc --noEmit` + build**

```bash
cd shell && npm run build
```

Expected: PASS. Si le build échoue sur une référence résiduelle à `ui/button`/`ui/dialog`/`ui/input` dans un fichier de cette famille, c'est un oubli de Task 1/2 — corriger avant de continuer, ne pas committer un build rouge.

- [ ] **Step 7: E2E — specs de la famille Apps & sites**

```bash
cd shell && npx playwright test app-builder.spec.ts copilot.spec.ts responsive.spec.ts publication.spec.ts config-history.spec.ts
```

Expected: PASS, sans modification à aucun de ces cinq fichiers `.spec.ts` — ils interagissent par rôle/label, pas par structure de layout.

- [ ] **Step 8: Commit**

```bash
git add shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
git commit -m "feat(shell): appBuilderPage sur TriptychLayout (Structure/Canevas/Propriétés)"
```

---

## Task 4: Vérification finale — suite complète + portes de qualité

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

Expected: PASS — 118 passed / 4 skipped / 0 failed (référence SP-30d) ou mieux (ce plan n'ajoute aucun nouveau spec Playwright, seulement des tests unitaires). Si un total différent apparaît, diagnostiquer contre le fichier `.spec.ts` précis en échec avant de conclure — ne jamais réajuster silencieusement le nombre attendu dans un rapport.

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

Expected: aucune sortie — ce plan ne touche pas `core/`.

- [ ] **Step 6: Recherche exhaustive de couleurs Tailwind en dur résiduelles dans les trois fichiers touchés par ce plan**

```bash
grep -rnE 'text-(red|slate|blue|gray|black|amber)-[0-9]+|bg-(white|black|slate|gray|amber)(/[0-9]+)?|border-(slate|gray|amber)-[0-9]+' \
  shell/src/builder/appexport/AppExportPanel.tsx shell/src/builder/copilot/CopilotPanel.tsx \
  shell/src/pages/AppBuilderPage.tsx
```

Expected: aucune sortie.

- [ ] **Step 7: Recherche exhaustive de `ui/dialog`/`ui/button`/`ui/input`/`ui/card` résiduels dans les trois fichiers touchés**

```bash
grep -rn 'ui/dialog"\|ui/button"\|ui/input"\|ui/card"' \
  shell/src/builder/appexport/AppExportPanel.tsx shell/src/builder/copilot/CopilotPanel.tsx \
  shell/src/pages/AppBuilderPage.tsx
```

Expected: aucune sortie.

- [ ] **Step 8: Confirmer qu'aucun `role="dialog"` ne subsiste dans les trois fichiers touchés**

```bash
grep -rn 'role="dialog"\|getByRole("dialog"' \
  shell/src/builder/appexport/AppExportPanel.tsx shell/src/builder/copilot/CopilotPanel.tsx \
  shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
```

Expected: aucune sortie.

Ce plan ne se termine pas par un commit propre — c'est une tâche de vérification. Si un des steps échoue, revenir à la tâche responsable (identifiable par le fichier en cause) pour corriger, jamais par un correctif générique en Task 4.
