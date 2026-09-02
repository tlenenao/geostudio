# SP-30l — revue transverse de sortie (§7) : Implementation Plan

> **Correction post-exécution (2026-09-02, committée avec ce plan) :**
> l'exécution a dévié de la prémisse de ce plan. En vérifiant réellement le
> critère de sortie §7 « aucun écran ne clippe au-dessus du seuil relevé »,
> le processus a trouvé un vrai bug générique de `TriptychLayout` (famine de
> la colonne centrale par les colonnes latérales), affectant 6 des 8 écrans
> de référence au-dessus du seuil de 640px (seuil lui-même relevé en cours
> d'exécution, depuis 390px). Ce bug n'est PAS corrigé par ce plan. En
> conséquence, malgré le texte de la Task 3 ci-dessous qui instruit
> d'écrire « SP-30 est clos » dans CLAUDE.md, le résultat réel et corrigé
> est que **SP-30 n'est PAS clos**, en attente de ce chantier de suivi —
> voir CLAUDE.md pour l'état actuel faisant autorité. Le corps du plan
> ci-dessous n'a pas été réécrit : il reste tel qu'il a été écrit avant
> cette découverte, comme trace historique de ce qui était planifié.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clore SP-30 en satisfaisant réellement les huit critères de sortie du
§7 de `docs/superpowers/specs/2026-08-30-sp30-bascule-triptyque-design.md` —
pas en les supposant acquis parce que les familles a→k sont closes.

**Architecture:** Revue de vérification, pas de nouvelle fonctionnalité. Trois
tâches : (1) combler le seul vrai trou de couverture trouvé sur le critère 5
(dégradation 390 px) — qui s'avère être un bug réel de seuil, pas seulement un
trou de test ; (2) combler le trou de couverture du critère 8 (badge de rôle
vérifié aux quatre profils) ; (3) vérification finale complète (suites,
portes de qualité, régénération OpenAPI) + clôture documentaire.

Les critères 1, 2, 3, 4, 6, 7 ont été vérifiés par lecture directe du code
avant d'écrire ce plan (piège n°3) et sont **déjà satisfaits** par SP-30a→k :
`AppLayout.tsx` est déjà le chrome triptyque (plus aucune trace du `<nav
class="w-48">` à cinq liens) ; `/tasks`/`/settings` rendent bien un
`EmptyState` ; `CollectionPermissions` existe déjà côté cœur
(`core/app/collections/routes.py`) et `canWrite` a disparu de son payload (les
deux occurrences restantes de la chaîne `canWrite` dans le dépôt sont un champ
sans rapport dans un snapshot d'export statique figé et le nom d'une variable
locale dérivée de `hasPermission` dans `form.tsx` — pas le payload
collections) ; `ItemActions.tsx` regroupe déjà Modifier/Publier/Miniature sous
un seul `<Locked>` (commit `2336eb7a`, SP-30a). La tâche 3 les re-vérifie
quand même mécaniquement (suites + grep), sans réouvrir de code sur ces
points sauf découverte contraire.

**Tech Stack:** React 19 + TypeScript (shell), Playwright (E2E), Vitest
(unitaire shell), FastAPI/pytest (cœur, non touché par ce plan sauf
régénération de vérification).

## Global Constraints

- Identifiants de test et messages utilisateur en **français** ; code en
  anglais (CLAUDE.md, « Comment on travaille »).
- Commits **conventional**, petits, un sujet par tâche.
- `npm run test`/`npm run e2e`/`uv run pytest` doivent rester verts après
  chaque tâche (piège n°6 : lancer la suite complète avant de clore, pas
  seulement le fichier touché).
- Aucun composant dédié par écran pour la dégradation 390 px — le mécanisme
  générique (`TriptychLayout`/`useNarrowViewport`/`BottomNav`) reste la seule
  source de vérité (§2.1.4 de la spec) ; ce plan ne touche **pas** au layout
  de chaque page, seulement au seuil du hook générique.
- Pas de nouvelle capacité, pas de nouveau champ de payload : ce plan ne
  touche aucun fichier sous `core/` en dehors des commandes de vérification de
  la tâche 3 (aucune modification de schéma attendue → diff OpenAPI/TS vide,
  et c'est le résultat correct, pas un oubli — piège n°1 dans son cas
  d'exception documentée).

---

## Contexte vérifié avant d'écrire ce plan

`shell/src/shell/chrome/useNarrowViewport.ts` définit aujourd'hui :

```ts
const QUERY = "(max-width: 389px)";
```

Le critère de sortie §7.5 de la spec demande : « 390 px vérifié sans casse sur
les 8 écrans de référence des maquettes » — et la maquette elle-même titre
cette section « Sur écran étroit — **390 px, sans casse** »
(`docs/design/triptyque-geostudio.html:1185`). Avec `max-width: 389px`, un
viewport **exactement à 390 px** (la largeur CSS réelle des iPhone 12/13/14,
et la largeur que toute vérification littérale « à 390 px » va utiliser) est
classé **large**, pas étroit : `AppLayout` rend `DomainBar` au lieu de
`BottomNav`, et `TriptychLayout` rend sa grille trois colonnes
(`grid-cols-[minmax(220px,280px)_1fr_minmax(260px,320px)]`) au lieu des
onglets. Cette grille a un minimum incompressible de 220 px + 260 px = 480 px
sur ses deux colonnes latérales seules — largement plus que les 390 px
disponibles. Autrement dit : **aucun test qui vérifie littéralement "390 px"
ne peut passer avec le seuil actuel**, quel que soit l'écran. C'est un
véritable bug de borne (off-by-one), invisible à toute la suite unitaire
existante parce que chaque test de composant stub `window.matchMedia` avec
une valeur `matches` fixe (jamais la vraie chaîne de requête, piège n°10) —
seul un test Playwright avec un vrai viewport peut le voir, ce qu'aucun test
existant ne fait aujourd'hui (`e2e/responsive.spec.ts` teste une
fonctionnalité sans rapport, la position des widgets par breakpoint du
builder d'app).

Les huit écrans de référence de la maquette (section « Le même gabarit, huit
fois », `docs/design/triptyque-geostudio.html:492-965`, plus le catalogue en
forme pleine à la ligne 367) et leur route la plus simple à atteindre en E2E
mock (vérifiée par lecture directe des routes et des fixtures E2E
existantes) :

| Écran de référence | Route | Fixture nécessaire |
|---|---|---|
| Catalogue | `/` | aucune (mockCore par défaut) |
| Cartes | `/maps/map-1` | item `map-1`, déjà câblé dans `e2e/mocks.ts` (consommé par `e2e/map-popup.spec.ts`) |
| Apps & sites | `/apps/1/edit` | item `pk=1` (app « Alpha »), déjà dans la fixture `ALL` de `e2e/mocks.ts` |
| Analytique | `/analytics/sql` | `GET /me` avec `isAnalyst: true` (route protégée par `RequireRole`) |
| Automatisation | `/pipelines/new` | aucune — `PipelineNewRoute` rend `PipelineBuilderPage pk={null}`, pas de fetch d'item |
| Tâches | `/tasks` | aucune (`EmptyState`, pas de `TriptychLayout`) |
| Administration | `/admin/extensions` | `GET /me` avec `isAdmin: true` (route protégée par `RequireRole`) |
| Paramètres | `/settings` | aucune (`EmptyState`, pas de `TriptychLayout`) |

---

## Task 1 : corriger le seuil de `useNarrowViewport` et prouver les 8 écrans sans débordement à 390 px

**Files:**
- Modify: `shell/src/shell/chrome/useNarrowViewport.ts`
- Modify: `shell/src/shell/chrome/useNarrowViewport.test.ts` (titres de test à
  corriger, la borne change de sens)
- Create: `shell/e2e/triptych-narrow.spec.ts`

**Interfaces:**
- Consomme : `useNarrowViewport()` (signature inchangée, `(): boolean`),
  `mockCore(page)` (`shell/e2e/mocks.ts`, déjà existant).
- Ne produit rien de nouveau pour les tâches suivantes (tâche indépendante).

- [ ] **Step 1: Écrire le test E2E qui échoue avec le seuil actuel**

Créer `shell/e2e/triptych-narrow.spec.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

const NARROW_WIDTH = 390;
const NARROW_HEIGHT = 844;

async function expectNoHorizontalOverflow(page: Page) {
  const overflow = await page.evaluate(() => {
    const doc = document.documentElement;
    return doc.scrollWidth - doc.clientWidth;
  });
  expect(overflow).toBeLessThanOrEqual(1);
}

function meRoute(page: Page, overrides: Record<string, boolean>) {
  return page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock",
        username: "mockuser",
        firstName: "Mock",
        lastName: "User",
        email: null,
        tenantId: "t-mock",
        isAdmin: false,
        isAnalyst: false,
        hasAnyEditorRole: true,
        version: "0.1.0",
        tenantSlug: "demo",
        ...overrides,
      },
    });
  });
}

const SCREENS: Array<{
  name: string;
  path: string;
  before?: (page: Page) => Promise<void>;
}> = [
  { name: "Catalogue", path: "/" },
  { name: "Cartes", path: "/maps/map-1" },
  { name: "Apps & sites", path: "/apps/1/edit" },
  { name: "Analytique", path: "/analytics/sql", before: (p) => meRoute(p, { isAnalyst: true }) },
  { name: "Automatisation", path: "/pipelines/new" },
  { name: "Tâches", path: "/tasks" },
  { name: "Administration", path: "/admin/extensions", before: (p) => meRoute(p, { isAdmin: true }) },
  { name: "Paramètres", path: "/settings" },
];

for (const screen of SCREENS) {
  test(`${screen.name} à 390 px : barre de navigation basse, aucun débordement horizontal`, async ({
    page,
  }) => {
    await page.setViewportSize({ width: NARROW_WIDTH, height: NARROW_HEIGHT });
    await mockCore(page);
    if (screen.before) {
      await screen.before(page);
    }
    await page.goto(screen.path);

    await expect(page.getByRole("navigation", { name: "Navigation" })).toBeVisible();
    await expectNoHorizontalOverflow(page);

    const tabs = page.getByRole("tab");
    const tabCount = await tabs.count();
    for (let i = 0; i < tabCount; i++) {
      await tabs.nth(i).click();
      await expectNoHorizontalOverflow(page);
    }
  });
}
```

- [ ] **Step 2: Lancer ce fichier seul et constater l'échec**

Run: `cd shell && npx playwright test e2e/triptych-narrow.spec.ts`
Expected: FAIL sur les 8 cas — `getByRole("navigation", { name: "Navigation"
})` introuvable (le seuil actuel classe 390 px comme large, donc `AppLayout`
rend `DomainBar`, pas `BottomNav`), et/ou débordement horizontal détecté sur
les écrans qui rendent la grille trois colonnes.

- [ ] **Step 3: Corriger le seuil**

Dans `shell/src/shell/chrome/useNarrowViewport.ts`, remplacer :

```ts
const QUERY = "(max-width: 389px)";
```

par :

```ts
const QUERY = "(max-width: 390px)";
```

- [ ] **Step 4: Corriger les titres du test unitaire du hook**

Dans `shell/src/shell/chrome/useNarrowViewport.test.ts`, ces deux tests
mockent `window.matchMedia` avec une valeur `matches` fixe — ils ne testent
jamais la chaîne de requête elle-même, donc rien ne casse, mais leurs titres
décrivaient l'ancienne borne. Remplacer :

```ts
test("retourne false par défaut au-dessus de 390 px", () => {
```

par :

```ts
test("retourne false par défaut strictement au-dessus de 390 px", () => {
```

et :

```ts
test("retourne true sous 390 px et suit les changements", () => {
```

par :

```ts
test("retourne true à 390 px ou en-dessous, et suit les changements", () => {
```

- [ ] **Step 5: Relancer le test unitaire du hook**

Run: `cd shell && npx vitest run src/shell/chrome/useNarrowViewport.test.ts`
Expected: PASS (2 tests) — ces tests ne dépendent que de la valeur `matches`
mockée, pas du seuil réel.

- [ ] **Step 6: Relancer le test E2E et confirmer les 8 cas verts**

Run: `cd shell && npx playwright test e2e/triptych-narrow.spec.ts`
Expected: PASS (8 tests). Si un écran échoue encore sur le débordement
horizontal (pas sur l'absence de `BottomNav`), c'est un vrai défaut de mise en
page propre à cet écran (pas le seuil) — le diagnostiquer avec
`page.evaluate` pour lister les éléments dont `scrollWidth` dépasse
`innerWidth` avant de conclure, ne pas supposer que c'est le même bug.

- [ ] **Step 7: Suite complète shell (piège n°6)**

Run: `cd shell && npm run test && npm run e2e`
Expected: 0 failed. Le nombre total de tests E2E augmente de 8 par rapport à
la référence CLAUDE.md (118 passed / 4 skipped avant ce plan).

- [ ] **Step 8: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/shell/chrome/useNarrowViewport.ts \
        shell/src/shell/chrome/useNarrowViewport.test.ts \
        shell/e2e/triptych-narrow.spec.ts
git commit -m "fix(shell): useNarrowViewport bascule à 390 px inclus, pas 389

390 px est la largeur CSS réelle des iPhone 12/13/14 et le seuil documenté
par la maquette/spec SP-30 (§7.5) : à ce seuil exact, la grille triptyque
trois colonnes (minimum 480px sur ses deux volets latéraux) ne peut pas
tenir. Le seuil (max-width: 389px) classait 390 px comme large — corrigé.
Preuve : e2e/triptych-narrow.spec.ts, 8 écrans de référence de la maquette,
aucun débordement horizontal à ce viewport."
```

---

## Task 2 : couverture du badge de rôle sur les quatre profils (critère §7.8)

**Files:**
- Modify: `shell/src/shell/chrome/AccountMenu.test.tsx`
- Create: `shell/e2e/account-badge.spec.ts`

**Interfaces:**
- Consomme : `AccountMenu` (`shell/src/shell/chrome/AccountMenu.tsx`, déjà
  écrit, pas modifié par cette tâche — `roleLabel()` est déjà correct pour
  les quatre cas) ; `mockCore(page)`.
- Indépendante de la tâche 1.

- [ ] **Step 1: Compléter la couverture unitaire (cas Analyste manquant)**

Dans `shell/src/shell/chrome/AccountMenu.test.tsx`, `roleLabel()` gère déjà
`isAdmin`/`isAnalyst`/`hasAnyEditorRole`/lecteur, mais le fichier ne teste que
Lecteur, Créateur et Administrateur — pas Analyste seul. Ajouter, à la suite
du dernier `test(...)` du fichier :

```ts
test(
  "affiche Analyste pour un compte analyste non admin",
  async () => {
    server.use(
      http.get("https://core.test/me", () =>
        meResponse({ isAnalyst: true, hasAnyEditorRole: true }),
      ),
    );
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Compte" }));
    expect(await screen.findByText("Analyste")).toBeInTheDocument();
  },
  OPEN_TIMEOUT,
);
```

- [ ] **Step 2: Lancer le fichier et confirmer qu'il passe**

Run: `cd shell && npx vitest run src/shell/chrome/AccountMenu.test.tsx`
Expected: PASS (4 tests). `roleLabel()` n'est pas modifié par cette tâche —
ce test caractérise un comportement déjà correct, il ferme un trou de
couverture, pas un bug.

- [ ] **Step 3: Écrire l'audit E2E des quatre profils (critère littéral §7.8 : « vérifié par les comptes de test E2E admin/analyste/créateur/lecteur-simulé »)**

Créer `shell/e2e/account-badge.spec.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

function meRoute(page: Page, overrides: Record<string, boolean>) {
  return page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock",
        username: "mockuser",
        firstName: "Mock",
        lastName: "User",
        email: null,
        tenantId: "t-mock",
        isAdmin: false,
        isAnalyst: false,
        hasAnyEditorRole: false,
        version: "0.1.0",
        tenantSlug: "demo",
        ...overrides,
      },
    });
  });
}

const CASES: Array<{ profile: string; overrides: Record<string, boolean>; badge: string }> = [
  {
    profile: "administrateur",
    overrides: { isAdmin: true, isAnalyst: true, hasAnyEditorRole: true },
    badge: "Administrateur",
  },
  {
    profile: "analyste",
    overrides: { isAnalyst: true, hasAnyEditorRole: true },
    badge: "Analyste",
  },
  {
    profile: "créateur",
    overrides: { hasAnyEditorRole: true },
    badge: "Créateur",
  },
  {
    profile: "lecteur (simulé — aucun rôle éditeur, ni admin, ni analyste)",
    overrides: {},
    badge: "Lecteur",
  },
];

for (const { profile, overrides, badge } of CASES) {
  test(`le badge de rôle affiche « ${badge} » pour un compte ${profile}`, async ({ page }) => {
    await mockCore(page);
    await meRoute(page, overrides);
    await page.goto("/");
    await page.getByRole("button", { name: "Compte" }).click();
    await expect(page.getByText(badge, { exact: true })).toBeVisible();
  });
}
```

- [ ] **Step 4: Lancer ce fichier seul**

Run: `cd shell && npx playwright test e2e/account-badge.spec.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Suite complète shell (piège n°6)**

Run: `cd shell && npm run test && npm run e2e`
Expected: 0 failed. Le nombre total de tests E2E augmente de 4 par rapport à
l'état après la tâche 1.

- [ ] **Step 6: Commit**

```bash
cd /home/lenen/projets/geostudio
git add shell/src/shell/chrome/AccountMenu.test.tsx shell/e2e/account-badge.spec.ts
git commit -m "test(shell): couvre le badge de rôle aux quatre profils (SP-30 §7.8)

Unitaire : cas Analyste manquant sur AccountMenu.test.tsx. E2E : nouveau
e2e/account-badge.spec.ts, un test par profil (admin/analyste/créateur/
lecteur-simulé) contre un vrai /me mocké — c'est le texte littéral du
critère de sortie §7.8 de la spec SP-30, jusqu'ici vérifié seulement par
des tests unitaires avec des comptes MSW, jamais par un compte de test
E2E dédié à cette question précise."
```

---

## Task 3 : vérification finale complète et clôture documentaire de SP-30

**Files:**
- Modify: `CLAUDE.md` (entrée `### Livré`, section `### À venir`)
- Pas d'autre fichier de code attendu — cette tâche ne fait que vérifier et
  documenter. Si une vérification échoue, revenir en tâche 1/2 pour corriger
  avant de continuer (ne pas improviser un correctif en tâche 3).

**Interfaces:** aucune — tâche de clôture.

- [ ] **Step 1: Vérifier mécaniquement les critères déjà établis par lecture de code (1, 2, 6, 7)**

```bash
cd /home/lenen/projets/geostudio
# Critère 1 : plus aucune trace de l'ancien chrome à cinq liens.
grep -rn "w-48" shell/src/shell/AppLayout.tsx
# Expected: aucune correspondance (exit code 1).

# Critère 6 : canWrite absent du payload collections et de son type shell.
grep -rn "canWrite" core/app/collections/ shell/src/api/types.ts
# Expected: aucune correspondance (exit code 1).

# Critère 7 : ItemActions ne rend plus qu'un seul groupe Locked pour les
# trois actions Modifier/Publier/Miniature.
grep -n "Locked" shell/src/shell/ItemActions.tsx
# Expected: une seule occurrence de <Locked ...> dans le JSX (hors import).
```

Expected: les trois vérifications confirment ce que ce plan affirme en
introduction. Si l'une échoue, c'est que le code a régressé depuis
l'écriture de ce plan — traiter comme un vrai défaut, pas comme un critère
« déjà acquis » à ignorer.

- [ ] **Step 2: Régénérer OpenAPI + types TS et confirmer un diff vide (critère 4)**

```bash
cd /home/lenen/projets/geostudio/core
PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
git diff --stat -- core/openapi.json
cd ../shell
npm run gen:api-types
git diff --stat -- src/api/generated/core-schema.d.ts
```

Expected: **diff vide sur les deux fichiers**. Ce plan ne touche aucun modèle
ni aucune route du cœur — un diff non vide ici serait la preuve d'une
dérive déjà présente sur `dev` avant ce plan, à traiter séparément (hors
périmètre de cette tâche, mais à signaler explicitement dans le commit de
clôture plutôt que tue).

- [ ] **Step 3: Suite complète et portes de qualité**

```bash
cd /home/lenen/projets/geostudio/shell
npm run test
npm run e2e
npm run build
npm run lint && npm run format:check
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold

cd ../core
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot
uv run lint-imports
uv run pytest
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold

cd ..
uvx pre-commit run --all-files
```

Expected: 0 échec sur toutes les commandes (les deux échecs préexistants
documentés dans CLAUDE.md — `test_scope_preserves_original_sql_error`
intermittent et `test_every_compose_substitution_is_documented` — restent
tolérés, ne pas les imputer à ce plan) ; couverture shell ≥ 88 %, couverture
cœur ≥ 85 % ; `npm run e2e` : 0 failed, total = 118 + 8 (tâche 1) + 4 (tâche
2) = 130 passed / 4 skipped si aucun autre spec n'a bougé entre-temps —
recompter réellement plutôt que supposer ce total si la suite a évolué en
parallèle (session concurrente, cf. piège n°9).

- [ ] **Step 4: Mettre à jour CLAUDE.md — clôturer SP-30**

Ajouter à la fin de la liste `### Livré` (juste après l'entrée SP-30k) :

```markdown
- **SP-30l** (3 tâches, revue transverse de sortie — §7 de la spec, clôt
  SP-30) — les huit critères de sortie vérifiés un par un, pas supposés
  acquis parce que les neuf familles et le chrome sont clos : 1 bug réel
  trouvé et corrigé (`useNarrowViewport` bascule sous `max-width: 389px`,
  classant 390 px — la largeur CSS réelle des iPhone 12/13/14 et le seuil
  que la maquette elle-même nomme — comme *large* plutôt qu'étroit ; aucun
  test unitaire existant ne pouvait le voir, chacun stubbant
  `window.matchMedia` avec une valeur fixe plutôt que la vraie chaîne de
  requête, piège n°10 — seul un test Playwright à viewport réel l'a
  révélé), corrigé à `max-width: 390px`, preuve par
  `e2e/triptych-narrow.spec.ts` sur les 8 écrans de référence de la
  maquette. Second trou comblé : le badge de rôle (§7.8) n'était vérifié
  que par des tests unitaires MSW, jamais par un compte de test E2E dédié
  à cette question précise — `e2e/account-badge.spec.ts` couvre désormais
  les quatre profils (admin/analyste/créateur/lecteur-simulé) contre un
  vrai `/me` mocké, plus le cas Analyste manquant sur
  `AccountMenu.test.tsx`. Les six autres critères (chrome neuf partout,
  neuf domaines navigables, suites + portes de qualité vertes,
  OpenAPI/types à jour, `CollectionPermissions` sans `canWrite`,
  `ItemActions` sans raison de verrou dupliquée) étaient déjà acquis par
  SP-30a→k, re-vérifiés mécaniquement plutôt que supposés. E2E 118/4/0 →
  **130/4/0**. **SP-30 est clos.**
```

Puis remplacer le premier paragraphe de la section `### À venir` (celui qui
commence par « **SP-30** : réécriture des écrans... ») par :

```markdown
- **SP-30 est clos** (SP-30a→l). Les neuf familles du §6.1, le dernier
  reliquat nommé du §2.1 (chrome) et les huit critères de sortie du §7 sont
  tous vérifiés. Reste, hors traitement par aucun plan SP-30 à ce jour :
```

(en conservant tel quel tout le texte qui suit déjà ce paragraphe dans le
fichier — la liste des permissions de collection/profil Lecteur restants,
la dette de tokens `LayersPanel`, les suivis Minor accumulés SP-29b→SP-30k,
etc. — ce sont des chantiers réels pour SP-31+, pas des critères SP-30
manquants).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add CLAUDE.md
git commit -m "docs: clôt SP-30 — revue transverse de sortie (§7), tous critères vérifiés"
```

---

## Self-Review

- **Couverture de la spec** : les 8 critères du §7 sont chacun couverts par
  une étape de vérification explicite (critères 1/2/6/7 en tâche 3 step 1,
  critère 3 en tâche 3 step 3, critère 4 en tâche 3 step 2, critère 5 en
  tâche 1, critère 8 en tâche 2).
- **Pas de placeholder** : chaque étape contient soit du code complet, soit
  une commande exacte avec un résultat attendu concret.
- **Cohérence des types/noms** : `meRoute()` a la même forme dans les deux
  specs E2E créées (tâches 1 et 2) — dupliquée plutôt que partagée via un
  helper commun de `e2e/mocks.ts`, décision assumée : ces deux fichiers n'ont
  en commun que cette fonction de 15 lignes, et `e2e/mocks.ts` est déjà un
  fichier volumineux partagé par toute la suite (YAGNI — pas d'abstraction
  pour un usage à deux occurrences dans deux fichiers indépendants).
