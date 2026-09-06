# SP-52 — App Builder : UX d'édition Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer les 5 manques d'UX du builder d'App documentés par
`docs/superpowers/specs/2026-09-05-sp52-app-builder-ux-design.md` (GAP-33,
GAP-54, GAP-51, GAP-66 a/b/c, GAP-13), sans toucher au cœur ni à
`itemClient.ts`.

**Architecture:** Aucune tâche n'a de dépendance dure sur une autre — sauf
Task 2 (fonction pure de purge des câblages orphelins), consommée par
Task 3 (suppression de widget) et Task 4 (suppression de variable). Ordre
retenu : du moins invasif au plus invasif (identique à la spec §4), avec
Task 2 déplacée juste avant Task 3 pour que le filet existe avant son
premier consommateur.

**Tech Stack:** React 19, Vitest + `@testing-library/react`, Playwright
(`shell/e2e/*.spec.ts`) — aucune nouvelle dépendance.

## Global Constraints

- Chaque tâche suit TDD (test qui échoue → implémentation minimale → test
  qui passe → commit), conformément à `CLAUDE.md`.
- Chaque interaction visible a sa spec E2E Playwright dédiée (règle du
  dépôt) — pas seulement des tests Vitest.
- Commits conventionnels français (`feat(shell): …`, `fix(shell): …`,
  `test(e2e): …`, `refactor(shell): …`), un sujet par commit.
- **`onRemoveItem` (pas `onDeleteItem`) et `handleRemove` (pas
  `handleDelete`)** — noms retenus par la spec (§3.2), à respecter tels
  quels pour rester cohérent avec le vocabulaire déjà choisi (`removeWidget`
  côté copilote, `remove()` déjà utilisé par `VariablesPanel`/
  `ActionsPanel`/`DataSourcePanel`).
- **Prop `onRemoveItem` de `GridCanvas` est obligatoire, jamais optionnelle**
  (spec §3.2) : force une erreur de compilation sur tout site oublié plutôt
  qu'un défaut silencieux. Ne pas lui donner de valeur par défaut.
- À la fin de chaque tâche qui touche plusieurs fichiers (Task 3, Task 8) :
  `cd shell && npx tsc --noEmit` doit passer avant de considérer la tâche
  close — c'est le filet de complétude pour Task 3 (prop obligatoire) ;
  Task 8 n'a pas ce filet (prop optionnelle, cf. spec §4) donc un grep de
  clôture explicite le remplace (Step dédié).
- Lancer la suite Vitest complète (`npm run test`) et la suite Playwright
  complète (`npm run e2e`) une fois à la toute fin du plan (Task 9),
  conformément à `CLAUDE.md` (piège n°6 : régressions cross-tâches trouvées
  seulement à la première exécution complète).

---

## File structure

**Create:**
- `shell/src/builder/actionMessages.ts` + `.test.ts` (Task 2)
- `shell/src/builder/widgets/variableInput.tsx` + `.test.tsx` (Task 8)
- `shell/e2e/app-builder-delete-widget.spec.ts` (Task 3)
- `shell/e2e/variables.spec.ts` — étendu, pas créé (Task 4)
- `shell/e2e/app-builder-static-source.spec.ts` (Task 6)
- `shell/e2e/variable-input-widget.spec.ts` (Task 8)

**Modify:**
- `shell/src/builder/grid.ts`, `grid.test.ts` (Task 1)
- `shell/src/builder/GridCanvas.tsx`, `.test.tsx` (Task 3)
- `shell/src/builder/LayoutEditor.tsx` (Task 3, Task 8)
- `shell/src/builder/AppRenderer.tsx` (Task 3)
- `shell/src/builder/widgets/tabs.tsx` (Task 3, Task 5, Task 8)
- `shell/src/builder/widgets/modal.tsx`, `drawer.tsx` (Task 3, Task 8)
- `shell/src/pages/AppBuilderPage.tsx`, `.test.tsx` (Task 3, Task 4)
- `shell/src/builder/copilot/applyClientOp.ts`, `.test.ts` (Task 6→ non, voir
  Task 6 réel ci-dessous)
- `shell/src/builder/copilot/clientTools.ts` (Task 6)
- `shell/src/builder/DataSourcePanel.tsx`, `.test.tsx` (Task 7)
- `shell/src/builder/VariablesContext.tsx` (Task 8)
- `shell/src/builder/registry.ts` (Task 8)
- `shell/src/builder/PropsPanel.tsx` (Task 8)
- `shell/src/builder/sdk.ts` (Task 8)
- `shell/src/builder/widgets/index.tsx` (Task 8)

(Le nommage `Task 6→` ci-dessus est une note de rédaction — ignorer ; le
détail réel de chaque tâche est ci-dessous, la numérotation finale est celle
des titres `### Task N`.)

---

### Task 1: GAP-33 — retrait du code mort de `grid.ts`

**Files:**
- Modify: `shell/src/builder/grid.ts`
- Modify: `shell/src/builder/grid.test.ts`

**Interfaces:** aucune — retrait pur, aucun consommateur externe.

- [ ] **Step 1: Confirmer l'absence d'appelant (filet avant suppression)**

Run: `grep -rn "resizeItem\|\bmoveItem\b\|styleFor(" shell/src --include=*.ts --include=*.tsx`
Expected: seuls `grid.ts` (déclarations) et `grid.test.ts` (leurs 3 tests,
lignes 8-24) apparaissent. Si un autre fichier apparaît, **arrêter cette
tâche** et investiguer avant de continuer (le code ne serait alors pas
mort).

- [ ] **Step 2: Retirer les 3 fonctions**

Dans `shell/src/builder/grid.ts`, retirer (lignes 7-24 au moment de
l'audit — revérifier les numéros de ligne réels avant de couper, ce fichier
a pu bouger) :
```ts
export function moveItem(item: WidgetItem, dxCells: number, dyCells: number): WidgetItem { ... }
export function resizeItem(item: WidgetItem, dwCells: number, dhCells: number): WidgetItem { ... }
export function styleFor(item: WidgetItem): CSSProperties {
  return {
    gridColumn: `${item.x + 1} / span ${item.w}`,
    gridRow: `${item.y + 1} / span ${item.h}`,
  };
}
```
`GRID_COLS` reste (toujours consommé par `GridCanvas.tsx`).
Si l'import `CSSProperties` devient inutilisé après ce retrait (il sert
aussi au type de retour de `styleForPos`, donc probablement encore utilisé
— vérifier avant de le retirer), ajuster l'import en conséquence.

- [ ] **Step 3: Retirer les 3 tests devenus orphelins**

Dans `shell/src/builder/grid.test.ts`, retirer les 3 `test(...)` qui
appellent `moveItem`/`resizeItem`/`styleFor` ainsi que l'import de ces 3
noms et la constante locale `base` qui ne sert qu'à eux — **vérifier
d'abord qu'aucun test plus bas dans le même fichier ne réutilise `base`**
avant de la retirer (les tests `posFor`/`moveItemAt` plus bas utilisent leur
propre `baseItem`, distinct — à confirmer par lecture, pas par supposition).

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/grid.test.ts`
Expected: PASS, 3 tests de moins qu'avant.

- [ ] **Step 5: Typecheck**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS — confirme qu'aucun fichier n'importait les 3 noms retirés.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/grid.ts shell/src/builder/grid.test.ts
git commit -m "refactor(shell): retire moveItem/resizeItem/styleFor, supersédés par les variantes breakpoint-aware (GAP-33)"
```

---

### Task 2: fonction pure partagée de purge des câblages orphelins

**Files:**
- Create: `shell/src/builder/actionMessages.ts`
- Create: `shell/src/builder/actionMessages.test.ts`

**Interfaces:**
- Produces: `pruneMessagesForIds(messages: ActionMessage[], removedIds: string[]): ActionMessage[]`
- Consumed by: Task 3 (`AppRenderer.tsx::handleRemove`, ids nus) et Task 4
  (`AppBuilderPage.tsx::setVariables`, ids `var:<id>`).

Cette tâche est posée **avant** Task 3/4 exprès (spec, note ajoutée en
§3.2/§3.4) : sans elle, Task 3 écrirait la suppression de widget sans
purge de messages, puis Task 4 réintroduirait le correctif seulement pour
les variables — exactement la classe de défaut « croisement entre tâches
d'un même plan » que `CLAUDE.md` (piège n°4) documente déjà.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/actionMessages.test.ts`:
```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import type { ActionMessage } from "../api/types";
import { pruneMessagesForIds } from "./actionMessages";

function msg(over: Partial<ActionMessage>): ActionMessage {
  return { id: "m1", from: "w1", event: "clicked", to: "w2", action: "reset", ...over };
}

test("removes a message whose `from` references a removed id", () => {
  const messages = [msg({ id: "m1", from: "w1" })];
  expect(pruneMessagesForIds(messages, ["w1"])).toEqual([]);
});

test("removes a message whose `to` references a removed id", () => {
  const messages = [msg({ id: "m1", to: "w2" })];
  expect(pruneMessagesForIds(messages, ["w2"])).toEqual([]);
});

test("keeps a message that references none of the removed ids", () => {
  const messages = [msg({ id: "m1", from: "w1", to: "w2" })];
  expect(pruneMessagesForIds(messages, ["w3"])).toEqual(messages);
});

test("works with the var: prefix used for variable receivers", () => {
  const messages = [msg({ id: "m1", from: "w1", to: "var:v1" })];
  expect(pruneMessagesForIds(messages, ["var:v1"])).toEqual([]);
});

test("an empty removedIds list is a no-op (identity, not a copy)", () => {
  const messages = [msg({ id: "m1" })];
  expect(pruneMessagesForIds(messages, [])).toBe(messages);
});

test("removing several ids at once prunes every affected message", () => {
  const messages = [
    msg({ id: "m1", from: "w1", to: "w2" }),
    msg({ id: "m2", from: "w3", to: "w4" }),
    msg({ id: "m3", from: "w5", to: "w6" }),
  ];
  expect(pruneMessagesForIds(messages, ["w2", "w5"]).map((m) => m.id)).toEqual(["m2"]);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/actionMessages.test.ts`
Expected: FAIL — `Cannot find module './actionMessages'`.

- [ ] **Step 3: Implement**

Create `shell/src/builder/actionMessages.ts`:
```ts
// SPDX-License-Identifier: Apache-2.0
// Retire tout ActionMessage dont from/to référence l'un des ids retirés —
// évite qu'un câblage ActionsPanel orphelin reste indéfiniment dans
// config.messages, invisible (ActionsPanel.resolvesOnThisPage le filtre
// déjà de l'affichage) mais jamais purgé, donc impossible à retirer depuis
// l'UI (GAP-66c). Un id nu identifie un widget retiré ; un id "var:<id>"
// identifie une variable retirée — même fonction pour les deux, appelée
// par AppRenderer.handleRemove (widget) et AppBuilderPage.setVariables
// (variable), pour ne jamais écrire ce filtrage à deux endroits légèrement
// différents (CLAUDE.md, piège n°4).
import type { ActionMessage } from "../api/types";

export function pruneMessagesForIds(
  messages: ActionMessage[],
  removedIds: string[],
): ActionMessage[] {
  if (removedIds.length === 0) return messages;
  const removed = new Set(removedIds);
  return messages.filter((m) => !removed.has(m.from) && !removed.has(m.to));
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/actionMessages.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/actionMessages.ts shell/src/builder/actionMessages.test.ts
git commit -m "feat(shell): pruneMessagesForIds — purge partagée des câblages orphelins (SP-52)"
```

---

### Task 3: GAP-66(a) — suppression de widget depuis le canevas

**Files:**
- Modify: `shell/src/builder/GridCanvas.tsx`, `GridCanvas.test.tsx`
- Modify: `shell/src/builder/LayoutEditor.tsx`
- Modify: `shell/src/builder/AppRenderer.tsx`
- Modify: `shell/src/builder/widgets/tabs.tsx`, `modal.tsx`, `drawer.tsx`
  (le seul changement ici : passer `onRemoveItem={() => {}}` à leur
  `GridCanvas` non-éditable imbriqué — ces 3 sites ne gagnent **pas** de
  bouton de suppression, ils satisfont juste le nouveau prop obligatoire)
- Modify: `shell/src/pages/AppBuilderPage.tsx`, `AppBuilderPage.test.tsx`
- Create: `shell/e2e/app-builder-delete-widget.spec.ts`

**Interfaces:**
- `GridCanvas` gagne `onRemoveItem: (id: string) => void` (requis, même
  niveau que `onMoveItem`).
- `AppRenderer.tsx` gagne `handleRemove(id: string)`, appelé par
  `GridCanvas`'s nouveau bouton.
- `AppBuilderPage.tsx` gagne un raccourci clavier `Delete`/`Backspace`
  (ignoré en champ texte, même garde que `Ctrl+Z`) qui supprime
  `selectedId`.

- [ ] **Step 1: Write the failing GridCanvas test**

Append to `shell/src/builder/GridCanvas.test.tsx`:
```tsx
test("the remove button removes the selected item", async () => {
  const onRemoveItem = vi.fn();
  renderCanvas({ selectedId: "a", onRemoveItem });
  await userEvent.click(screen.getByRole("button", { name: "Supprimer widget-a" }));
  expect(onRemoveItem).toHaveBeenCalledWith("a");
});
```
Et mettre à jour `renderCanvas`'s défaut (`onRemoveItem: over.onRemoveItem
?? vi.fn()`) ainsi que le `<GridCanvas>` construit à la main dans le test
« positions items at the active breakpoint » (ajouter
`onRemoveItem={vi.fn()}`).

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/GridCanvas.test.tsx`
Expected: FAIL — TypeScript refuse la prop manquante / le bouton
« Supprimer widget-a » n'existe pas.

- [ ] **Step 3: Implement in `GridCanvas.tsx`**

Ajouter `onDeleteItem` — non, **`onRemoveItem`** — à la signature de props
et un 5e bouton dans le cluster (lignes ~55-102 au moment de l'audit),
après les 4 flèches :
```tsx
<button
  type="button"
  aria-label={`Supprimer widget-${item.id}`}
  className="bg-red-600 px-1 text-xs text-white"
  onClick={(e) => {
    e.stopPropagation();
    onRemoveItem(item.id);
  }}
>
  ✕
</button>
```
Ajouter `onRemoveItem: (id: string) => void;` à la destructuration et au
type de props de la fonction (même endroit que `onMoveItem`).

- [ ] **Step 4: Run to verify it passes, then update the 4 other call sites**

Run: `cd shell && npx vitest run src/builder/GridCanvas.test.tsx` → PASS.

`cd shell && npx tsc --noEmit` → doit maintenant lister une erreur par site
de `<GridCanvas>` qui ne fournit pas `onRemoveItem` : `AppRenderer.tsx`,
`LayoutEditor.tsx`, `widgets/tabs.tsx` (site runtime), `widgets/modal.tsx`,
`widgets/drawer.tsx`. Corriger chacun :

- `widgets/tabs.tsx` (canevas runtime, ligne ~163+), `widgets/modal.tsx`
  (ligne ~71+), `widgets/drawer.tsx` (ligne ~98+) : ajouter
  `onRemoveItem={() => {}}` juste après leur `onMoveItem={() => {}}`
  existant — ces 3 canevas restent non éditables, aucun autre changement.
- `LayoutEditor.tsx` : ajouter un `handleRemove(id)` local, miroir de son
  `handleMove` existant :
  ```ts
  function handleRemove(id: string) {
    onChange(items.filter((i) => i.id !== id));
    if (selectedId === id) setSelectedId(null);
  }
  ```
  et passer `onRemoveItem={handleRemove}` à son `<GridCanvas>`. Pas de
  `pruneMessagesForIds` ici : les items imbriqués d'un onglet/modale/tiroir
  ne sont jamais des émetteurs/récepteurs référencés par
  `ActionsPanel.messages` (celui-ci ne reçoit que `activeLayout.items`, la
  page courante — vérifié avant d'écrire cette tâche, à revérifier en
  l'exécutant si le code a bougé).
- `AppRenderer.tsx` : ajouter, à côté de `handleMove` existant :
  ```ts
  import { pruneMessagesForIds } from "./actionMessages";
  // ...
  function handleRemove(id: string) {
    if (!onChange) return;
    const items = activeLayout.items.filter((it) => it.id !== id);
    const next = setPageLayout(config, activePageId, { ...activeLayout, items });
    onChange({ ...next, messages: pruneMessagesForIds(next.messages, [id]) });
  }
  ```
  et passer `onRemoveItem={handleRemove}` à son `<GridCanvas>` (à côté de
  `onMoveItem={handleMove}`).

Run: `cd shell && npx tsc --noEmit` → PASS (0 site oublié).

- [ ] **Step 5: Keyboard shortcut in `AppBuilderPage.tsx`**

Étendre l'effect clavier existant (celui qui gère `Ctrl+Z`/`Ctrl+Shift+Z`,
même garde « pas dans un champ texte ») pour aussi gérer
`Delete`/`Backspace` :
```tsx
useEffect(() => {
  function onKeyDown(e: KeyboardEvent) {
    const target = document.activeElement;
    const isTextField =
      target instanceof HTMLInputElement ||
      target instanceof HTMLTextAreaElement ||
      (target instanceof HTMLElement && target.isContentEditable);
    if (isTextField) return;
    if ((e.key === "Delete" || e.key === "Backspace") && selectedId) {
      e.preventDefault();
      removeSelected();
      return;
    }
    if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
    e.preventDefault();
    if (e.shiftKey) redo();
    else undo();
  }
  window.addEventListener("keydown", onKeyDown);
  return () => window.removeEventListener("keydown", onKeyDown);
}, [undo, redo, selectedId]); // + removeSelected si ce n'est pas déjà stable
```
`removeSelected()` (nouvelle fonction, à côté d'`addWidget`) :
```ts
function removeSelected() {
  if (!selectedId || !activePage) return;
  const id = selectedId;
  setDraft((d) => {
    if (!d) return d;
    const layout = getPageLayout(d, activePage);
    const next = setPageLayout(d, activePage, {
      ...layout,
      items: layout.items.filter((i) => i.id !== id),
    });
    return { ...next, messages: pruneMessagesForIds(next.messages, [id]) };
  });
  setSelectedId(null);
}
```
Cette fonction est aussi celle qu'appelle le bouton `✕` de `GridCanvas` sur
le canevas principal — **passer `onRemoveItem={removeSelected}` côté
`AppRenderer` invocation dans `AppBuilderPage.tsx` plutôt que de dupliquer
la logique dans `AppRenderer.handleRemove`** : relire `AppRenderer.tsx`'s
prop `onChange` (c'est `setDraft` directement, pas une fonction locale) —
**décision à trancher en écrivant le code, pas ici** : soit `AppRenderer`
garde son propre `handleRemove` interne (appelé par son propre
`GridCanvas`, cf. Step 4) et `AppBuilderPage` n'a besoin de
`removeSelected()` que pour le raccourci clavier (les deux chemins
convergent vers le même résultat par des routes différentes, comme
`handleMove` d'`AppRenderer` et un futur raccourci clavier de déplacement
le feraient aussi) ; soit `removeSelected()` d'`AppBuilderPage` est la
seule source de vérité et `AppRenderer.handleRemove` lui délègue via un
prop optionnel supplémentaire. **Retenir la première option** (pas de
nouveau prop sur `AppRenderer` au-delà d'`onRemoveItem` déjà posé côté
`GridCanvas`) — plus simple, cohérente avec le fait qu'`AppRenderer` gère
déjà ses propres `handleMove`/`handleNavigate` sans déléguer à
`AppBuilderPage`.

- [ ] **Step 6: Write the failing AppBuilderPage tests**

Append to `shell/src/pages/AppBuilderPage.test.tsx` (patron identique aux
tests d'undo de SP-19 déjà dans ce fichier) :
```tsx
test("the remove button on GridCanvas removes the selected widget", async () => {
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(configWithOneTextWidget) });
  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.click(screen.getByRole("button", { name: "Supprimer widget-w1" }));
  expect(screen.queryByRole("button", { name: "Sélectionner widget-w1" })).not.toBeInTheDocument();
});

test("Backspace with a widget selected removes it, ignored while typing", async () => {
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(configWithOneTextWidget) });
  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.keyboard("{Backspace}");
  expect(screen.queryByRole("button", { name: "Sélectionner widget-w1" })).not.toBeInTheDocument();
});

test("removing a widget prunes any ActionsPanel message wired to it", async () => {
  // Config de départ : un widget Bouton (w1) câblé vers un widget Liste (w2)
  // via un ActionMessage. Après suppression de w1, ouvrir Actions et
  // vérifier qu'aucune ligne "Bouton.clicked → …" ne reste — vérifier
  // via l'onglet Actions du panneau Propriétés, pas seulement l'absence de
  // planter.
});
```
(Le 3e test ci-dessus est une esquisse — le rédiger avec une config
réaliste au moment de l'implémentation, en s'inspirant de la forme déjà
utilisée par les tests d'`ActionsPanel.test.tsx` pour construire un
`ActionMessage`.)

- [ ] **Step 7: Run to verify it fails, then implement, then verify it passes**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx` → FAIL,
puis implémenter §Step 5 ci-dessus, puis → PASS.

- [ ] **Step 8: E2E**

Create `shell/e2e/app-builder-delete-widget.spec.ts` :
```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("a widget can be removed from the canvas and the removal is undoable", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Texte" }).click();
  const select = page.getByRole("button", { name: /^Sélectionner widget-/ });
  await select.click();
  await page.getByRole("button", { name: /^Supprimer widget-/ }).click();
  await expect(select).toHaveCount(0);

  await page.keyboard.press("Control+z");
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toBeVisible();
});
```

- [ ] **Step 9: Full typecheck + unit suite**

Run: `cd shell && npx tsc --noEmit && npm run test`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add shell/src/builder/GridCanvas.tsx shell/src/builder/GridCanvas.test.tsx \
  shell/src/builder/LayoutEditor.tsx shell/src/builder/AppRenderer.tsx \
  shell/src/builder/widgets/tabs.tsx shell/src/builder/widgets/modal.tsx \
  shell/src/builder/widgets/drawer.tsx \
  shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx \
  shell/e2e/app-builder-delete-widget.spec.ts
git commit -m "feat(shell): supprimer un widget du canevas (bouton + Backspace), purge les câblages orphelins (GAP-66a)"
```

---

### Task 4: GAP-66(c) — suppression d'une variable purge ses câblages

**Files:**
- Modify: `shell/src/pages/AppBuilderPage.tsx`, `AppBuilderPage.test.tsx`
- Modify: `shell/e2e/variables.spec.ts`

**Interfaces:** `setVariables` change de forme (functional updater), même
signature externe consommée par `VariablesPanel` (`onChange: (variables) =>
void` — inchangé côté `VariablesPanel`).

- [ ] **Step 1: Write the failing test**

Append to `shell/src/pages/AppBuilderPage.test.tsx`:
```tsx
test("removing a variable prunes any ActionsPanel message wired to it", async () => {
  // Config de départ : draft.variables a une variable "seuil" (v1) ; un
  // ActionMessage câble un widget émetteur vers `var:v1`.set. Ouvrir
  // Variables, cliquer "Retirer la variable v1". Rouvrir Actions : la
  // ligne de câblage a disparu de la config sauvegardée (pas seulement de
  // l'affichage) — vérifier via l'objet passé à saveAppConfig après
  // Enregistrer, pas seulement via l'absence visuelle dans ActionsPanel
  // (qui la masquait déjà avant ce correctif).
});
```
Rédiger la config de départ au moment de l'implémentation ; le point
important de l'assertion est de vérifier **l'objet sauvegardé**
(`saveAppConfig.mock.calls[0][1].messages`), pas seulement l'affichage —
c'est justement la différence entre « masqué » (déjà vrai avant ce
correctif) et « purgé » (ce que ce correctif ajoute).

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: FAIL — le message orphelin est toujours présent dans l'objet
sauvegardé.

- [ ] **Step 3: Implement**

Remplacer, dans `AppBuilderPage.tsx` :
```ts
const setVariables = (variables: typeof draft.variables) =>
  setDraft((d) => (d ? { ...d, variables } : d));
```
par :
```ts
import { pruneMessagesForIds } from "../builder/actionMessages";
// ...
const setVariables = (variables: typeof draft.variables) =>
  setDraft((d) => {
    if (!d) return d;
    const before = new Set((d.variables ?? []).map((v) => v.id));
    const after = new Set((variables ?? []).map((v) => v.id));
    const removedIds = [...before]
      .filter((id) => !after.has(id))
      .map((id) => `var:${id}`);
    return { ...d, variables, messages: pruneMessagesForIds(d.messages, removedIds) };
  });
```
(Functional updater nécessaire ici précisément pour lire `d.variables`
*avant* mise à jour — pas seulement pour la raison usuelle de batching déjà
documentée sur `addWidget` dans ce même fichier.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: PASS.

- [ ] **Step 5: E2E**

Append to `shell/e2e/variables.spec.ts` :
```ts
test("removing a wired variable removes the dangling ActionsPanel wiring", async ({ page }) => {
  // Reprendre le montage existant de ce fichier (Filtre → variable → Texte)
  // et, après avoir vérifié le câblage fonctionnel (test déjà présent),
  // retirer la variable depuis le panneau Variables puis rouvrir Actions :
  // vérifier qu'aucune ligne "… → Variable : …" ne subsiste.
});
```

- [ ] **Step 6: Run + typecheck**

Run: `cd shell && npx vitest run && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx shell/e2e/variables.spec.ts
git commit -m "fix(shell): supprimer une variable purge les câblages ActionsPanel orphelins (GAP-66c)"
```

---

### Task 5: GAP-66(b) — `setFilter` du copilote fusionne au lieu de remplacer

**Files:**
- Modify: `shell/src/builder/copilot/applyClientOp.ts`, `.test.ts`
- Modify: `shell/src/builder/copilot/clientTools.ts`

**Interfaces:** aucun changement de signature — même shape de `RawClientOp`,
comportement interne changé.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/copilot/applyClientOp.test.ts` :
```ts
it("setFilter merges into the existing query instead of replacing it", () => {
  let config = applyClientOp(
    { op: "addDataSource", args: { id: "ds1", type: "statistics", service: "core", layer: "incidents" } },
    emptyConfig(),
    "page-1",
  );
  config = applyClientOp(
    { op: "setFilter", args: { dataSourceId: "ds1", query: { groupBy: "category", agg: "sum", field: "amount" } } },
    config,
    "page-1",
  );
  config = applyClientOp(
    { op: "setFilter", args: { dataSourceId: "ds1", query: { status: "active" } } },
    config,
    "page-1",
  );
  expect(config.dataSources[0].query).toEqual({
    groupBy: "category",
    agg: "sum",
    field: "amount",
    status: "active",
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/copilot/applyClientOp.test.ts`
Expected: FAIL — le second `setFilter` écrase `groupBy`/`agg`/`field`.

- [ ] **Step 3: Implement**

Dans `applyClientOp.ts`, remplacer :
```ts
case "setFilter": {
  const dataSourceId = String(raw.args.dataSourceId ?? "");
  const query = (raw.args.query ?? {}) as Record<string, unknown>;
  return {
    ...config,
    dataSources: config.dataSources.map((s) => (s.id === dataSourceId ? { ...s, query } : s)),
  };
}
```
par :
```ts
case "setFilter": {
  const dataSourceId = String(raw.args.dataSourceId ?? "");
  const patch = (raw.args.query ?? {}) as Record<string, unknown>;
  return {
    ...config,
    dataSources: config.dataSources.map((s) =>
      s.id === dataSourceId ? { ...s, query: { ...s.query, ...patch } } : s,
    ),
  };
}
```

- [ ] **Step 4: Run to verify it passes (both tests)**

Run: `cd shell && npx vitest run src/builder/copilot/applyClientOp.test.ts`
Expected: PASS (le test existant « setFilter updates an existing source's
query » doit rester vert inchangé — il part d'une query vide, fusion et
remplacement y produisent le même résultat).

- [ ] **Step 5: Mettre à jour la description du tool**

Dans `clientTools.ts`, remplacer la description de `setFilter` :
```ts
description: "Modifie la requête (filtre) d'une source de données existante.",
```
par :
```ts
description:
  "Fusionne des clés dans la requête (filtre) d'une source de données existante — les clés déjà présentes et non citées ici restent inchangées.",
```

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/copilot/applyClientOp.ts shell/src/builder/copilot/applyClientOp.test.ts shell/src/builder/copilot/clientTools.ts
git commit -m "fix(shell): setFilter du copilote fusionne la requête au lieu de la remplacer (GAP-66b)"
```

(Pas d'E2E dédiée : ce chemin n'est exercé qu'avec `copilotEnabled` — déjà
couvert par le filet Vitest unitaire de `applyClientOp.ts`, cohérent avec
le reste de la suite copilote qui n'a pas d'E2E Playwright dédiée pour
chaque tool individuel.)

---

### Task 6: GAP-54 — Onglets : contenu réel visible en mode édition

**Files:**
- Modify: `shell/src/builder/widgets/tabs.tsx`, `.test.tsx`
- Create/extend: E2E (voir Step 5)

**Interfaces:** aucun changement de props/état du widget — changement de
rendu uniquement.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/widgets/tabs.test.tsx` :
```tsx
test("edit mode renders the active tab's real content, not an empty band", () => {
  // Monter le widget Tabs (Component, ctx.mode = "edit") avec un onglet
  // portant un item "text" dont les props affichent un texte connu ;
  // vérifier que ce texte est présent dans le DOM (pas seulement le
  // libellé de l'onglet).
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/tabs.test.tsx`
Expected: FAIL — le texte n'apparaît pas (bandeau vide actuel).

- [ ] **Step 3: Implement**

Dans `tabs.tsx`, remplacer le corps de la branche `if (ctx.mode ===
"edit")` :
```tsx
if (ctx.mode === "edit") {
  return (
    <div className="flex h-full flex-col">
      <div className="flex gap-1 border-b border-[var(--gs-color-border)] p-1 text-xs">
        {tabs.map((t) => (
          <span key={t.id} className="px-2 py-1">{t.label}</span>
        ))}
      </div>
      <div className="min-h-0 flex-1">
        <GridCanvas
          items={active.items}
          breakpoint={ctx.breakpoint ?? "lg"}
          editable={false}
          selectedId={null}
          onSelect={() => {}}
          onMoveItem={() => {}}
          onRemoveItem={() => {}}
          renderItem={(item) => (
            <WidgetHost
              item={item}
              mode="preview"
              pages={ctx.pages}
              navigate={ctx.navigate}
              breakpoint={ctx.breakpoint}
            />
          )}
        />
      </div>
    </div>
  );
}
```
**Vérifier avant d'écrire ce code** quel mode la branche non-édition du même
fichier (juste en dessous) passe réellement à `WidgetHost` — copier cette
valeur exacte plutôt que d'inventer `"preview"` ici si le code réel utilise
autre chose (spec §3.1, note de vérification).

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/widgets/tabs.test.tsx`
Expected: PASS. Vérifier aussi que le test existant du `PropsPanel` (qui
édite via son propre `LayoutEditor`) reste vert — deux surfaces
indépendantes, aucune ne doit régresser l'autre.

- [ ] **Step 5: E2E**

Ajouter à un spec E2E existant qui monte déjà un widget Onglets (chercher
`shell/e2e/*.spec.ts` pour un montage Onglets existant — sinon en créer un
minimal) :
```ts
test("a Tabs widget shows its active tab's content directly on the edit canvas", async ({ page }) => {
  // Ajouter un widget Onglets, ajouter un widget Texte dans son premier
  // onglet via le panneau Propriétés, refermer le panneau : le texte doit
  // être visible sur le canevas principal sans rouvrir les Propriétés.
});
```

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/widgets/tabs.tsx shell/src/builder/widgets/tabs.test.tsx
git commit -m "fix(shell): le widget Onglets affiche le contenu réel de l'onglet actif en mode édition (GAP-54)"
```

---

### Task 7: GAP-51 — éditeur de source « Statique »

**Files:**
- Modify: `shell/src/builder/DataSourcePanel.tsx`, `.test.tsx`
- Create: `shell/e2e/app-builder-static-source.spec.ts`

**Interfaces:** aucun changement de `DataSource`/`DataRecord` (types
existants) — `s.query.records` déjà lu par
`shell/src/api/domains/datasets.ts`.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/DataSourcePanel.test.tsx` :
```tsx
test("a static source exposes a records editor, not the features/statistics fields", async () => {
  const onChange = vi.fn();
  render(<DataSourcePanel sources={[{ id: "s1", type: "static", service: "", layer: "", query: {} }]} onChange={onChange} />);
  expect(screen.getByRole("button", { name: "Ajouter un enregistrement" })).toBeInTheDocument();
  expect(screen.queryByLabelText(/Collection de la source/)).not.toBeInTheDocument();
});

test("adding a record pushes a new entry with an auto-generated id", async () => {
  const onChange = vi.fn();
  render(<DataSourcePanel sources={[{ id: "s1", type: "static", service: "", layer: "", query: {} }]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter un enregistrement" }));
  const [sources] = onChange.mock.calls[0];
  expect(sources[0].query.records).toHaveLength(1);
  expect(sources[0].query.records[0]).toMatchObject({ properties: {} });
});

test("editing a record's JSON on blur commits valid JSON, rejects invalid JSON with an alert", async () => {
  const onChange = vi.fn();
  const source = { id: "s1", type: "static" as const, service: "", layer: "", query: { records: [{ id: "r1", properties: {} }] } };
  render(<DataSourcePanel sources={[source]} onChange={onChange} />);
  const area = screen.getByLabelText(/Propriétés de l'enregistrement r1/);
  await userEvent.clear(area);
  await userEvent.type(area, '{"name":"A"}');
  area.blur();
  await waitFor(() => {
    const [sources] = onChange.mock.calls.at(-1)!;
    expect(sources[0].query.records[0].properties).toEqual({ name: "A" });
  });

  await userEvent.clear(area);
  await userEvent.type(area, "{not json");
  area.blur();
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});

test("removing a record drops it from query.records", async () => {
  const onChange = vi.fn();
  const source = { id: "s1", type: "static" as const, service: "", layer: "", query: { records: [{ id: "r1", properties: {} }] } };
  render(<DataSourcePanel sources={[source]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: /Retirer l'enregistrement r1/ }));
  const [sources] = onChange.mock.calls[0];
  expect(sources[0].query.records).toEqual([]);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx`
Expected: FAIL — aucun contrôle « Statique » n'existe encore.

- [ ] **Step 3: Implement**

Dans `DataSourcePanel.tsx`, ajouter après le bloc `{s.type ===
"statistics" && (...)}` (juste avant le `</li>` de fermeture) :
```tsx
{s.type === "static" && (
  <div className="mt-1 flex flex-col gap-1">
    {(Array.isArray(s.query.records) ? (s.query.records as DataRecord[]) : []).map((r) => (
      <StaticRecordRow
        key={r.id}
        record={r}
        onChange={(properties) =>
          patchQuery(s.id, {
            records: (s.query.records as DataRecord[]).map((x) =>
              x.id === r.id ? { ...x, properties } : x,
            ),
          })
        }
        onRemove={() =>
          patchQuery(s.id, {
            records: (s.query.records as DataRecord[]).filter((x) => x.id !== r.id),
          })
        }
      />
    ))}
    <button
      type="button"
      className="rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-100"
      onClick={() =>
        patchQuery(s.id, {
          records: [
            ...(Array.isArray(s.query.records) ? (s.query.records as DataRecord[]) : []),
            { id: crypto.randomUUID(), properties: {} },
          ],
        })
      }
    >
      Ajouter un enregistrement
    </button>
  </div>
)}
```
Et un petit composant local, en bas du fichier ou juste avant
`DataSourcePanel` :
```tsx
function StaticRecordRow({
  record,
  onChange,
  onRemove,
}: {
  record: DataRecord;
  onChange: (properties: Record<string, unknown>) => void;
  onRemove: () => void;
}) {
  const [text, setText] = useState(JSON.stringify(record.properties));
  const [error, setError] = useState<string | null>(null);
  function commit() {
    try {
      const parsed = JSON.parse(text);
      setError(null);
      onChange(parsed);
    } catch {
      setError("JSON invalide — modification non enregistrée.");
    }
  }
  return (
    <div className="flex flex-col gap-1 rounded border border-slate-200 p-1">
      <div className="flex items-center gap-1">
        <textarea
          aria-label={`Propriétés de l'enregistrement ${record.id}`}
          className="h-16 flex-1 rounded border border-slate-300 p-1 font-mono text-xs"
          value={text}
          onChange={(e) => setText(e.target.value)}
          onBlur={commit}
        />
        <button
          type="button"
          aria-label={`Retirer l'enregistrement ${record.id}`}
          className="text-xs text-red-600"
          onClick={onRemove}
        >
          ✕
        </button>
      </div>
      {error && <span role="alert" className="text-xs text-red-600">{error}</span>}
    </div>
  );
}
```
Ajouter l'import `useState` et `DataRecord` (`import type { DataRecord,
DataSource } from "../api/types";`) en tête de fichier.

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx`
Expected: PASS.

- [ ] **Step 5: E2E**

Create `shell/e2e/app-builder-static-source.spec.ts` :
```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("a static data source's records feed a widget bound to it", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Ouvrir Sources de données, ajouter une source, la passer en Statique,
  // ajouter un enregistrement, saisir un JSON de propriétés, ajouter un
  // widget Liste bindé à cette source, vérifier que l'enregistrement
  // apparaît dans le rendu du widget (en édition ou en aperçu, à trancher
  // à l'implémentation selon ce que le widget Liste rend déjà en édition).
});
```

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/DataSourcePanel.tsx shell/src/builder/DataSourcePanel.test.tsx shell/e2e/app-builder-static-source.spec.ts
git commit -m "feat(shell): éditeur d'enregistrements pour les sources de données Statique (GAP-51)"
```

---

### Task 8: GAP-13 — widget « Saisie » lié à une variable

**Files:**
- Modify: `shell/src/builder/VariablesContext.tsx`
- Modify: `shell/src/builder/sdk.ts`
- Modify: `shell/src/builder/registry.ts`
- Modify: `shell/src/builder/PropsPanel.tsx`
- Modify: `shell/src/builder/LayoutEditor.tsx`
- Modify: `shell/src/builder/widgets/tabs.tsx`, `modal.tsx`, `drawer.tsx`
  (thread `variables` vers leur `LayoutEditor` imbriqué)
- Modify: `shell/src/pages/AppBuilderPage.tsx` (thread `variables={draft.variables}`)
- Modify: `shell/src/builder/widgets/index.tsx` (enregistrement)
- Create: `shell/src/builder/widgets/variableInput.tsx`, `.test.tsx`
- Create: `shell/e2e/variable-input-widget.spec.ts`

**Interfaces:**
- `useVariableDefs(): Variable[]` — nouveau hook sur `VariablesContext.tsx`.
- `WidgetDefinition["PropsPanel"]` gagne un champ optionnel `variables?:
  Variable[]`.
- Nouveau widget `type: "variableInput"`, `label: "Saisie"`,
  `defaultProps: { variableId: "", label: "" }`.

- [ ] **Step 1: `useVariableDefs` — write the failing test**

Append to `shell/src/builder/VariablesContext.test.tsx` (créer ce fichier
s'il n'existe pas déjà — vérifier avant) :
```tsx
test("useVariableDefs exposes the raw Variable[] passed to the provider", () => {
  const variables: Variable[] = [{ id: "v1", name: "seuil", type: "number", initialValue: 0 }];
  const { result } = renderHook(() => useVariableDefs(), {
    wrapper: ({ children }) => <VariablesProvider variables={variables}>{children}</VariablesProvider>,
  });
  expect(result.current).toEqual(variables);
});
```

- [ ] **Step 2: Run to verify it fails, then implement**

Dans `VariablesContext.tsx`, ajouter :
```ts
const VariableDefsContext = createContext<Variable[]>([]);
// ...
export function VariablesProvider({ variables, children }: ...) {
  // ... (state values inchangé)
  return (
    <VariableDefsContext.Provider value={variables}>
      <SetVariableContext.Provider value={setVariable}>
        <VariablesContext.Provider value={values}>{children}</VariablesContext.Provider>
      </SetVariableContext.Provider>
    </VariableDefsContext.Provider>
  );
}
// ...
export function useVariableDefs(): Variable[] {
  return useContext(VariableDefsContext);
}
```
Run: `cd shell && npx vitest run src/builder/VariablesContext.test.tsx` →
PASS.

Exporter aussi depuis `sdk.ts` (cohérence avec `useVariables`/
`useSetVariable` déjà réexportés) :
```ts
export { useVariables, useSetVariable, useVariableDefs } from "./VariablesContext";
```

- [ ] **Step 3: `variables` optionnel sur `PropsPanel` — thread**

`registry.ts` : ajouter `variables?: Variable[];` au type de la fonction
`PropsPanel` de `WidgetDefinition` (importer `Variable` depuis
`../api/types`).

`PropsPanel.tsx` (le composant, pas le type) : ajouter un prop optionnel
`variables?: Variable[]` (défaut `[]`), le passer à `<Panel ...
variables={variables ?? []} />`.

`AppBuilderPage.tsx` : passer `variables={draft.variables ?? []}` à son
`<PropsPanel ...>`.

`LayoutEditor.tsx` : ajouter un prop `variables?: Variable[]` à sa
signature, le passer à son propre `<PropsPanel ... variables={variables ??
[]} />` imbriqué.

`widgets/tabs.tsx`, `modal.tsx`, `drawer.tsx` : leur `PropsPanel`
destructure déjà `dataSources` — ajouter `variables` à la même
destructuration (`({ props, onChange, dataSources, variables }) => {`) et
le passer à leur `<LayoutEditor ... variables={variables} />` imbriqué.

**Ces 3 sites + `LayoutEditor.tsx` + `AppBuilderPage.tsx` + `PropsPanel.tsx`
: 6 fichiers, prop optionnel partout — le compilateur ne signale aucun
oubli** (contrairement à Task 3). Grep de clôture obligatoire avant de
considérer cette étape close :
```bash
grep -rln "PropsPanel:" shell/src/builder/widgets/*.tsx | xargs grep -L "variables"
```
Tout fichier listé qui a un `PropsPanel` utilisant un `LayoutEditor`
imbriqué (seuls `tabs.tsx`/`modal.tsx`/`drawer.tsx` en ont un — les 19+
autres widgets n'ont pas de contenu imbriqué et n'ont pas besoin de ce
threading) doit être revu avant de continuer.

- [ ] **Step 4: Write the failing widget tests**

Create `shell/src/builder/widgets/variableInput.test.tsx` :
```tsx
// SPDX-License-Identifier: Apache-2.0
// Vérifie : (1) le PropsPanel liste les variables disponibles par nom ;
// (2) le Component en mode edit rend un contrôle désactivé ; (3) en mode
// preview/runtime, taper dans le contrôle appelle useSetVariable avec le
// nom courant de la variable référencée par id (pas un nom figé) ; (4) le
// type de contrôle suit VariableType (number → input[type=number], bool →
// checkbox, date → input[type=date], string → text) ; (5) un variableId
// qui ne résout plus affiche un état "Variable introuvable" sans planter.
```
(Rédiger les 5 cas ci-dessus comme des `test(...)` complets au moment de
l'implémentation — patron déjà en place dans `tabs.test.tsx`/
`selectFilter.test.tsx` pour monter un widget avec `VariablesProvider` en
wrapper.)

- [ ] **Step 5: Run to verify it fails, then implement**

Create `shell/src/builder/widgets/variableInput.tsx`, modelé sur
`selectFilter.tsx` (widget le plus proche par simplicité) :
```tsx
// SPDX-License-Identifier: Apache-2.0
import { registerWidget } from "../registry";
import { useVariableDefs, useVariables, useSetVariable } from "../VariablesContext";
import type { Variable } from "../../api/types";

type Props = { variableId: string; label: string };

function controlFor(variable: Variable, value: unknown, onChange: (v: unknown) => void, disabled: boolean) {
  const type = variable.type ?? "string";
  if (type === "number") {
    return <input type="number" disabled={disabled} value={Number(value ?? 0)} onChange={(e) => onChange(Number(e.target.value))} />;
  }
  if (type === "bool") {
    return <input type="checkbox" disabled={disabled} checked={Boolean(value)} onChange={(e) => onChange(e.target.checked)} />;
  }
  if (type === "date") {
    return <input type="date" disabled={disabled} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />;
  }
  return <input type="text" disabled={disabled} value={String(value ?? "")} onChange={(e) => onChange(e.target.value)} />;
}

export function registerVariableInputWidget(): void {
  registerWidget({
    type: "variableInput",
    label: "Saisie",
    defaultProps: { variableId: "", label: "" } satisfies Props,
    defaultSize: { w: 3, h: 2 },
    configSchema: [
      { name: "variableId", type: "string", label: "Variable", default: "" },
      { name: "label", type: "string", label: "Libellé", default: "" },
    ],
    PropsPanel: ({ props, onChange, variables = [] }) => {
      const { variableId, label } = props as Props;
      return (
        <div className="flex flex-col gap-2 text-sm">
          <label className="flex flex-col gap-1">
            Variable
            <select
              aria-label="Variable liée"
              value={variableId}
              onChange={(e) => onChange({ variableId: e.target.value, label })}
            >
              <option value="">Choisir une variable…</option>
              {variables
                .filter((v) => (v.type ?? "string") !== "record" && (v.type ?? "string") !== "list")
                .map((v) => (
                  <option key={v.id} value={v.id}>{v.name}</option>
                ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            Libellé
            <input value={label} onChange={(e) => onChange({ variableId, label: e.target.value })} />
          </label>
        </div>
      );
    },
    Component: ({ props, ctx }) => {
      const { variableId, label } = props as Props;
      const defs = useVariableDefs();
      const values = useVariables();
      const setVariable = useSetVariable();
      const variable = defs.find((v) => v.id === variableId);
      if (!variable) {
        return <p className="text-xs text-slate-400">Variable introuvable.</p>;
      }
      const disabled = ctx.mode === "edit";
      return (
        <label className="flex flex-col gap-1 text-sm">
          {label || variable.name}
          {controlFor(variable, values[variable.name], (v) => setVariable(variable.name, v), disabled)}
        </label>
      );
    },
  });
}
```
**Vérifier avant de merger** : `useVariableDefs`/`useVariables`/
`useSetVariable` appelés directement dans `Component` — légitime
puisque `WidgetHost.tsx` rend `<Widget ... />` comme un véritable élément
JSX (pas un appel de fonction brut), donc les règles des hooks sont
respectées ; confirmer ce point en lisant `WidgetHost.tsx` avant
d'implémenter si le fichier a changé depuis la rédaction de cette tâche.

Enregistrer dans `widgets/index.tsx` :
```ts
import { registerVariableInputWidget } from "./variableInput";
// ...
registerVariableInputWidget();
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/widgets/variableInput.test.tsx`
Expected: PASS.

- [ ] **Step 7: Full typecheck + unit suite**

Run: `cd shell && npx tsc --noEmit && npm run test`
Expected: PASS.

- [ ] **Step 8: E2E**

Create `shell/e2e/variable-input-widget.spec.ts` :
```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("a Saisie widget bound to a number variable updates a Texte widget reading it, at runtime", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Ajouter une variable "seuil" (number) via le panneau Variables ;
  // ajouter un widget Saisie, le lier à "seuil" ; ajouter un widget Texte
  // dont le texte interpole {{var:seuil}} ; Enregistrer ; ouvrir le
  // runtime ; taper une valeur dans le champ Saisie ; vérifier que le
  // Texte se met à jour sans rechargement de page.
});
```

- [ ] **Step 9: Commit**

```bash
git add shell/src/builder/VariablesContext.tsx shell/src/builder/VariablesContext.test.tsx \
  shell/src/builder/sdk.ts shell/src/builder/registry.ts shell/src/builder/PropsPanel.tsx \
  shell/src/builder/LayoutEditor.tsx shell/src/builder/widgets/tabs.tsx \
  shell/src/builder/widgets/modal.tsx shell/src/builder/widgets/drawer.tsx \
  shell/src/builder/widgets/variableInput.tsx shell/src/builder/widgets/variableInput.test.tsx \
  shell/src/builder/widgets/index.tsx shell/src/pages/AppBuilderPage.tsx \
  shell/e2e/variable-input-widget.spec.ts
git commit -m "feat(shell): widget Saisie — liaison directe d'un contrôle natif à une variable typée (GAP-13, chantier 4.24)"
```

---

### Task 9: vérification finale de branche

**Files:** aucun (vérification uniquement).

- [ ] **Step 1: Suite Vitest complète**

Run: `cd shell && npm run test`
Expected: PASS, aucune régression. Comparer le compte de tests à la mesure
de clôture SP-41/42 dans `CLAUDE.md` — une variation nette (au-delà des
tests ajoutés par ce plan) mérite investigation avant de continuer.

- [ ] **Step 2: Suite E2E complète**

Run: `cd shell && npm run e2e`
Expected: PASS — `VITE_AUTH_MODE=mock`. C'est le filet qui, historiquement
sur ce dépôt (`CLAUDE.md` piège n°6), trouve les régressions de
croisement entre tâches qu'aucune suite unitaire par tâche ne peut voir —
en particulier ici, un site de `<GridCanvas>` oublié dans Task 3 malgré le
prop obligatoire (un test qui construit un mock incomplet peut encore
compiler si le mock n'est pas le vrai composant), ou un rendu `tabs.tsx`
(Task 6) qui interagit mal avec la sélection de widget imbriquée (Task 3
touche aussi `LayoutEditor.tsx`, consommé par `tabs.tsx`).

- [ ] **Step 3: Portes de qualité**

Run:
```bash
cd shell && npm run lint && npm run format:check
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```
(nettoyer `dist/`/`dist-export/` avant la mesure de couverture — piège
documenté 4 fois dans `CLAUDE.md`).

- [ ] **Step 4: Grep de clôture (Task 8, prop optionnel non garanti par le compilateur)**

Run:
```bash
grep -rln "PropsPanel:" shell/src/builder/widgets/*.tsx | xargs grep -L "variables"
```
Expected: seuls les widgets sans contenu imbriqué apparaissent (aucun
`LayoutEditor` interne) — confirmer qu'aucun des 3 conteneurs
(`tabs.tsx`/`modal.tsx`/`drawer.tsx`) n'apparaît dans la sortie.

- [ ] **Step 5: Régénération OpenAPI/types TS — vérification négative**

Ce plan ne touche aucune route ni modèle du cœur. Confirmer par un diff
vide plutôt que de supposer :
```bash
cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py /tmp/openapi-check.json
diff core/openapi.json /tmp/openapi-check.json
cd ../shell && npm run gen:api-types && git diff --stat src/api/generated/core-schema.d.ts
```
Expected : deux diffs vides — confirme qu'aucune route/modèle n'a
silencieusement changé de forme (piège n°1 CLAUDE.md), légitime ici
puisque ce plan est shell-only.

- [ ] **Step 6: Mise à jour de `CLAUDE.md`**

Ajouter une ligne `### Livré` pour SP-52, cohérente avec le format des
entrées précédentes (une phrase, gaps fermés cités par leur id, tout suivi
non bloquant explicite — ex. si l'ajustement de synchronisation
`activeId` évoqué en spec §3.1 (onglet prévisualisé sur le canevas
toujours le premier, indépendant du sélecteur du `PropsPanel`) est laissé
tel quel, le documenter comme limitation connue plutôt que de laisser un
lecteur futur le découvrir).

---

## Self-review notes

- **Spec coverage** : les 5 gaps de
  `docs/superpowers/specs/2026-09-05-sp52-app-builder-ux-design.md` ont
  chacun leur tâche (GAP-33→Task 1, GAP-66a→Task 3, GAP-66c→Task 4,
  GAP-66b→Task 5, GAP-54→Task 6, GAP-51→Task 7, GAP-13→Task 8). Task 2
  n'est pas un gap séparé : c'est le filet ajouté par la spec (note
  ajoutée en §3.2/§3.4) pour que Task 3 et Task 4 ne dupliquent pas la même
  règle de purge à deux endroits légèrement différents.
- **Ordre** : Task 2 avant Task 3/4 (dépendance réelle) ; sinon ordre
  spec §4 (du moins au plus invasif) préservé — Task 1 (nul), Task 5/6/7
  (bas), Task 3/4 (moyen, prop obligatoire + fonction partagée), Task 8
  (le plus invasif, seul endroit sans filet de complétude mécanique).
- **Placeholder scan** : Task 3 Step 5 et Task 8 Step 4 contiennent des
  esquisses de test (commentaire décrivant le scénario plutôt que le code
  complet) — assumé délibérément : la forme exacte de la config de départ
  dépend de patrons déjà en place ailleurs (`ActionsPanel.test.tsx`,
  `tabs.test.tsx`) qu'il faut relire au moment de l'implémentation plutôt
  que de recopier à l'aveugle dans ce document. Chaque esquisse dit
  explicitement quoi vérifier et pourquoi — pas seulement « ajouter un
  test ».
- **Risque non mitigé mécaniquement** : Task 8's threading de `variables`
  à travers 6 fichiers repose sur un grep de clôture (Step 3), pas sur le
  compilateur (prop optionnel) — seule tâche de ce plan dans ce cas,
  documenté explicitement dans la spec (§4) et repris ici (Task 9 Step 4
  revérifie le même grep en toute fin de plan, pas seulement en fin de
  Task 8, au cas où une tâche postérieure aurait ajouté un widget
  conteneur sans le savoir).
