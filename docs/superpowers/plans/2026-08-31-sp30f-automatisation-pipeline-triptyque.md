# SP-30f — Automatisation, volet 1 (PipelineBuilderPage) sur le socle triptyque Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Basculer `PipelineBuilderPage` (première page de la famille 6 « Automatisation »,
`docs/superpowers/specs/2026-08-30-sp30-bascule-triptyque-design.md` §6.1) sur
`TriptychLayout` : trois onglets — « Étapes » (`PipelinePalette`, reprend le
libellé de la maquette PIPELINE), « Canevas » (titre local + `PipelineCanvas`,
le graphe DAG), « Propriétés » (inspecteur du nœud sélectionné +
`PipelinePreviewPanel`, puis `PipelineRunPanel`, `PipelineScheduleEditor`,
`ConfigHistoryPanel`, Enregistrer).

**Ce que ce plan NE fait PAS** : famille 6 compte trois pages
(`PipelineBuilderPage`, `ReportEditPage`, `VisualQueryWizardPage`) — c'est la
première fois qu'une famille du §6.1 en compte plus d'une (les familles 3/4/5
n'en avaient qu'une chacune). Ce plan ne traite que `PipelineBuilderPage` ;
`ReportEditPage` et `VisualQueryWizardPage` restent dans un ou plusieurs plans
SP-30g+ séparés (granularité : une page par plan, comme SP-30c/d/e — pas un
plan par famille entière, la spec ne l'exige pas). `PipelineRunPanel.tsx` et
`PipelineScheduleEditor.tsx` (Task 4 ci-dessous) sont **partagés** avec
`VisualQueryWizardPage` — kit-ifiés maintenant, ils seront consommés tels
quels par SP-30g sans nouveau travail (même séquencement que
`ConfigHistoryPanel` kit-ifié par SP-30c et réutilisé sans retouche par
SP-30d/e). Le coffre de secrets visible dans la maquette PIPELINE
(`docs/design/triptyque-geostudio.html` lignes 737-738, badge « nouveau ») et
la liste « Ce pipeline · 5 » (nœuds déjà placés, listés dans le volet gauche
de la maquette) sont des **fonctionnalités non implémentées aujourd'hui** —
aucune route ni composant existant ne les porte. Ce plan ne les ajoute pas
(piège n°4 : ne pas mélanger bascule de layout et nouvelle fonctionnalité
dans le même plan) ; le volet « Étapes » ne contient donc que
`PipelinePalette` (la « Bibliothèque » de la maquette), pas de liste des
nœuds déjà placés. `QueryFilterBuilder.tsx`/`QuerySummaryBuilder.tsx`
(utilisés par `VisualQueryWizardPage`, importent `ui/dialog`) et
`ReportScheduleEditor.tsx`/`ReportRunPanel.tsx` (utilisés par
`ReportEditPage`) restent hors de ce plan.

**Décisions explicites de ce plan (à ne pas re-débattre en exécution)** :

1. **L'inspecteur ne montre rien de nouveau quand aucun nœud n'est
   sélectionné** — comportement inchangé : avant ce plan, la colonne de
   droite (`w-64 shrink-0 border-l`) était simplement vide hors sélection
   (`{selectedNode && catalog[selectedNode.op] && (...)}`, aucun message de
   repli). Contrairement à SP-30e (§ decision 1, où `PropsPanel` avait déjà
   son propre message « Aucun widget sélectionné » **avant** ce plan-là et
   ce plan-ci le préserve), il n'existe ici aucun message de repli
   préexistant à préserver — en inventer un serait une fonctionnalité
   nouvelle, hors périmètre (piège n°4). L'onglet « Propriétés » omet donc
   entièrement le bloc « Nœud sélectionné » (label compris) tant qu'aucun
   nœud n'est sélectionné, exactement comme aujourd'hui.
2. **`Enregistrer` déménage du haut du volet Canevas vers le bas du volet
   Propriétés**, aligné sur les trois familles précédentes (`MapEditorPage`
   « Inspecter », `DatasetEditPage` « Réglages », `AppBuilderPage`
   « Propriétés » : dans les trois cas, Enregistrer est le dernier élément
   du volet de réglages, jamais dans l'en-tête du volet d'édition). Le titre
   du pipeline (`<h2>{initialTitle ?? "Pipeline"}</h2>`) reste seul dans
   l'en-tête local du volet Canevas — pas de bouton à côté, à la manière du
   `<h2>` local de `DatasetEditPage` (SP-30d). Le message d'erreur de
   sauvegarde (`saveError`) déménage avec le bouton, pour rester adjacent.
   Sur large viewport, `TriptychLayout` rend les trois volets simultanément
   (vérifié dans `shell/src/shell/chrome/TriptychLayout.tsx:22-29` : la
   branche `!narrow` retourne une grille à trois colonnes, aucune n'est
   masquée) — le test « unsaved mode: Enregistrer is disabled on an empty
   graph » (`getByRole("button", {name: "Enregistrer"})` sans navigation
   d'onglet) continue de le trouver sans changement.
3. **Les couleurs catégorielles de `PipelineCanvas.tsx` restent en dur,
   volontairement** : `KIND_COLOR` (bordure/fond emerald/amber/sky par
   type de nœud — lecteur/transform/écrivain) et le badge de comptage de
   lignes (`bg-emerald-600 ... text-white`) sont un encodage sémantique
   catégoriel, pas du chrome neutre — même classe d'exemption que la dette
   de `MapSymbologyEditor`/`LayersPanel` documentée par SP-30c (`CLAUDE.md`,
   « Suivis non bloquants »). En revanche, `ring-blue-500` (anneau de
   sélection d'un nœud) et `border-blue-500` (spinner « exécution en
   cours ») sont converti en `ring-accent`/`border-accent` dans ce plan :
   ce ne sont pas des couleurs catégorielles mais des doublons littéraux du
   token `accent` déjà utilisé partout ailleurs pour l'état
   sélectionné/actif (`Button` du kit : `focus-visible:ring-accent`,
   `hover:bg-accent-ink`) — les convertir ne crée aucune nouvelle décision
   de design, juste une correction de littéral. La grep de vérification de
   ce plan (Task 6) couvre donc explicitement `ring-` en plus des préfixes
   `text-`/`bg-`/`border-` déjà couverts par les plans précédents (les
   trois plans précédents ne vérifiaient jamais `ring-`, aucun fichier
   qu'ils touchaient n'en avait).
   `PipelinePreviewMap.tsx` (couleurs hex `#2563eb` de rendu cartographique)
   est, de la même façon, entièrement exempté — ni Tailwind ni couleur de
   chrome, données géométriques rendues sur fond de carte.
4. **`onDragOver`/`onDrop` (drop d'une op de la palette sur le canevas)
   déménagent du conteneur `<div className="flex gap-4">` (englobait
   auparavant palette + canevas + inspecteur en une seule rangée flex) vers
   le conteneur `-m-6` externe qui enveloppe tout `TriptychLayout`.** Sans
   ce déplacement, un drop resterait fonctionnellement capté nulle part une
   fois la palette et le canevas séparés en deux colonnes de grille
   indépendantes. Le calcul de position reste identique
   (`{ x: e.clientX, y: e.clientY }`, coordonnées écran absolues — pas une
   correction de bug préexistant, juste un changement du nœud DOM qui porte
   l'écouteur).

**Architecture:** `PipelineBuilderPage` s'enveloppe dans
`<div className="-m-6 flex flex-1 flex-col overflow-hidden" onDragOver={...} onDrop={...}>`
(même technique de transition locale que les quatre familles précédentes) et
instancie `TriptychLayout` avec `defaultTabId="canvas"` et trois volets :
**browse** = « Étapes » (`<PipelinePalette />` seul — la palette rend déjà
elle-même ses trois groupes Sources/Transforms/Écritures, pas de wrapper de
labels supplémentaire nécessaire, à la différence d'`AppBuilderPage` qui
empilait deux composants distincts sous « Structure ») ; **work** = « Canevas »
(en-tête local `<h2>` titre seul ; puis `<main>` défilant — le volet `work`
de `TriptychLayout` est `overflow-hidden` par construction, ce plan fournit
donc son propre conteneur de défilement, piège documenté par SP-30d/SP-30e)
contenant `PipelineCanvas` ; **inspect** = « Propriétés » (cf. décisions
explicites 1/2 ci-dessus : bloc nœud sélectionné omis si rien n'est
sélectionné, puis Exécution (`PipelineRunPanel`, si `pk !== null`), puis
Planification (`PipelineScheduleEditor`, si `pk !== null`), puis
`ConfigHistoryPanel` (si `pk !== null`), puis Enregistrer + erreur de
sauvegarde).

**Tech Stack:** React 19, `@tanstack/react-query`, react-router-dom, `@xyflow/react`
(canvas DAG), kit de primitives SP-29b (`shell/src/ui/kit/`), Vitest +
Testing Library, Playwright.

## Global Constraints

- Docs et identifiants de test en français ; code/identifiants en anglais (CLAUDE.md).
- Aucune couleur Tailwind en dur (`slate-*`, `red-*`, `gray-*`, `white`, `black`
  — et, spécifiquement dans ce plan, `blue-500` littéral hors des tokens) dans
  les fichiers touchés : tokens uniquement (`bg-surface`, `text-ink`,
  `text-ink-2`, `text-ink-3`, `border-rule`, `bg-raised`, `bg-sunken`,
  `text-danger`, `text-accent`, `border-accent`, `ring-accent` —
  `shell/src/styles/tokens.css`). **Exception explicitement documentée** (cf.
  décision 3) : les couleurs catégorielles `emerald`/`amber`/`sky` de
  `PipelineCanvas.tsx` (encodage du type de nœud) et les couleurs hex de
  `PipelinePreviewMap.tsx` (rendu cartographique) restent inchangées.
- Aucun ancien import `ui/button`/`ui/dialog`/`ui/input`/`ui/card` ne subsiste
  dans les fichiers touchés par ce plan après leur tâche respective.
- `-m-6` est une technique de transition **locale à `PipelineBuilderPage.tsx`
  seule** dans ce plan, jamais un changement à `AppLayout.tsx`.
- Régression jsdom (piège n°10) : `window.matchMedia` n'existe pas sous
  jsdom — `TriptychLayout` l'appelle via `useNarrowViewport`.
  `PipelineBuilderPage.tsx` ne rendait pas `TriptychLayout` avant ce plan ;
  `PipelineBuilderPage.test.tsx` a déjà un `beforeEach`/`afterEach` pour
  `ResizeObserver` (avec `vi.unstubAllGlobals()` en `afterEach` — ce fichier
  n'a **pas** la dette « stub jamais désinstallé » notée sur
  `MapEditorPage.test.tsx`/`DatasetEditPage.test.tsx`/`AppBuilderPage.test.tsx` ;
  Task 5 étend le `beforeEach` existant plutôt que d'en ajouter un second).
- Pas de changement au cœur (`core/`) dans ce plan — famille Automatisation,
  aucun schéma de permissions concerné. Diff vide attendu (piège n°1 — vide
  parce qu'aucun schéma ne change), vérifié en Task 6 par
  `git status --short core/`.
- E2E : suite **complète** exigée avant tout commit qui change la structure
  DOM de la page (Task 5, Task 6) — pas de liste de specs nommée dans ce
  plan. Recommandation actée par la revue finale de SP-30e (`CLAUDE.md`,
  entrée SP-30e) après que le filet à 5 specs nommées de SP-30c/d/e s'est
  révélé trop étroit trois fois consécutives (piège n°6) : nommer une liste
  crée l'illusion d'un filet suffisant alors que seule la suite complète
  l'est réellement pour une page consommée par ~20 specs indirectement (Nouveau
  → type pipeline, pas uniquement par URL littérale).

---

## Task 1: Shell — kit-ifier `PipelineCanvas.tsx` + `PipelinePalette.tsx` (tokens)

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineCanvas.tsx`
- Modify: `shell/src/builder/pipeline/PipelinePalette.tsx`
- Test: `shell/src/builder/pipeline/PipelineCanvas.test.tsx` (baseline, doit passer sans modification)
- Test: `shell/src/builder/pipeline/PipelinePalette.test.tsx` (baseline, doit passer sans modification)

**Interfaces:**
- Consumes: aucun composant du kit (ni `Button` ni `Panel`) — ces deux fichiers
  n'importaient déjà aucun composant `ui/*` (boutons natifs `<button>`,
  `<div draggable>`), seules leurs classes Tailwind changent.
- Produces: aucune API publique changée — `PipelineCanvas(props)` et
  `PipelinePalette()` inchangées, consommées telles quelles par Task 5.

Ni `PipelineCanvas.tsx` ni `PipelinePalette.tsx` n'importent `ui/dialog`,
`ui/button` ou `ui/input` : ce n'est qu'une passe de tokenisation de couleurs.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx src/builder/pipeline/PipelinePalette.test.tsx
```

Expected: PASS (les deux fichiers de test, aucune modification prévue à leur texte).

- [ ] **Step 2: `PipelineCanvas.tsx` — tokeniser les couleurs de chrome neutre, convertir les deux `blue-500` en `accent`**

Remplacer (ligne 68, anneau de sélection — cf. décision explicite 3) :
```tsx
      className={`relative rounded-md border-2 px-3 py-2 text-xs ${KIND_COLOR[node.kind]} ${selected ? "ring-2 ring-blue-500" : ""}`}
```
par :
```tsx
      className={`relative rounded-md border-2 px-3 py-2 text-xs ${KIND_COLOR[node.kind]} ${selected ? "ring-2 ring-accent" : ""}`}
```

Remplacer (ligne 80, sous-titre de l'op) :
```tsx
      <div className="text-[10px] text-slate-500">{node.op}</div>
```
par :
```tsx
      <div className="text-[10px] text-ink-2">{node.op}</div>
```

Remplacer (ligne 94, spinner « exécution en cours » — cf. décision explicite 3) :
```tsx
          className="absolute -right-2 -top-2 h-3 w-3 animate-spin rounded-full border-2 border-blue-500 border-t-transparent"
```
par :
```tsx
          className="absolute -right-2 -top-2 h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent"
```

Remplacer (ligne 132, bouton « + » d'insertion sur une arête) :
```tsx
            className="h-5 w-5 rounded-full border border-slate-400 bg-white text-xs leading-none hover:bg-slate-100"
```
par :
```tsx
            className="h-5 w-5 rounded-full border border-rule bg-surface text-xs leading-none hover:bg-sunken"
```

Remplacer (ligne 140, menu déroulant d'insertion) :
```tsx
              className="absolute z-10 mt-1 rounded border border-slate-300 bg-white text-xs shadow"
```
par :
```tsx
              className="absolute z-10 mt-1 rounded border border-rule bg-surface text-xs shadow"
```

Remplacer (ligne 147, item de menu) :
```tsx
                    className="block w-full whitespace-nowrap px-2 py-1 text-left hover:bg-slate-100"
```
par :
```tsx
                    className="block w-full whitespace-nowrap px-2 py-1 text-left hover:bg-sunken"
```

`KIND_COLOR` (lignes 48-52) et le badge de comptage de lignes
(`bg-emerald-600 ... text-white`, ligne 85) restent inchangés — cf. décision
explicite 3.

- [ ] **Step 3: `PipelinePalette.tsx` — tokeniser les couleurs de chrome neutre**

Remplacer (ligne 23, titre de section) :
```tsx
          <h3 className="mb-1 font-semibold text-slate-600">{SECTION_LABEL[kind]}</h3>
```
par :
```tsx
          <h3 className="mb-1 font-semibold text-ink-2">{SECTION_LABEL[kind]}</h3>
```

Remplacer (ligne 33, item draggable) :
```tsx
                  className="cursor-grab rounded border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50"
```
par :
```tsx
                  className="cursor-grab rounded border border-rule bg-surface px-2 py-1 hover:bg-sunken"
```

- [ ] **Step 4: Vérifier qu'aucune couleur Tailwind en dur de chrome neutre (hors exemptions décision 3) ne subsiste**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+|ring-(red|slate|blue|gray|black)-[0-9]+' \
  shell/src/builder/pipeline/PipelineCanvas.tsx shell/src/builder/pipeline/PipelinePalette.tsx
```

Expected: aucune sortie. (`amber`/`emerald`/`sky` ne sont volontairement pas
dans ce motif — décision explicite 3.)

- [ ] **Step 5: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx src/builder/pipeline/PipelinePalette.test.tsx
```

Expected: PASS, sans modification aux fichiers de test.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/pipeline/PipelineCanvas.tsx shell/src/builder/pipeline/PipelinePalette.tsx
git commit -m "feat(shell): pipelineCanvas/pipelinePalette — tokens (couleurs de chrome neutre)"
```

---

## Task 2: Shell — kit-ifier `CollectionParamSelect.tsx` + `PipelineNodeInspector.tsx` (tokens)

**Files:**
- Modify: `shell/src/builder/pipeline/CollectionParamSelect.tsx`
- Modify: `shell/src/builder/pipeline/PipelineNodeInspector.tsx`
- Test: `shell/src/builder/pipeline/CollectionParamSelect.test.tsx` (baseline, doit passer sans modification)
- Test: `shell/src/builder/pipeline/PipelineNodeInspector.test.tsx` (baseline, doit passer sans modification)

**Interfaces:**
- Consumes: aucun composant du kit — `PipelineNodeInspector` consomme
  `CollectionParamSelect` (import relatif inchangé), tous deux via des
  contrôles natifs (`<select>`, `<input>`, `<button>`).
- Produces: aucune API publique changée — `CollectionParamSelect({value, onChange,
  variant, ariaLabel})` et `PipelineNodeInspector({node, opEntry, errors,
  onChange})` inchangées, consommées telles quelles par Task 5.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/builder/pipeline/CollectionParamSelect.test.tsx src/builder/pipeline/PipelineNodeInspector.test.tsx
```

Expected: PASS (les deux fichiers de test, aucune modification prévue à leur texte).

- [ ] **Step 2: `CollectionParamSelect.tsx` — tokeniser le `<select>`**

Remplacer (ligne 30) :
```tsx
      className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
```
par :
```tsx
      className="h-9 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
```

- [ ] **Step 3: `PipelineNodeInspector.tsx` — tokeniser les huit occurrences de couleurs en dur**

Remplacer (ligne 23, `KeyValueField`, libellé) :
```tsx
      <span className="text-xs font-medium text-slate-600">{name}</span>
```
par :
```tsx
      <span className="text-xs font-medium text-ink-2">{name}</span>
```

Remplacer (lignes 28 et 39 — chaîne strictement identique pour les deux
`<input>` clé et valeur de `KeyValueField`, `replace_all`) :
```tsx
            className="h-8 w-1/2 rounded border border-slate-300 px-2 text-xs"
```
par :
```tsx
            className="h-8 w-1/2 rounded border border-rule bg-surface px-2 text-xs text-ink"
```

Remplacer (ligne 51, bouton « Ajouter … » de `KeyValueField`) :
```tsx
        className="w-fit text-xs text-blue-600 hover:underline"
```
par :
```tsx
        className="w-fit text-xs text-accent hover:underline"
```

Remplacer (ligne 74, `<input>` de `StringListField`) :
```tsx
        className="h-8 rounded border border-slate-300 px-2"
```
par :
```tsx
        className="h-8 rounded border border-rule bg-surface px-2 text-ink"
```

Remplacer (ligne 121, description de champ sous le contrôle) :
```tsx
        <p className="text-xs text-slate-500">{prop.description}</p>
```
par :
```tsx
        <p className="text-xs text-ink-2">{prop.description}</p>
```

Remplacer (ligne 144, `<select>` d'un champ `enum`) :
```tsx
            className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
```
par :
```tsx
            className="h-9 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
```

Remplacer (ligne 196, `<input>` générique texte/nombre) :
```tsx
          className="h-8 rounded border border-slate-300 px-2"
```
par :
```tsx
          className="h-8 rounded border border-rule bg-surface px-2 text-ink"
```

Remplacer (ligne 217, erreur de validation) :
```tsx
        <p key={err} role="alert" className="text-xs text-red-600">
```
par :
```tsx
        <p key={err} role="alert" className="text-xs text-danger">
```

- [ ] **Step 4: Vérifier qu'aucune couleur Tailwind en dur ne subsiste**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/pipeline/CollectionParamSelect.tsx shell/src/builder/pipeline/PipelineNodeInspector.tsx
```

Expected: aucune sortie.

- [ ] **Step 5: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/pipeline/CollectionParamSelect.test.tsx src/builder/pipeline/PipelineNodeInspector.test.tsx
```

Expected: PASS, sans modification aux fichiers de test.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/pipeline/CollectionParamSelect.tsx shell/src/builder/pipeline/PipelineNodeInspector.tsx
git commit -m "feat(shell): collectionParamSelect/pipelineNodeInspector — tokens"
```

---

## Task 3: Shell — kit-ifier `PipelinePreviewPanel.tsx` (tokens)

**Files:**
- Modify: `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`
- Test: `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx` (baseline, doit passer sans modification)

**Interfaces:**
- Consumes: `PipelinePreviewMap` (import relatif inchangé, aucune modification —
  `PipelinePreviewMap.tsx` n'a aucune couleur Tailwind en dur : ses seules
  couleurs sont des hex de rendu cartographique dans des objets `paint`
  MapLibre, cf. décision explicite 3. Vérifié par grep avant d'écrire ce
  plan, rien à faire dans ce fichier.).
- Produces: aucune API publique changée — `PipelinePreviewPanel({pipelineId,
  nodeId})` inchangée, consommée telle quelle par Task 5.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx
```

Expected: PASS (aucune modification prévue au fichier de test).

- [ ] **Step 2: Tokeniser les quatre occurrences de couleurs en dur**

Remplacer (ligne 20, message d'erreur) :
```tsx
      <p role="alert" className="text-sm text-red-600">
```
par :
```tsx
      <p role="alert" className="text-sm text-danger">
```

Remplacer (ligne 36, bouton bascule « Tableau ») :
```tsx
            className={`rounded px-2 py-1 ${view === "table" ? "bg-slate-200" : ""}`}
```
par :
```tsx
            className={`rounded px-2 py-1 ${view === "table" ? "bg-sunken" : ""}`}
```

Remplacer (ligne 43, bouton bascule « Carte ») :
```tsx
            className={`rounded px-2 py-1 ${view === "map" ? "bg-slate-200" : ""}`}
```
par :
```tsx
            className={`rounded px-2 py-1 ${view === "map" ? "bg-sunken" : ""}`}
```

Remplacer (ligne 64, séparateur de ligne du tableau) :
```tsx
              <tr key={i} className="border-t border-slate-200">
```
par :
```tsx
              <tr key={i} className="border-t border-rule">
```

- [ ] **Step 3: Vérifier qu'aucune couleur Tailwind en dur ne subsiste**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/pipeline/PipelinePreviewPanel.tsx
```

Expected: aucune sortie.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx
```

Expected: PASS, sans modification au fichier de test.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelinePreviewPanel.tsx
git commit -m "feat(shell): pipelinePreviewPanel — tokens"
```

---

## Task 4: Shell — kit-ifier `PipelineRunPanel.tsx` (Button du kit) + `PipelineScheduleEditor.tsx` (tokens)

**Files:**
- Modify: `shell/src/builder/pipeline/PipelineRunPanel.tsx`
- Modify: `shell/src/builder/pipeline/PipelineScheduleEditor.tsx`
- Test: `shell/src/builder/pipeline/PipelineRunPanel.test.tsx` (baseline, doit passer sans modification)
- Test: `shell/src/builder/pipeline/PipelineScheduleEditor.test.tsx` (baseline, doit passer sans modification)

**Interfaces:**
- Consumes: `Button` de `shell/src/ui/kit/Button.tsx` (`PipelineRunPanel`
  seulement — `PipelineScheduleEditor` n'importe aucun composant `ui/*`,
  contrôles natifs uniquement).
- Produces: aucune API publique changée — `PipelineRunPanel({pipelineId,
  onLatestRunChange})` et `PipelineScheduleEditor({value, onChange})`
  inchangées. **Les deux sont partagés avec `VisualQueryWizardPage`**
  (SP-30g+) — cette tâche les rend définitivement kit-ifiés pour les deux
  pages, aucun retravail attendu côté SP-30g sur ces deux fichiers.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineRunPanel.test.tsx src/builder/pipeline/PipelineScheduleEditor.test.tsx
```

Expected: PASS (les deux fichiers de test, aucune modification prévue à leur texte).

- [ ] **Step 2: `PipelineRunPanel.tsx` — import Button du kit**

Remplacer :
```tsx
import { Button } from "../../ui/button";
```
par :
```tsx
import { Button } from "../../ui/kit/Button";
```

- [ ] **Step 3: `PipelineRunPanel.tsx` — tokeniser les quatre couleurs en dur**

Remplacer (ligne 81, erreur de lancement) :
```tsx
        <p role="alert" className="text-red-600 text-xs">
```
par :
```tsx
        <p role="alert" className="text-xs text-danger">
```

Remplacer (ligne 87, séparateur d'un item d'exécution) :
```tsx
          <li key={run.id} className="border-t border-slate-200 pt-1">
```
par :
```tsx
          <li key={run.id} className="border-t border-rule pt-1">
```

Remplacer (ligne 89, horodatage) :
```tsx
            {run.startedAt && <span className="ml-2 text-slate-500">{run.startedAt}</span>}
```
par :
```tsx
            {run.startedAt && <span className="ml-2 text-ink-2">{run.startedAt}</span>}
```

Remplacer (ligne 91, erreur d'une exécution) :
```tsx
              <p role="alert" className="text-red-600">
```
par :
```tsx
              <p role="alert" className="text-danger">
```

- [ ] **Step 4: `PipelineScheduleEditor.tsx` — tokeniser les neuf couleurs en dur**

Remplacer (ligne 89, conteneur) :
```tsx
    <div className="flex flex-col gap-2 border-t border-slate-200 pt-2">
```
par :
```tsx
    <div className="flex flex-col gap-2 border-t border-rule pt-2">
```

Remplacer (ligne 90, libellé de la case à cocher) :
```tsx
      <label className="flex items-center gap-2 text-xs font-medium text-slate-600">
```
par :
```tsx
      <label className="flex items-center gap-2 text-xs font-medium text-ink-2">
```

Remplacer (les cinq occurrences strictement identiques du `<select>` de
mode et des `<input>` d'intervalle/heure/jour, lignes 105/129/141/153/171,
`replace_all`) :
```tsx
              className="h-8 rounded border border-slate-300 px-2"
```
par :
```tsx
              className="h-8 rounded border border-rule bg-surface px-2 text-ink"
```

Remplacer (ligne 185, `<input>` cron avancé — suffixe `font-mono` distinct
de la chaîne ci-dessus, remplacement séparé) :
```tsx
                className="h-8 rounded border border-slate-300 px-2 font-mono"
```
par :
```tsx
                className="h-8 rounded border border-rule bg-surface px-2 font-mono text-ink"
```

Remplacer (ligne 190, erreur de format cron) :
```tsx
                <p role="alert" className="text-red-600">
```
par :
```tsx
                <p role="alert" className="text-danger">
```

- [ ] **Step 5: Vérifier qu'aucune couleur Tailwind en dur ni ancien import ne subsiste**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/pipeline/PipelineRunPanel.tsx shell/src/builder/pipeline/PipelineScheduleEditor.tsx
grep -n 'ui/dialog"\|ui/button"\|ui/input"\|ui/card"' \
  shell/src/builder/pipeline/PipelineRunPanel.tsx shell/src/builder/pipeline/PipelineScheduleEditor.tsx
```

Expected: aucune sortie pour les deux commandes.

- [ ] **Step 6: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/pipeline/PipelineRunPanel.test.tsx src/builder/pipeline/PipelineScheduleEditor.test.tsx
```

Expected: PASS, sans modification aux fichiers de test.

- [ ] **Step 7: Commit**

```bash
git add shell/src/builder/pipeline/PipelineRunPanel.tsx shell/src/builder/pipeline/PipelineScheduleEditor.tsx
git commit -m "feat(shell): pipelineRunPanel/pipelineScheduleEditor — kit Button + tokens"
```

---

## Task 5: Shell — `PipelineBuilderPage` sur `TriptychLayout` (« Étapes / Canevas / Propriétés »)

**Files:**
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`
- Modify: `shell/src/pages/PipelineBuilderPage.test.tsx`

**Interfaces:**
- Consumes: `TriptychLayout` (`shell/src/shell/chrome/TriptychLayout.tsx`,
  `{browse,work,inspect,defaultTabId}` — SP-30a) ; `PipelinePalette`,
  `PipelineCanvas`, `PipelineNodeInspector`, `PipelinePreviewPanel`,
  `PipelineRunPanel`, `PipelineScheduleEditor` (Tasks 1-4, API inchangées) ;
  `ConfigHistoryPanel` (déjà kit-ifié depuis SP-30c) ; `Button` du kit.
- Produces: `PipelineBuilderPage({pk, initialTitle})` — API publique
  inchangée, aucune route dans `shell/src/shell/routes.tsx` ne change.

Cf. « Décisions explicites de ce plan » en tête de document pour la
justification des quatre choix structurants (pas de message de repli
inventé, Enregistrer déménagé en bas du volet Propriétés, couleurs
catégorielles de `PipelineCanvas` non touchées, `onDragOver`/`onDrop`
déplacés sur le conteneur externe).

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx
```

Expected: PASS (10 tests).

- [ ] **Step 2: Étendre le `beforeEach` existant avec le stub `matchMedia`, ajouter le test de dégradation en onglets**

Dans `shell/src/pages/PipelineBuilderPage.test.tsx`, remplacer :
```tsx
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
});
afterEach(() => vi.unstubAllGlobals());
```
par :
```tsx
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. PipelineBuilderPage ne rendait pas
// TriptychLayout avant ce plan, donc ce stub est nouveau dans ce fichier —
// stub local, jamais dans shell/src/test/setup.ts. matches: false => le
// layout "large" (3 volets simultanés), pas les onglets — la valeur par
// défaut de tous les tests existants de ce fichier, qui n'affirment pas
// sur la largeur. vi.unstubAllGlobals() en afterEach existait déjà ici
// avant ce plan (contrairement à MapEditorPage.test.tsx/
// DatasetEditPage.test.tsx/AppBuilderPage.test.tsx) — préservé tel quel.
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
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
  stubMatchMedia(false);
});
afterEach(() => vi.unstubAllGlobals());
```

Ajouter, en fin de fichier, un nouveau test :

```tsx
test("sous viewport étroit, affiche trois onglets Étapes/Canevas/Propriétés avec Canevas actif par défaut", async () => {
  stubMatchMedia(true);
  renderPage(null);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Étapes", "Canevas", "Propriétés"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Canevas");
});
```

- [ ] **Step 3: Lancer les tests, vérifier l'échec du nouveau test (les 10 existants doivent encore passer)**

```bash
cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx
```

Expected: le nouveau test « sous viewport étroit… » FAIL (`PipelineBuilderPage`
ne rend encore aucun `role="tab"`) ; les 10 tests existants PASS (le stub
`matchMedia(false)` ajouté au `beforeEach` ne change le comportement d'aucun
d'eux tant que `PipelineBuilderPage` ne consomme pas encore `useNarrowViewport`).

- [ ] **Step 4: Réécrire `PipelineBuilderPage.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useCreatePipeline,
  usePipelineConfig,
  usePipelineOps,
  useSavePipeline,
} from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import { useItemClient } from "../api/ItemClientProvider";
import type {
  PipelineEdge,
  PipelineNode,
  PipelinePayload,
  PipelineRefreshPolicy,
  PipelineRun,
} from "../api/types";
import { Button } from "../ui/kit/Button";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { PipelineCanvas } from "../builder/pipeline/PipelineCanvas";
import { PipelineNodeInspector } from "../builder/pipeline/PipelineNodeInspector";
import { PipelinePalette, PIPELINE_OP_DND_TYPE } from "../builder/pipeline/PipelinePalette";
import { PipelinePreviewPanel } from "../builder/pipeline/PipelinePreviewPanel";
import { PipelineRunPanel } from "../builder/pipeline/PipelineRunPanel";
import { PipelineScheduleEditor } from "../builder/pipeline/PipelineScheduleEditor";
import { genNodeId, insertNodeOnEdge } from "../builder/pipeline/graphOps";
import { isPipelineValid, validatePipelineGraphLocally } from "../builder/pipeline/validation";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

const EMPTY_PAYLOAD: PipelinePayload = { nodes: [], edges: [] };

// pk === null : brouillon local (/pipelines/new, design SP-15b §2.2) —
// rien n'est persisté avant le premier "Enregistrer" (choix de session : le
// validateur serveur exige déjà ≥1 reader/≥1 writer, donc il n'existe pas de
// payload trivial à créer immédiatement comme pour app/dashboard/map/site).
export function PipelineBuilderPage({
  pk,
  initialTitle,
}: {
  pk: string | null;
  initialTitle?: string;
}) {
  const navigate = useNavigate();
  const { username } = useAuth();
  const client = useItemClient();
  const opsQuery = usePipelineOps();
  const configQuery = usePipelineConfig(pk ?? "", { enabled: pk !== null });
  const createPipeline = useCreatePipeline();
  const savePipeline = useSavePipeline(pk ?? "");

  const [draft, setDraft] = useState<PipelinePayload>(EMPTY_PAYLOAD);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [latestRun, setLatestRun] = useState<PipelineRun | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (pk !== null && configQuery.data) setDraft(configQuery.data);
  }, [pk, configQuery.data]);

  if (pk !== null && configQuery.isLoading) return <p role="status">Chargement…</p>;
  if (opsQuery.isLoading || !opsQuery.data) return <p role="status">Chargement…</p>;

  const catalog = opsQuery.data;
  const validation = validatePipelineGraphLocally(draft.nodes, draft.edges, catalog);
  const valid = isPipelineValid(validation);
  const selectedNode = draft.nodes.find((n) => n.id === selectedNodeId) ?? null;

  function setNodes(nodes: PipelineNode[]) {
    setDraft((d) => ({ ...d, nodes }));
  }
  function setEdges(edges: PipelineEdge[]) {
    setDraft((d) => ({ ...d, edges }));
  }
  function setRefreshPolicy(refreshPolicy: PipelineRefreshPolicy | null) {
    setDraft((d) => ({ ...d, refreshPolicy }));
  }
  function updateSelectedNodeParams(params: Record<string, unknown>) {
    if (!selectedNode) return;
    setNodes(draft.nodes.map((n) => (n.id === selectedNode.id ? { ...n, params } : n)));
  }
  function onInsertOnEdge(edgeId: string, op: string) {
    const kind = catalog[op]?.kind ?? "transform";
    const result = insertNodeOnEdge(draft.nodes, draft.edges, edgeId, {
      id: genNodeId(),
      kind,
      op,
      x: 0,
      y: 0,
      params: {},
      title: op,
    });
    setDraft(result);
  }
  function onDropOnCanvas(op: string, position: { x: number; y: number }) {
    const kind = catalog[op]?.kind ?? "transform";
    setNodes([
      ...draft.nodes,
      { id: genNodeId(), kind, op, x: position.x, y: position.y, params: {}, title: op },
    ]);
  }

  async function onSave() {
    setSaveError(null);
    try {
      if (pk === null) {
        const item = await createPipeline.mutateAsync({
          title: initialTitle ?? "",
          owner: username ?? "",
          pipeline: draft,
        });
        navigate(`/pipelines/${item.pk}/edit`, { replace: true });
        return;
      }
      await savePipeline.mutateAsync(draft);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Échec de l'enregistrement.");
    }
  }

  return (
    <div
      className="-m-6 flex flex-1 flex-col overflow-hidden"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        const op = e.dataTransfer.getData(PIPELINE_OP_DND_TYPE);
        if (!op) return;
        onDropOnCanvas(op, { x: e.clientX, y: e.clientY });
      }}
    >
      <TriptychLayout
        defaultTabId="canvas"
        browse={{
          id: "steps",
          label: "Étapes",
          content: <PipelinePalette />,
        }}
        work={{
          id: "canvas",
          label: "Canevas",
          content: (
            <div className="flex h-full flex-col overflow-hidden">
              <div className="border-b border-rule p-2">
                <h2 className="text-lg font-semibold text-ink">{initialTitle ?? "Pipeline"}</h2>
              </div>
              <main className="flex-1 overflow-auto p-2">
                <PipelineCanvas
                  nodes={draft.nodes}
                  edges={draft.edges}
                  selectedNodeId={selectedNodeId}
                  onSelectNode={setSelectedNodeId}
                  onNodesChange={setNodes}
                  onEdgesChange={setEdges}
                  onInsertOnEdge={onInsertOnEdge}
                  opsCatalog={catalog}
                  nodeStats={latestRun?.nodeStats}
                  runStatus={latestRun?.status}
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
              {selectedNode && catalog[selectedNode.op] && (
                <>
                  <p className="mb-1 text-xs font-medium text-ink-2">Nœud sélectionné</p>
                  <PipelineNodeInspector
                    key={selectedNode.id}
                    node={selectedNode}
                    opEntry={catalog[selectedNode.op]}
                    errors={validation.nodeErrors[selectedNode.id] ?? []}
                    onChange={updateSelectedNodeParams}
                  />
                  {pk !== null && <PipelinePreviewPanel pipelineId={pk} nodeId={selectedNode.id} />}
                </>
              )}
              {pk !== null && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Exécution</p>
                  <PipelineRunPanel pipelineId={pk} onLatestRunChange={setLatestRun} />
                </>
              )}
              {pk !== null && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Planification</p>
                  <PipelineScheduleEditor
                    value={draft.refreshPolicy ?? null}
                    onChange={setRefreshPolicy}
                  />
                </>
              )}
              {pk !== null && (
                <div className="mt-3">
                  <ConfigHistoryPanel
                    pk={pk}
                    currentVersion={null}
                    onRestored={async () => setDraft(await client.getPipelineConfig(pk))}
                  />
                </div>
              )}
              <div className="mt-3 flex flex-col gap-2 border-t border-rule pt-3">
                <Button
                  size="sm"
                  className="w-fit"
                  onClick={() => void onSave()}
                  disabled={!valid || createPipeline.isPending || savePipeline.isPending}
                >
                  Enregistrer
                </Button>
                {saveError && (
                  <p role="alert" className="text-xs text-danger">
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
cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx
```

Expected: PASS — les 10 tests existants (aucun ne cherche une structure DOM
particulière hors des rôles/labels déjà stables) plus le nouveau test des
onglets, soit 11 au total.

- [ ] **Step 6: `tsc --noEmit` + build**

```bash
cd shell && npm run build
```

Expected: PASS. Si le build échoue sur une référence résiduelle à
`ui/button`/`ui/dialog`/`ui/input` dans un fichier de cette famille, c'est un
oubli de Task 1-4 — corriger avant de continuer, ne pas committer un build rouge.

- [ ] **Step 7: E2E — suite complète**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed (référence SP-30e) ou
mieux. Si un total différent apparaît, diagnostiquer contre le fichier
`.spec.ts` précis en échec avant de conclure — ne jamais réajuster
silencieusement le nombre attendu dans un rapport (piège n°6, déjà rencontré
trois fois consécutives sur cette famille de plans).

- [ ] **Step 8: Commit**

```bash
git add shell/src/pages/PipelineBuilderPage.tsx shell/src/pages/PipelineBuilderPage.test.tsx
git commit -m "feat(shell): pipelineBuilderPage sur TriptychLayout (Étapes/Canevas/Propriétés)"
```

---

## Task 6: Vérification finale — suite complète + portes de qualité

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

- [ ] **Step 6: Recherche exhaustive de couleurs Tailwind en dur résiduelles (y compris `ring-`) dans les sept fichiers touchés par ce plan**

```bash
grep -rnE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+|ring-(red|slate|blue|gray|black)-[0-9]+' \
  shell/src/builder/pipeline/PipelineCanvas.tsx shell/src/builder/pipeline/PipelinePalette.tsx \
  shell/src/builder/pipeline/CollectionParamSelect.tsx shell/src/builder/pipeline/PipelineNodeInspector.tsx \
  shell/src/builder/pipeline/PipelinePreviewPanel.tsx shell/src/builder/pipeline/PipelineRunPanel.tsx \
  shell/src/builder/pipeline/PipelineScheduleEditor.tsx shell/src/pages/PipelineBuilderPage.tsx
```

Expected: aucune sortie. (`amber`/`emerald`/`sky` dans `PipelineCanvas.tsx`
et les hex de `PipelinePreviewMap.tsx` — non listé ici, non touché par ce
plan — restent hors motif : décision explicite 3.)

- [ ] **Step 7: Recherche exhaustive de `ui/dialog`/`ui/button`/`ui/input`/`ui/card` résiduels dans les huit fichiers touchés**

```bash
grep -rn 'ui/dialog"\|ui/button"\|ui/input"\|ui/card"' \
  shell/src/builder/pipeline/PipelineCanvas.tsx shell/src/builder/pipeline/PipelinePalette.tsx \
  shell/src/builder/pipeline/CollectionParamSelect.tsx shell/src/builder/pipeline/PipelineNodeInspector.tsx \
  shell/src/builder/pipeline/PipelinePreviewPanel.tsx shell/src/builder/pipeline/PipelineRunPanel.tsx \
  shell/src/builder/pipeline/PipelineScheduleEditor.tsx shell/src/pages/PipelineBuilderPage.tsx
```

Expected: aucune sortie.

Ce plan ne se termine pas par un commit propre — c'est une tâche de
vérification. Si un des steps échoue, revenir à la tâche responsable
(identifiable par le fichier en cause) pour corriger, jamais par un
correctif générique en Task 6.
