# SP-30h — Automatisation, volet 3 (VisualQueryWizardPage) sur le socle triptyque Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Basculer `VisualQueryWizardPage` (troisième et dernière page de la
famille 6 « Automatisation »,
`docs/superpowers/specs/2026-08-30-sp30-bascule-triptyque-design.md` §6.1,
dans l'ordre où la spec les énumère : `PipelineBuilderPage` — SP-30f —, puis
`ReportEditPage` — SP-30g —, puis `VisualQueryWizardPage`) sur
`TriptychLayout` : trois onglets — « Catalogue » (retour au catalogue + fiche
`<dl>` Type/Modifié, visible seulement une fois l'item dataset résolu),
« Requête » (titre, sélection de la collection de base, Filtrer/Joindre/
Résumer), « Réglages » (Planifier, alertes de validation, erreur de
sauvegarde, bouton Créer/Mettre à jour). Ce plan clôt la famille 6.

**Ce que ce plan NE fait PAS** : aucune nouvelle fonctionnalité. En
particulier, `VisualQueryWizardPage` ne gagne pas de `ConfigHistoryPanel` —
elle n'en a jamais eu (à la différence de `ReportEditPage`/
`PipelineBuilderPage`/`DatasetEditPage`), et en ajouter un serait une
fonctionnalité non demandée (piège n°4). Aucun changement à
`compilePipeline.ts`/`inferSchema.ts`/`compileFilter.ts` (logique métier,
hors périmètre d'une bascule de chrome).

**Décisions explicites de ce plan (à ne pas re-débattre en exécution)** :

1. **Aucune maquette de référence pour cette page**, comme pour
   `ReportEditPage` (SP-30g). Reverifié directement sur
   `docs/design/triptyque-geostudio.html` (`grep -n "<!--"` avant d'écrire ce
   plan) : les sept écrans commentés sont CARTE, BUILDER, SQL LAB, PIPELINE,
   TACHES, ADMIN/AUDIT, PARAMETRES (+ CATALOGUE non commenté en tête) — aucun
   écran REQUETE/VisualQuery. `VisualQueryWizardPage` est une page de
   formulaire simple, sans canevas ni panneau-liste métier propre (pas de
   `LayersPanel`/`PipelinePalette` équivalent) : elle suit donc le patron de
   `ReportEditPage`/`DatasetEditPage` — volet `browse` = « Catalogue »
   (retour + `<dl>`), pas un panneau-liste dédié.
2. **`pipelinePk` est nullable** (`/datasets/visual-query/new` : brouillon
   local), comme `PipelineBuilderPage`/`ReportEditPage`. Particularité propre
   à cette page : `pipelinePk` référence l'item **Pipeline**, mais l'item que
   l'utilisateur perçoit comme « son » objet catalogué est le **Dataset**
   produit — le composant récupère déjà cet item séparément
   (`existingDatasetItemQuery`, ligne 81-85 du fichier actuel, utilisé pour
   pré-remplir le champ Titre) car un `Pipeline` ne porte pas de titre. Le
   volet Catalogue réutilise **cette même requête déjà existante** pour sa
   fiche `<dl>`, plutôt que d'ajouter un second `useItem(pipelinePk)` qui
   interrogerait le mauvais item (le Pipeline, pas le Dataset). Aucun
   changement à `shell/src/api/hooks.ts` dans ce plan — à la différence de
   SP-30g (qui a dû étendre `useItem` d'un `enabled`), cette page n'a besoin
   d'aucun nouveau hook.
3. **Les deux retours anticipés existants restent hors `TriptychLayout`**,
   même précédent que `ReportEditPage.tsx` (`if (pk !== null &&
   configQuery.isLoading) return <p role="status">Chargement…</p>;`, jamais
   enveloppé dans le chrome triptyque) : l'alerte `unrecognizedShape` (requête
   modifiée dans l'éditeur avancé, non ouvrable dans l'assistant) et l'écran
   de sondage « Exécution de la requête… » (`createdPipelinePk &&
   createdDatasetPk`) restent des retours bruts, avant toute instanciation de
   `TriptychLayout`. Seul le formulaire en régime stable (le `return` final
   actuel, un simple `<div className="flex flex-col gap-4 p-4">`) devient les
   trois volets.
4. **Répartition des sections entre volets** :
   - **browse = « Catalogue »** : lien « ← Retour au catalogue » (nouveau —
     la page n'en avait aucun) + `<dl>` Type/Modifié, visible seulement si
     `existingDatasetItemQuery.data` est résolu (mode édition uniquement,
     après le second aller-retour réseau) — même garde que la donnée
     existante, aucune nouvelle condition inventée. `<dd>Type</dd>` utilise
     `RESOURCE_TYPE_LABELS[existingDatasetItemQuery.data.resourceType]`
     (`shell/src/api/resourceTypes.ts`), jamais un littéral en dur — ne
     répète pas le défaut noté par CLAUDE.md sur `DatasetEditPage` (SP-30d).
     Vérifié : `RESOURCE_TYPE_LABELS["dataset"]` vaut `"Dataset"`, distinct
     des trois libellés d'onglet de cette page (Catalogue/Requête/Réglages)
     — pas de répétition de la collision documentée sur SP-30g (`"Rapport"`
     ambigu avec l'onglet du même nom).
   - **work = « Requête »** : titre local `<h2 className="text-lg
     font-semibold text-ink">` (pas de `text-xl` : comme `ReportEditPage`/
     `PipelineBuilderPage`, cette page n'a pas de `item.title` réel à
     afficher en grand — le Titre est un champ de formulaire, pas un
     en-tête), champ Titre, sélecteur Collection de base, puis
     Filtrer/Joindre/Résumer (conditionnels à `baseSchema`, logique
     inchangée).
   - **inspect = « Réglages » ** : Planifier (`PipelineScheduleEditor`,
     conditionnel à `baseSchema`, même garde qu'aujourd'hui), puis un bloc
     `border-t border-rule pt-3` avec l'alerte d'incompatibilité de schéma,
     l'erreur de soumission, et le bouton Créer/Mettre à jour — même
     regroupement que le bas du volet Réglages des quatre familles
     précédentes.
5. **Kit-ification préalable de quatre fichiers, dans cet ordre** :
   `QueryFilterBuilder.tsx`, `QueryJoinPicker.tsx`, `QuerySummaryBuilder.tsx`
   (+ le `className` par défaut partagé de `PercentileInput.tsx`, seul
   consommateur : `QuerySummaryBuilder.tsx:119-125` n'override pas
   `className`, à la différence des deux appels de `DataSourcePanel.tsx`
   — vérifié par lecture directe des deux sites d'appel — qui passent
   toujours `className={inputCls}` et ne sont donc affectés par aucun
   changement à `PercentileInput.tsx` dans ce plan), puis
   `VisualQueryWizardPage.tsx` lui-même — même séquence que SP-30g (kit-ifier
   les dépendances avant la page qui les consomme).
6. **Import `Button`/`Input`** : `ui/button` → `ui/kit/Button`, `ui/input` →
   `ui/kit/Input`, dans les quatre fichiers concernés (`QueryFilterBuilder`,
   `QuerySummaryBuilder` importent `Button` ; `VisualQueryWizardPage` importe
   les deux). `QueryJoinPicker.tsx` n'importe ni l'un ni l'autre (contrôles
   natifs seulement) — seule sa tâche de tokenisation de couleurs s'applique.

**Architecture:** `VisualQueryWizardPage` s'enveloppe dans
`<div className="-m-6 flex flex-1 flex-col overflow-hidden">` (même technique
de transition locale que les quatre familles précédentes) et instancie
`TriptychLayout` avec `defaultTabId="query"` et trois volets : **browse** =
« Catalogue » (`Panel` avec lien retour + `<dl>` conditionnelle) ; **work** =
« Requête » (titre local + formulaire, dans un conteneur `overflow-y-auto`
propre — le volet `work` de `TriptychLayout` est `overflow-hidden` par
construction, piège déjà documenté par SP-30d/e/f/g) ; **inspect** =
« Réglages » (Planifier + alertes + Créer/Mettre à jour). Les deux retours
anticipés existants (`unrecognizedShape`, écran de sondage post-création)
restent des retours bruts non enveloppés.

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
- `-m-6` est une technique de transition **locale à
  `VisualQueryWizardPage.tsx` seule** dans ce plan, jamais un changement à
  `AppLayout.tsx`.
- Régression jsdom (piège n°10) : `window.matchMedia` n'existe pas sous
  jsdom — `TriptychLayout` l'appelle via `useNarrowViewport`. Stub local à
  `VisualQueryWizardPage.test.tsx`, **avec** `afterEach(() =>
  vi.unstubAllGlobals())` dès son introduction — jamais dans
  `shell/src/test/setup.ts`.
- Pas de changement au cœur (`core/`) dans ce plan — aucun schéma de
  permissions ni de config concerné. Diff vide attendu (piège n°1 — vide
  parce qu'aucun schéma ne change), vérifié en Task 5 par `git status
  --short core/`. Régénération OpenAPI/TS **non nécessaire** pour la même
  raison.
- E2E : suite **complète** exigée avant tout commit qui change la structure
  DOM de la page — pas de liste de specs nommée dans ce plan
  (recommandation actée par SP-30e/f/g après plusieurs occurrences du piège
  n°6).

---

## Task 1: Shell — kit-ifier `QueryFilterBuilder.tsx` (tokens + import Button)

**Files:**
- Modify: `shell/src/builder/visualQuery/QueryFilterBuilder.tsx`
- Test: `shell/src/builder/visualQuery/QueryFilterBuilder.test.tsx` (baseline, doit passer sans modification)

**Interfaces:**
- Consumes: `Button` du kit (`shell/src/ui/kit/Button.tsx`, déjà utilisé par
  les quatre familles précédentes — API identique à `ui/button.tsx` sur les
  props utilisées ici : `type`, `size`, `variant`, `onClick`, children).
- Produces: aucune API publique changée —
  `QueryFilterBuilder({schema, rows, onChange})` inchangée, consommée telle
  quelle par Task 4.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/builder/visualQuery/QueryFilterBuilder.test.tsx
```

Expected: PASS (3 tests, aucune modification prévue à ce fichier de test).

- [ ] **Step 2: Import `Button` depuis le kit**

Remplacer :
```tsx
import { Button } from "../../ui/button";
```
par :
```tsx
import { Button } from "../../ui/kit/Button";
```

- [ ] **Step 3: Tokeniser les quatre couleurs en dur**

Remplacer (ligne 44, select colonne) :
```tsx
              className="h-8 rounded border border-slate-300 px-2 text-xs"
```
par :
```tsx
              className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
```

Remplacer (ligne 56, select opérateur — **même chaîne exacte**, la remplacer
à sa deuxième occurrence) :
```tsx
              className="h-8 rounded border border-slate-300 px-2 text-xs"
```
par :
```tsx
              className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
```

Remplacer (ligne 69, input valeur — **même chaîne exacte**, troisième
occurrence) :
```tsx
              className="h-8 rounded border border-slate-300 px-2 text-xs"
```
par :
```tsx
              className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
```

Remplacer (ligne 76, bouton natif Supprimer) :
```tsx
              className="text-xs text-red-600"
```
par :
```tsx
              className="text-xs text-danger"
```

- [ ] **Step 4: Vérifier qu'aucune couleur Tailwind en dur ne subsiste**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/visualQuery/QueryFilterBuilder.tsx
```

Expected: aucune sortie.

- [ ] **Step 5: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/visualQuery/QueryFilterBuilder.test.tsx
```

Expected: PASS, sans modification au fichier de test.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/visualQuery/QueryFilterBuilder.tsx
git commit -m "feat(shell): queryFilterBuilder — tokens"
```

---

## Task 2: Shell — kit-ifier `QueryJoinPicker.tsx` (tokens seuls)

**Files:**
- Modify: `shell/src/builder/visualQuery/QueryJoinPicker.tsx`
- Test: `shell/src/builder/visualQuery/QueryJoinPicker.test.tsx` (baseline, doit passer sans modification)

**Interfaces:**
- Consumes: aucun composant du kit — contrôles natifs uniquement, déjà
  vérifié (aucun import `ui/*` dans ce fichier).
- Produces: aucune API publique changée — `QueryJoinPicker({baseSchema,
  joinedSchema, collections, value, onChange})` inchangée, consommée telle
  quelle par Task 4.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/builder/visualQuery/QueryJoinPicker.test.tsx
```

Expected: PASS (3 tests, aucune modification prévue à ce fichier de test).

- [ ] **Step 2: Tokeniser les quatre couleurs en dur**

Remplacer (ligne 29, select collection à joindre) :
```tsx
          className="h-8 rounded border border-slate-300 px-2 text-xs"
```
par :
```tsx
          className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
```

Remplacer (ligne 42, message d'absence de colonne commune) :
```tsx
        <p className="text-xs text-red-600">
```
par :
```tsx
        <p className="text-xs text-danger">
```

Remplacer (ligne 51, select colonne de jointure) :
```tsx
            className="h-8 rounded border border-slate-300 px-2 text-xs"
```
par :
```tsx
            className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
```

Remplacer (ligne 68, select type de jointure) :
```tsx
          className="h-8 rounded border border-slate-300 px-2 text-xs"
```
par :
```tsx
          className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
```

- [ ] **Step 3: Vérifier qu'aucune couleur Tailwind en dur ne subsiste**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/visualQuery/QueryJoinPicker.tsx
```

Expected: aucune sortie.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/visualQuery/QueryJoinPicker.test.tsx
```

Expected: PASS, sans modification au fichier de test.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/visualQuery/QueryJoinPicker.tsx
git commit -m "feat(shell): queryJoinPicker — tokens"
```

---

## Task 3: Shell — kit-ifier `QuerySummaryBuilder.tsx` (tokens + import Button) et `PercentileInput.tsx` (tokens du `className` par défaut)

**Files:**
- Modify: `shell/src/builder/visualQuery/QuerySummaryBuilder.tsx`
- Modify: `shell/src/builder/PercentileInput.tsx`
- Test: `shell/src/builder/visualQuery/QuerySummaryBuilder.test.tsx` (baseline, doit passer sans modification)
- Test: `shell/src/builder/DataSourcePanel.test.tsx` (baseline, doit passer sans modification — vérifie l'absence de régression croisée sur l'autre consommateur de `PercentileInput`)

**Interfaces:**
- Consumes: `Button` du kit ; `PercentileInput`
  (`shell/src/builder/PercentileInput.tsx`, API `{label, value, onCommit,
  className?, placeholder?}` inchangée — seul le **défaut** du paramètre
  `className` change).
- Produces: aucune API publique changée —
  `QuerySummaryBuilder({schema, value, onChange})` inchangée, consommée
  telle quelle par Task 4 ; `PercentileInput` inchangée pour tout appelant
  qui passe déjà `className` explicitement (`DataSourcePanel.tsx`, deux
  sites d'appel, vérifiés avant ce plan — aucun des deux n'omet
  `className`).

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/builder/visualQuery/QuerySummaryBuilder.test.tsx src/builder/DataSourcePanel.test.tsx
```

Expected: PASS (7 + le nombre de tests actuel de `DataSourcePanel.test.tsx`,
aucune modification prévue à ces deux fichiers de test).

- [ ] **Step 2: Import `Button` depuis le kit**

Remplacer, dans `QuerySummaryBuilder.tsx` :
```tsx
import { Button } from "../../ui/button";
```
par :
```tsx
import { Button } from "../../ui/kit/Button";
```

- [ ] **Step 3: Tokeniser les six couleurs en dur de `QuerySummaryBuilder.tsx`**

Remplacer (ligne 77, libellé "Regrouper par") :
```tsx
      <p className="text-xs font-medium text-slate-500">Regrouper par</p>
```
par :
```tsx
      <p className="text-xs font-medium text-ink-2">Regrouper par</p>
```

Remplacer (ligne 89, libellé "Métriques") :
```tsx
      <p className="text-xs font-medium text-slate-500">Métriques</p>
```
par :
```tsx
      <p className="text-xs font-medium text-ink-2">Métriques</p>
```

Remplacer (ligne 94, select fonction) :
```tsx
            className="h-8 rounded border border-slate-300 px-2 text-xs"
```
par :
```tsx
            className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
```

Remplacer (ligne 107, select colonne source — **même chaîne exacte**,
deuxième occurrence) :
```tsx
              className="h-8 rounded border border-slate-300 px-2 text-xs"
```
par :
```tsx
              className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
```

- [ ] **Step 4: Tokeniser le `className` par défaut de `PercentileInput.tsx`**

Remplacer, dans `shell/src/builder/PercentileInput.tsx` :
```tsx
  className = "h-8 w-20 rounded border border-slate-300 px-2 text-xs",
```
par :
```tsx
  className = "h-8 w-20 rounded border border-rule bg-surface px-2 text-xs text-ink",
```

- [ ] **Step 5: Vérifier qu'aucune couleur Tailwind en dur ne subsiste**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/visualQuery/QuerySummaryBuilder.tsx shell/src/builder/PercentileInput.tsx
```

Expected: aucune sortie.

- [ ] **Step 6: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/builder/visualQuery/QuerySummaryBuilder.test.tsx src/builder/DataSourcePanel.test.tsx
```

Expected: PASS, sans modification à ces deux fichiers de test —
`DataSourcePanel.test.tsx` reste vert car ses deux appels à
`PercentileInput` passent toujours `className={inputCls}` (leur propre
tokenisation, déjà faite par SP-30e), donc n'utilisent jamais le défaut
changé au Step 4.

- [ ] **Step 7: Commit**

```bash
git add shell/src/builder/visualQuery/QuerySummaryBuilder.tsx shell/src/builder/PercentileInput.tsx
git commit -m "feat(shell): querySummaryBuilder + percentileInput — tokens"
```

---

## Task 4: Shell — `VisualQueryWizardPage` sur `TriptychLayout` (« Catalogue / Requête / Réglages »)

**Files:**
- Modify: `shell/src/pages/VisualQueryWizardPage.tsx`
- Modify: `shell/src/pages/VisualQueryWizardPage.test.tsx`

**Interfaces:**
- Consumes: `TriptychLayout` (`shell/src/shell/chrome/TriptychLayout.tsx`,
  `{browse,work,inspect,defaultTabId}` — SP-30a) ; `Panel`/`Button`/`Input`
  du kit ; `RESOURCE_TYPE_LABELS` (`shell/src/api/resourceTypes.ts`) ;
  `QueryFilterBuilder`/`QueryJoinPicker`/`QuerySummaryBuilder` (Tasks 1-3,
  API inchangées) ; `PipelineScheduleEditor`/`PipelineRunPanel` (déjà
  kit-ifiés par SP-30f, API inchangées).
- Produces: `VisualQueryWizardPage({pipelinePk, initialTitle})` — API
  publique inchangée, aucune route dans `shell/src/shell/routes.tsx` ne
  change.

Cf. « Décisions explicites de ce plan » en tête de document pour la
justification des six choix structurants.

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/pages/VisualQueryWizardPage.test.tsx
```

Expected: PASS (10 tests).

- [ ] **Step 2: Étendre `VisualQueryWizardPage.test.tsx`**

Remplacer l'import de `vitest` :
```tsx
import { describe, expect, test, vi } from "vitest";
```
par :
```tsx
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";
```

Juste après le bloc `vi.mock("../auth/useAuth", ...)` existant (avant `const
BASE_SCHEMA = ...`), insérer :

```tsx
// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. VisualQueryWizardPage ne rendait pas
// TriptychLayout avant ce plan, donc ce stub est nouveau dans ce fichier —
// stub local, jamais dans shell/src/test/setup.ts. matches: false => le
// layout "large" (3 volets simultanés), pas les onglets — la valeur par
// défaut de tous les tests de ce fichier qui n'affirment pas sur la
// largeur. vi.unstubAllGlobals() en afterEach dès l'introduction du stub.
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
```

En toute fin de fichier (après le dernier `test(...)` du second `describe`),
ajouter trois nouveaux tests : le premier à l'intérieur du second `describe`
existant (« mode édition »), les deux suivants dans un **troisième**
`describe` ouvert après la fermeture du second (dégradation d'affichage et
mode création sont indépendants du mode édition, donc hors de ce bloc) :

```tsx
  test("le volet Catalogue affiche la fiche Type/Modifié une fois l'item dataset résolu", async () => {
    renderWizardEdit();
    await screen.findByText("Modifier la requête");
    await waitFor(() =>
      expect(screen.getByLabelText("Collection de base")).toHaveValue("incidents"),
    );
    expect(await screen.findByText("Dataset")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "← Retour au catalogue" })).toBeInTheDocument();
  });
});

describe("VisualQueryWizardPage — volet Catalogue et dégradation d'affichage", () => {
  test("mode création : le volet Catalogue ne montre aucune fiche d'item avant le premier Créer", async () => {
    renderWizard();
    expect(
      await screen.findByRole("link", { name: "← Retour au catalogue" }),
    ).toBeInTheDocument();
    expect(screen.queryByText("Dataset")).not.toBeInTheDocument();
  });

  test("sous viewport étroit, affiche trois onglets Catalogue/Requête/Réglages avec Requête actif par défaut", async () => {
    stubMatchMedia(true);
    renderWizard();
    const tabs = await screen.findAllByRole("tab");
    expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Requête", "Réglages"]);
    const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
    expect(activeTab).toHaveTextContent("Requête");
  });
```

Ce découpage ferme le second `describe` existant après son premier nouveau
test (d'où le `});` isolé ci-dessus, qui referme le `describe("…mode
édition…")`) et ouvre un troisième `describe` pour les deux tests restants —
vérifier à l'application de ce step que l'indentation et l'accolade de
fermeture du fichier retombent juste (le fichier doit se terminer par
`});\n});` : la fermeture du troisième `describe` puis rien d'autre après).

- [ ] **Step 3: Lancer les tests, vérifier l'échec des trois nouveaux (les 10 existants doivent encore passer)**

```bash
cd shell && npx vitest run src/pages/VisualQueryWizardPage.test.tsx
```

Expected : les 10 tests existants **PASS** (le stub `matchMedia` est sans
effet tant que le composant ne rend pas `TriptychLayout`) ; « le volet
Catalogue affiche la fiche Type/Modifié… » FAIL (pas de `<dl>` ni de lien
retour) ; « mode création : le volet Catalogue ne montre aucune fiche… »
FAIL (le lien « ← Retour au catalogue » n'existe pas encore) ; « sous
viewport étroit… » FAIL (aucun `role="tab"`).

- [ ] **Step 4: Réécrire `VisualQueryWizardPage.tsx`**

Remplacer le bloc d'imports :
```tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/useAuth";
import { useItemClient } from "../api/ItemClientProvider";
import { useCollectionsAdmin, usePipelineConfig } from "../api/hooks";
import type { CollectionSchema, PipelineRefreshPolicy } from "../api/types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { QueryFilterBuilder } from "../builder/visualQuery/QueryFilterBuilder";
import { QueryJoinPicker } from "../builder/visualQuery/QueryJoinPicker";
import { QuerySummaryBuilder } from "../builder/visualQuery/QuerySummaryBuilder";
import { PipelineScheduleEditor } from "../builder/pipeline/PipelineScheduleEditor";
import { PipelineRunPanel } from "../builder/pipeline/PipelineRunPanel";
import { inferOutputColumns } from "../builder/visualQuery/inferSchema";
import { FilterRow, isFilterRowValueValid } from "../builder/visualQuery/compileFilter";
import { InferredSchema, JoinConfig, SummaryConfig } from "../builder/visualQuery/inferSchema";
import {
  VisualQueryState,
  compileVisualQueryToPipeline,
  decompilePipelineToWizardState,
} from "../builder/visualQuery/compilePipeline";
```
par :
```tsx
import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/useAuth";
import { useItemClient } from "../api/ItemClientProvider";
import { useCollectionsAdmin, usePipelineConfig } from "../api/hooks";
import type { CollectionSchema, PipelineRefreshPolicy } from "../api/types";
import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Panel } from "../ui/kit/Panel";
import { QueryFilterBuilder } from "../builder/visualQuery/QueryFilterBuilder";
import { QueryJoinPicker } from "../builder/visualQuery/QueryJoinPicker";
import { QuerySummaryBuilder } from "../builder/visualQuery/QuerySummaryBuilder";
import { PipelineScheduleEditor } from "../builder/pipeline/PipelineScheduleEditor";
import { PipelineRunPanel } from "../builder/pipeline/PipelineRunPanel";
import { inferOutputColumns } from "../builder/visualQuery/inferSchema";
import { FilterRow, isFilterRowValueValid } from "../builder/visualQuery/compileFilter";
import { InferredSchema, JoinConfig, SummaryConfig } from "../builder/visualQuery/inferSchema";
import {
  VisualQueryState,
  compileVisualQueryToPipeline,
  decompilePipelineToWizardState,
} from "../builder/visualQuery/compilePipeline";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
```

Ne rien changer entre le début du corps de `VisualQueryWizardPage` et le
`return` de l'alerte `unrecognizedShape`, **sauf** la couleur :

Remplacer :
```tsx
      <p role="alert" className="text-sm text-red-600">
        Cette requête a été modifiée dans l'éditeur avancé et ne peut plus être ouverte dans
```
par :
```tsx
      <p role="alert" className="text-sm text-danger">
        Cette requête a été modifiée dans l'éditeur avancé et ne peut plus être ouverte dans
```

Ne rien changer entre `const baseSchema` et le `return` de l'écran de
sondage post-création (`if (createdPipelinePk && createdDatasetPk)`) : cette
logique (calcul de `inferredOutput`, `outputSchemaMismatch`, `handleCreate`,
`filtersValid`/`joinValid`/`summaryValid`) reste identique. L'écran de
sondage lui-même reste identique aussi (pas de couleur en dur dedans).

Remplacer le `return` final (le formulaire en régime stable) :
```tsx
  return (
    <div className="flex flex-col gap-4 p-4">
      <h2 className="text-xl font-semibold">
        {pipelinePk !== null ? "Modifier la requête" : "Nouvelle requête visuelle"}
      </h2>
      <label className="flex flex-col gap-1 text-sm">
        Titre
        <Input
          aria-label="Titre"
          value={title}
          onChange={(e) => {
            setTitle(e.target.value);
            setTitleTouched(true);
          }}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Collection de base
        <select
          aria-label="Collection de base"
          className="h-9 rounded-md border border-slate-300 px-3 text-sm"
          value={baseCollectionId}
          onChange={(e) => {
            // Important 3 : un changement direct de collection de base
            // invalide filtres/jointure/résumé (colonnes qui n'existent
            // plus forcément dans la nouvelle collection) — réinitialiser
            // pour éviter un état validé à tort qui échouerait à
            // l'exécution. Le useEffect de décompilation (chargement d'une
            // requête existante) pose ces mêmes champs ensemble et n'a pas
            // besoin de ce garde : ce n'est pas une interaction utilisateur.
            setBaseCollectionId(e.target.value);
            setFilters([]);
            setJoin(null);
            setSummary(null);
          }}
        >
          <option value="">Choisir…</option>
          {(collectionsQuery.data ?? []).map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
      </label>
      {baseSchema && (
        <>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Filtrer</p>
            <QueryFilterBuilder schema={baseSchema} rows={filters} onChange={setFilters} />
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Joindre</p>
            {join ? (
              <div className="flex flex-col gap-2">
                <QueryJoinPicker
                  baseSchema={baseSchema}
                  joinedSchema={joinedSchemaQuery.data ?? null}
                  collections={collectionsQuery.data ?? []}
                  value={join}
                  onChange={setJoin}
                />
                <Button type="button" size="sm" variant="outline" onClick={() => setJoin(null)}>
                  Supprimer la jointure
                </Button>
              </div>
            ) : (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setJoin({ collectionId: "", on: "", how: "inner" })}
              >
                Ajouter une jointure
              </Button>
            )}
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Résumer</p>
            {summary ? (
              <div className="flex flex-col gap-2">
                <QuerySummaryBuilder schema={baseSchema} value={summary} onChange={setSummary} />
                <Button type="button" size="sm" variant="outline" onClick={() => setSummary(null)}>
                  Supprimer le résumé
                </Button>
              </div>
            ) : (
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setSummary({ groupBy: [], metrics: [] })}
              >
                Ajouter un résumé
              </Button>
            )}
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Planifier</p>
            <PipelineScheduleEditor value={refreshPolicy} onChange={setRefreshPolicy} />
          </div>
        </>
      )}
      {pipelinePk !== null && outputSchemaMismatch && (
        <p role="alert" className="text-sm text-red-600">
          La structure de sortie a changé (colonnes ou géométrie) : cette modification ne peut pas
          être enregistrée sur la requête existante. Créez une nouvelle requête à la place.
        </p>
      )}
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
      <Button
        size="sm"
        className="w-fit"
        disabled={
          submitting ||
          !title.trim() ||
          !baseCollectionId ||
          !filtersValid ||
          !joinValid ||
          !summaryValid ||
          (pipelinePk !== null && !existingOutput) ||
          outputSchemaMismatch
        }
        onClick={() => void handleCreate()}
      >
        {pipelinePk !== null ? "Mettre à jour" : "Créer"}
      </Button>
    </div>
  );
}
```
par :
```tsx
  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="query"
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
              {existingDatasetItemQuery.data && (
                <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs text-ink-2">
                  <dt>Type</dt>
                  <dd>{RESOURCE_TYPE_LABELS[existingDatasetItemQuery.data.resourceType]}</dd>
                  <dt>Modifié</dt>
                  <dd>{existingDatasetItemQuery.data.date || "—"}</dd>
                </dl>
              )}
            </Panel>
          ),
        }}
        work={{
          id: "query",
          label: "Requête",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h2 className="text-lg font-semibold text-ink">
                {pipelinePk !== null ? "Modifier la requête" : "Nouvelle requête visuelle"}
              </h2>
              <label className="flex flex-col gap-1 text-sm">
                Titre
                <Input
                  aria-label="Titre"
                  value={title}
                  onChange={(e) => {
                    setTitle(e.target.value);
                    setTitleTouched(true);
                  }}
                />
              </label>
              <label className="flex flex-col gap-1 text-sm">
                Collection de base
                <select
                  aria-label="Collection de base"
                  className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                  value={baseCollectionId}
                  onChange={(e) => {
                    // Important 3 : un changement direct de collection de base
                    // invalide filtres/jointure/résumé (colonnes qui n'existent
                    // plus forcément dans la nouvelle collection) — réinitialiser
                    // pour éviter un état validé à tort qui échouerait à
                    // l'exécution. Le useEffect de décompilation (chargement d'une
                    // requête existante) pose ces mêmes champs ensemble et n'a pas
                    // besoin de ce garde : ce n'est pas une interaction utilisateur.
                    setBaseCollectionId(e.target.value);
                    setFilters([]);
                    setJoin(null);
                    setSummary(null);
                  }}
                >
                  <option value="">Choisir…</option>
                  {(collectionsQuery.data ?? []).map((c) => (
                    <option key={c.id} value={c.id}>
                      {c.title}
                    </option>
                  ))}
                </select>
              </label>
              {baseSchema && (
                <>
                  <div>
                    <p className="mb-1 text-xs font-medium text-ink-2">Filtrer</p>
                    <QueryFilterBuilder schema={baseSchema} rows={filters} onChange={setFilters} />
                  </div>
                  <div>
                    <p className="mb-1 text-xs font-medium text-ink-2">Joindre</p>
                    {join ? (
                      <div className="flex flex-col gap-2">
                        <QueryJoinPicker
                          baseSchema={baseSchema}
                          joinedSchema={joinedSchemaQuery.data ?? null}
                          collections={collectionsQuery.data ?? []}
                          value={join}
                          onChange={setJoin}
                        />
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => setJoin(null)}
                        >
                          Supprimer la jointure
                        </Button>
                      </div>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => setJoin({ collectionId: "", on: "", how: "inner" })}
                      >
                        Ajouter une jointure
                      </Button>
                    )}
                  </div>
                  <div>
                    <p className="mb-1 text-xs font-medium text-ink-2">Résumer</p>
                    {summary ? (
                      <div className="flex flex-col gap-2">
                        <QuerySummaryBuilder
                          schema={baseSchema}
                          value={summary}
                          onChange={setSummary}
                        />
                        <Button
                          type="button"
                          size="sm"
                          variant="outline"
                          onClick={() => setSummary(null)}
                        >
                          Supprimer le résumé
                        </Button>
                      </div>
                    ) : (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={() => setSummary({ groupBy: [], metrics: [] })}
                      >
                        Ajouter un résumé
                      </Button>
                    )}
                  </div>
                </>
              )}
            </div>
          ),
        }}
        inspect={{
          id: "settings",
          label: "Réglages",
          content: (
            <div className="flex flex-col gap-4 p-3">
              {baseSchema && (
                <div>
                  <p className="mb-1 text-xs font-medium text-ink-2">Planifier</p>
                  <PipelineScheduleEditor value={refreshPolicy} onChange={setRefreshPolicy} />
                </div>
              )}
              <div className="flex flex-col gap-2 border-t border-rule pt-3">
                {pipelinePk !== null && outputSchemaMismatch && (
                  <p role="alert" className="text-sm text-danger">
                    La structure de sortie a changé (colonnes ou géométrie) : cette modification
                    ne peut pas être enregistrée sur la requête existante. Créez une nouvelle
                    requête à la place.
                  </p>
                )}
                {error && (
                  <p role="alert" className="text-sm text-danger">
                    {error}
                  </p>
                )}
                <Button
                  size="sm"
                  className="w-fit"
                  disabled={
                    submitting ||
                    !title.trim() ||
                    !baseCollectionId ||
                    !filtersValid ||
                    !joinValid ||
                    !summaryValid ||
                    (pipelinePk !== null && !existingOutput) ||
                    outputSchemaMismatch
                  }
                  onClick={() => void handleCreate()}
                >
                  {pipelinePk !== null ? "Mettre à jour" : "Créer"}
                </Button>
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
cd shell && npx vitest run src/pages/VisualQueryWizardPage.test.tsx
```

Expected: PASS — les 13 tests (10 existants + 3 nouveaux).

- [ ] **Step 6: `tsc --noEmit` + build**

```bash
cd shell && npm run build
```

Expected: PASS. Si le build échoue sur une référence résiduelle à
`ui/button`/`ui/input` dans un fichier de cette famille, c'est un oubli de
Task 1-3 — corriger avant de continuer, ne pas committer un build rouge.

- [ ] **Step 7: E2E — suite complète**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed (référence SP-30g) ou
mieux. `shell/e2e/visual-query.spec.ts` est le spec directement concerné
(crée une requête visuelle via `/datasets/visual-query/new`, sélectionne
« Collection de base », ajoute un filtre, clique « Créer », attend la
redirection vers `/datasets/dataset-1/edit`, rouvre via
`/datasets/visual-query/pipeline-vq1/edit` et vérifie que « Valeur du filtre
1 » a conservé sa valeur) — sous viewport large (défaut Playwright), les
trois volets de `TriptychLayout` sont rendus simultanément, donc aucune
navigation d'onglet n'est nécessaire pour que ces assertions restent
valides. Si un total différent apparaît, diagnostiquer contre le fichier
`.spec.ts` précis en échec avant de conclure — ne jamais réajuster
silencieusement le nombre attendu dans un rapport (piège n°6).

- [ ] **Step 8: Commit**

```bash
git add shell/src/pages/VisualQueryWizardPage.tsx shell/src/pages/VisualQueryWizardPage.test.tsx
git commit -m "feat(shell): visualQueryWizardPage sur TriptychLayout (Catalogue/Requête/Réglages)"
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

- [ ] **Step 6: Recherche exhaustive de couleurs Tailwind en dur résiduelles dans les cinq fichiers touchés par ce plan**

```bash
grep -rnE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/builder/visualQuery/QueryFilterBuilder.tsx \
  shell/src/builder/visualQuery/QueryJoinPicker.tsx \
  shell/src/builder/visualQuery/QuerySummaryBuilder.tsx \
  shell/src/builder/PercentileInput.tsx \
  shell/src/pages/VisualQueryWizardPage.tsx
```

Expected: aucune sortie.

- [ ] **Step 7: Recherche exhaustive de `ui/dialog`/`ui/button`/`ui/input`/`ui/card` résiduels dans les fichiers touchés**

```bash
grep -rn 'ui/dialog"\|ui/button"\|ui/input"\|ui/card"' \
  shell/src/builder/visualQuery/QueryFilterBuilder.tsx \
  shell/src/builder/visualQuery/QueryJoinPicker.tsx \
  shell/src/builder/visualQuery/QuerySummaryBuilder.tsx \
  shell/src/builder/PercentileInput.tsx \
  shell/src/pages/VisualQueryWizardPage.tsx
```

Expected: aucune sortie.

- [ ] **Step 8: Confirmer que `DataSourcePanel.test.tsx` n'a subi aucune régression croisée**

```bash
cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx
```

Expected: PASS — seul consommateur de `PercentileInput` en dehors de ce
plan, doit rester vert sans modification (Task 3, décision explicite 5).

Ce plan ne se termine pas par un commit propre — c'est une tâche de
vérification. Si un des steps échoue, revenir à la tâche responsable
(identifiable par le fichier en cause) pour corriger, jamais par un
correctif générique en Task 5.
