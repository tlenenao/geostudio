# SP-30i — Analytique (SqlLabPage) sur le socle triptyque Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Basculer `SqlLabPage` (famille 7 « Analytique »,
`docs/superpowers/specs/2026-08-30-sp30-bascule-triptyque-design.md` §6.1 —
première famille traitée après la clôture complète de la famille 6 par
SP-30h) sur `TriptychLayout` : trois onglets — « Catalogue » (retour au
catalogue seul, aucune fiche `<dl>` — cette page n'a jamais eu d'item),
« Requête » (titre, éditeur SQL, bouton Exécuter, erreur, tableau de
résultat — contenu existant, inchangé), « Historique » (liste des requêtes
passées, déplacée depuis le bas de la page). Le plan retire aussi
l'unique comparaison de droits en dur de cette page
(`meQuery.data?.isAnalyst !== true`, `SqlLabPage.tsx:40`) au profit d'un
nouveau garde générique au niveau route, `RequireRole`, réutilisable tel
quel par les trois pages d'administration de la famille 8 (SP-30j).

**Ce que ce plan NE fait PAS** : aucune nouvelle fonctionnalité. En
particulier :
- Pas d'arborescence de schémas/tables, pas de statistiques de colonne
  sélectionnée (type, distinctes, nulls, distribution), pas de bouton
  « Enregistrer comme dataset », pas d'export CSV. La maquette
  `docs/design/triptyque-geostudio.html:639-714` (bloc `<!-- SQL LAB -->`)
  montre tout cela — c'est la cible **long terme** du domaine Analytique
  (§4 de `docs/superpowers/specs/2026-08-29-refonte-ui-triptyque-design.md`),
  pas le périmètre de SP-30. La spec SP-30 elle-même l'exclut explicitement :
  « Toute nouvelle capacité (…) : SP-31/32/33 » (§2.2, hors périmètre). Ce
  plan reloge l'éditeur/résultat/historique **existants** dans le chrome
  triptyque, rien de plus — même restriction que SP-30g/h vis-à-vis de leurs
  pages respectives.
- Pas de champs « Limite »/« Délai max »/« Moteur » dans l'onglet Historique
  malgré leur présence dans la maquette (bloc « Requête » de l'inspecteur,
  ligne 702-704) : ce ne sont pas des réglages réels aujourd'hui (aucune API
  ne les expose), les inventer serait une fonctionnalité non demandée
  (piège n°4).
- Aucun changement à `AppLayout.tsx`, à `capabilities.ts`, ni aux trois
  pages d'administration (`AdminExtensionsPage.tsx`,
  `CollectionsAdminPage.tsx`, `HarvestSourcesAdminPage.tsx`) : ce sont la
  famille 8 (SP-30j), hors périmètre de ce plan. `RequireRole` (Task 1) est
  construit générique pour qu'elles le consomment sans modification, sur le
  même principe que la kit-ification de `PipelineRunPanel`/
  `PipelineScheduleEditor` par SP-30f, réutilisée sans retouche par SP-30g/h.
- Aucun changement au cœur (`core/`) : ni schéma, ni endpoint. Diff vide
  attendu sur `core/`, pas de régénération OpenAPI/TS nécessaire (rien ne
  change côté serveur).

**Décisions explicites de ce plan (à ne pas re-débattre en exécution) :**

1. **`SqlLabPage` n'a jamais eu d'item catalogué** (pas de `pk`, pas
   d'`useItem`) — à la différence des quatre familles précédentes
   (`DatasetEditPage`/`PipelineBuilderPage`/`ReportEditPage`/
   `VisualQueryWizardPage`, toutes liées à un item même en mode brouillon).
   L'onglet **browse = « Catalogue »** ne comporte donc qu'un lien de
   retour, sans `<dl>` Type/Modifié (rien à afficher) — patron le plus
   proche est `DatasetEditPage`/`ReportEditPage` moins la fiche, pas une
   nouvelle idiome.
2. **L'onglet inspect n'est PAS appelé « Réglages »**, contrairement aux
   quatre familles précédentes. Cette page n'a ni persistance, ni
   planification, ni bouton Enregistrer — seulement l'historique des
   requêtes exécutées, déjà rendu en bas de page aujourd'hui. Un onglet
   nommé « Réglages » contenant uniquement une liste d'historique serait
   trompeur ; il est nommé **« Historique »**, décrivant exactement son seul
   contenu. Premier écart de nommage de la série SP-30 sur ce point précis,
   documenté ici plutôt que répété silencieusement.
3. **Règle « l'inspecteur n'est jamais vide » (spec design §3.3)** :
   quand `history` est vide (aucune requête exécutée depuis l'ouverture ou
   depuis la dernière purge du `localStorage`), l'onglet Historique affiche
   `EmptyState` du kit (`title="Aucune requête exécutée pour l'instant."`)
   plutôt qu'un volet blanc — la seule concession à la doctrine de
   l'inspecteur permise sans construire les statistiques de colonne
   mentionnées par la maquette (Décision explicite ci-dessus, point 1 de la
   section « Ce que ce plan NE fait PAS »).
4. **`RequireRole` remplace l'unique occurrence de comparaison de droits en
   dur de cette famille** (`SqlLabPage.tsx:40`, une des neuf occurrences
   comptées par la spec design §6.5 — les cinq fichiers concernés :
   `SqlLabPage.tsx`, `AdminExtensionsPage.tsx`, `HarvestSourcesAdminPage.tsx`,
   `CollectionsAdminPage.tsx`, `AppLayout.tsx`). Conçu comme un garde au
   niveau **route** (`shell/routes.tsx`), sur le même principe que
   `RequireAuth.tsx` (déjà un wrapper d'élément de route, mais global à
   toutes les routes protégées — `RequireRole` s'applique route par route,
   avec un rôle et un message différents selon l'appelant), plutôt qu'un
   garde interne à la page : la page elle-même n'a alors plus aucune
   connaissance des droits, cohérent avec la doctrine « aucune comparaison
   de droits ailleurs dans le shell » (spec design §6.5 — la comparaison vit
   à un seul endroit, testé une seule fois). `useMe()` reste la seule source
   consultée (pas de nouveau hook `useProfile()` : `RequireRole` n'a besoin
   que d'`isAdmin`/`isAnalyst`, pas des capacités d'instance que porte
   `Profile` de `capabilities.ts` — leur inclure une dépendance à
   `useInstanceInfo()` non nécessaire créerait un état de chargement
   superflu, risquant de bloquer l'affichage sur une requête sans rapport
   avec le rôle vérifié).
5. **Ordre des tâches : garde d'abord, page ensuite.** Task 1 crée
   `RequireRole` (fichier neuf, testable seul, aucun risque de régression).
   Task 2 le câble sur la route `/analytics/sql` **avant** que Task 3 ne
   retire la vérification interne de `SqlLabPage.tsx` : à aucun moment entre
   les commits de ce plan l'application ne se retrouve sans garde d'accès
   sur cette route (entre Task 2 et Task 3, la vérification interne devient
   du code mort inatteignable — `RequireRole` bloque déjà le rendu de
   `SqlLabPage` avant qu'elle ne s'exécute — mais reste présente jusqu'à sa
   suppression explicite en Task 3, pas de fenêtre de régression réelle).

**Architecture:** Nouveau composant `shell/src/auth/RequireRole.tsx`
(garde générique `role: "admin" | "analyst"`, message de refus fourni par
l'appelant), câblé dans `shell/src/shell/routes.tsx` autour de l'élément de
la route `/analytics/sql`. `SqlLabPage.tsx` s'enveloppe dans
`<div className="-m-6 flex flex-1 flex-col overflow-hidden">` (même
technique que les cinq familles précédentes) et instancie `TriptychLayout`
avec `defaultTabId="query"` et trois volets : **browse** = « Catalogue »
(`Panel` avec lien retour seul) ; **work** = « Requête » (titre local,
éditeur, bouton, erreur, tableau — dans un conteneur `overflow-y-auto`
propre, le volet `work` de `TriptychLayout` étant `overflow-hidden` par
construction, piège déjà documenté par SP-30d/e/f/g/h) ; **inspect** =
« Historique » (liste existante, ou `EmptyState` si vide).

**Tech Stack:** React 19, `@tanstack/react-query`, react-router-dom, kit de
primitives SP-29b (`shell/src/ui/kit/`), Vitest + Testing Library, MSW,
Playwright.

## Global Constraints

- Docs et identifiants de test en français ; code/identifiants en anglais
  (CLAUDE.md).
- Aucune couleur Tailwind en dur (`slate-*`, `red-*`, `blue-*`, `gray-*`,
  `white`, `black`) dans les fichiers touchés : tokens uniquement
  (`bg-surface`, `text-ink`, `text-ink-2`, `border-rule`, `border-rule-2`,
  `text-danger`, `text-accent` — `shell/src/styles/tokens.css`).
- Aucun ancien import `ui/button` ne subsiste dans `SqlLabPage.tsx` après
  Task 3 (remplacé par `ui/kit/Button`).
- `-m-6` est une technique de transition **locale à `SqlLabPage.tsx` seule**
  dans ce plan, jamais un changement à `AppLayout.tsx`.
- Régression jsdom (piège n°10) : `window.matchMedia` n'existe pas sous
  jsdom — `TriptychLayout` l'appelle via `useNarrowViewport`. Stub local à
  `SqlLabPage.test.tsx`, **avec** `afterEach(() => vi.unstubAllGlobals())`
  dès son introduction — jamais dans `shell/src/test/setup.ts`.
- Pas de changement au cœur (`core/`) dans ce plan. Diff vide attendu
  (vérifié en Task 4 par `git status --short core/`). Régénération
  OpenAPI/TS **non nécessaire**.
- `RequireRole` est, après ce plan, le seul endroit du shell qui compare
  `meQuery.data?.isAdmin`/`isAnalyst` pour la route `/analytics/sql`. Les
  six occurrences des trois pages d'administration et les deux
  d'`AppLayout.tsx` restent hors périmètre (famille 8, SP-30j) — ne pas les
  toucher dans ce plan malgré la tentation de « finir le travail » : ce
  découpage en familles est celui de la spec (§6.1), pas une préférence de
  ce plan.
- Suite E2E **complète** exigée avant tout commit qui change la structure
  DOM de la page (Task 3) — pas de liste de specs nommée dans ce plan
  (recommandation actée par SP-30e/f/g/h après plusieurs occurrences du
  piège n°6).

---

## Task 1: Shell — `RequireRole`, garde de rôle au niveau route

**Files:**
- Create: `shell/src/auth/RequireRole.tsx`
- Test: `shell/src/auth/RequireRole.test.tsx`

**Interfaces:**
- Consumes: `useMe()` (`shell/src/api/hooks.ts:45-48`, déjà existant —
  `useQuery({ queryKey: ["me"], queryFn: () => client.getMe() })`, données de
  type `Me` : `{ isAdmin: boolean; isAnalyst: boolean; ... }`,
  `shell/src/api/types.ts:42-50`).
- Produces: `RequireRole({ role: "admin" | "analyst", deniedMessage: string,
  children: ReactNode }): ReactNode` — consommé par Task 2
  (`shell/routes.tsx`), et par la future famille 8 (SP-30j, hors périmètre
  de ce plan) sans modification.

- [ ] **Step 1: Écrire le test, le voir échouer**

Créer `shell/src/auth/RequireRole.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { RequireRole } from "./RequireRole";

function mockMe(overrides: { isAdmin?: boolean; isAnalyst?: boolean }) {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        isAdmin: overrides.isAdmin ?? false,
        isAnalyst: overrides.isAnalyst ?? false,
      }),
    ),
  );
}

function renderGate(role: "admin" | "analyst", deniedMessage: string) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <RequireRole role={role} deniedMessage={deniedMessage}>
          <p>Contenu protégé</p>
        </RequireRole>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("affiche le contenu quand le rôle requis est présent", async () => {
  mockMe({ isAnalyst: true });
  renderGate("analyst", "Accès réservé aux analystes.");
  expect(await screen.findByText("Contenu protégé")).toBeInTheDocument();
});

test("affiche le message de refus quand le rôle requis est absent", async () => {
  mockMe({ isAnalyst: false });
  renderGate("analyst", "Accès réservé aux analystes.");
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Accès réservé aux analystes."),
  );
  expect(screen.queryByText("Contenu protégé")).not.toBeInTheDocument();
});

test("le rôle admin se vérifie indépendamment du rôle analyste", async () => {
  mockMe({ isAdmin: true, isAnalyst: false });
  renderGate("admin", "Accès réservé aux administrateurs.");
  expect(await screen.findByText("Contenu protégé")).toBeInTheDocument();
});

test("affiche un statut de chargement avant la résolution de /me", () => {
  mockMe({ isAnalyst: true });
  renderGate("analyst", "Accès réservé aux analystes.");
  expect(screen.getByRole("status")).toHaveTextContent("Chargement…");
});
```

- [ ] **Step 2: Lancer le test, vérifier l'échec**

```bash
cd shell && npx vitest run src/auth/RequireRole.test.tsx
```

Expected: FAIL — `Cannot find module './RequireRole'` (le fichier n'existe
pas encore).

- [ ] **Step 3: Créer `RequireRole.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import type { ReactNode } from "react";
import { useMe } from "../api/hooks";

/**
 * Porte de rôle au niveau route (spec design SP-30 §6.5 : « meQuery.data?.
 * isAdmin === true et consorts disparaissent des pages » — neuf occurrences
 * comptées dans cinq fichiers). La comparaison vit ici, testée une seule
 * fois — pendant côté rôles d'instance de `Gate`/`hasPermission` côté
 * permissions d'item.
 */
export function RequireRole({
  role,
  deniedMessage,
  children,
}: {
  role: "admin" | "analyst";
  deniedMessage: string;
  children: ReactNode;
}): ReactNode {
  const meQuery = useMe();
  if (meQuery.isLoading) return <p role="status">Chargement…</p>;
  const allowed =
    role === "admin" ? meQuery.data?.isAdmin === true : meQuery.data?.isAnalyst === true;
  if (!allowed) {
    return (
      <p role="alert" className="text-sm text-danger">
        {deniedMessage}
      </p>
    );
  }
  return children;
}
```

- [ ] **Step 4: Lancer le test, vérifier le succès**

```bash
cd shell && npx vitest run src/auth/RequireRole.test.tsx
```

Expected: PASS — 4 tests.

- [ ] **Step 5: Vérifier l'absence de couleur Tailwind en dur**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/auth/RequireRole.tsx
```

Expected: aucune sortie.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/auth/RequireRole.tsx src/auth/RequireRole.test.tsx
git commit -m "feat(shell): requireRole — garde de rôle générique au niveau route"
```

---

## Task 2: Shell — câbler `RequireRole` sur la route `/analytics/sql`

**Files:**
- Modify: `shell/src/shell/routes.tsx`

**Interfaces:**
- Consumes: `RequireRole` (Task 1, `shell/src/auth/RequireRole.tsx`).
- Produces: aucune API changée — la route `/analytics/sql` rend
  désormais `<RequireRole role="analyst" deniedMessage="…"><SqlLabPage />
  </RequireRole>` au lieu de `<SqlLabPage />` seule.

- [ ] **Step 1: Baseline E2E**

```bash
cd shell && npx playwright test e2e/sql-lab.spec.ts
```

Expected: PASS (3 tests) — avant toute modification.

- [ ] **Step 2: Importer `RequireRole`**

Dans `shell/src/shell/routes.tsx`, ajouter l'import (à côté des autres
imports de `../auth/`) :

```tsx
import { RequireAuth } from "../auth/RequireAuth";
```

devient :

```tsx
import { RequireAuth } from "../auth/RequireAuth";
import { RequireRole } from "../auth/RequireRole";
```

- [ ] **Step 3: Envelopper la route**

Remplacer :

```tsx
        <Route path="/analytics/sql" element={<SqlLabPage />} />
```

par :

```tsx
        <Route
          path="/analytics/sql"
          element={
            <RequireRole role="analyst" deniedMessage="Accès réservé aux analystes.">
              <SqlLabPage />
            </RequireRole>
          }
        />
```

Note : `SqlLabPage.tsx` contient encore, à ce stade, sa propre vérification
interne (`meQuery.data?.isAnalyst !== true`) — elle devient du code mort
inatteignable (`RequireRole` bloque déjà le rendu de `SqlLabPage` avant
qu'elle ne s'exécute pour un non-analyste), retirée explicitement en
Task 3. Aucune fenêtre de régression : la route reste gardée à tout moment.

- [ ] **Step 4: Relancer l'E2E, vérifier le succès**

```bash
cd shell && npx playwright test e2e/sql-lab.spec.ts
```

Expected: PASS (3 tests), y compris le troisième
(« un utilisateur non-analyste ne voit pas le lien SQL Lab et reçoit un
message d'accès refusé ») — désormais servi par `RequireRole`, pas par
`SqlLabPage`.

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/shell/routes.tsx
git commit -m "feat(shell): route /analytics/sql — câble requireRole(analyst)"
```

---

## Task 3: Shell — `SqlLabPage` sur `TriptychLayout` (Catalogue/Requête/Historique)

**Files:**
- Modify: `shell/src/pages/SqlLabPage.tsx`
- Modify: `shell/src/pages/SqlLabPage.test.tsx`

**Interfaces:**
- Consumes: `TriptychLayout` (`shell/src/shell/chrome/TriptychLayout.tsx`,
  props `browse`/`work`/`inspect`/`defaultTabId`, chacun `{id, label,
  content}`) ; `Button`/`Panel`/`EmptyState` du kit (`shell/src/ui/kit/`) ;
  `useItemClient()` (inchangé) ; `appendSqlHistory`/`readSqlHistory`/
  `SqlHistoryEntry` (`shell/src/lib/sqlLabHistory.ts`, inchangé).
- Produces: `SqlLabPage()` — aucune prop, inchangé (déjà sans prop) ;
  consommée par `shell/routes.tsx` via `RequireRole` (Task 2).

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/pages/SqlLabPage.test.tsx
```

Expected: PASS (5 tests, état actuel avant modification).

- [ ] **Step 2: Réécrire `SqlLabPage.tsx`**

Remplacer tout le contenu du fichier par :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { useItemClient } from "../api/ItemClientProvider";
import { appendSqlHistory, readSqlHistory, type SqlHistoryEntry } from "../lib/sqlLabHistory";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { EmptyState } from "../ui/kit/EmptyState";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

type SqlResult = { columns: string[]; rows: unknown[][]; truncated: boolean };

export function SqlLabPage() {
  const client = useItemClient();
  const [sql, setSql] = useState("");
  const [result, setResult] = useState<SqlResult | null>(null);
  const [history, setHistory] = useState<SqlHistoryEntry[]>(() => readSqlHistory());

  const run = useMutation({
    mutationFn: (query: string) => client.runAnalyticsSql(query),
    onSuccess: (data, query) => {
      setResult(data);
      setHistory(
        appendSqlHistory({
          sql: query,
          executedAt: new Date().toISOString(),
          status: "ok",
          rowCount: data.rows.length,
        }),
      );
    },
    onError: (_error, query) => {
      setResult(null);
      setHistory(
        appendSqlHistory({ sql: query, executedAt: new Date().toISOString(), status: "error" }),
      );
    },
  });

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
            </Panel>
          ),
        }}
        work={{
          id: "query",
          label: "Requête",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">SQL Lab</h1>
              <label className="flex flex-col gap-1 text-sm text-ink">
                Requête SQL
                <textarea
                  aria-label="Requête SQL"
                  className="h-32 rounded-md border border-rule bg-surface p-2 font-mono text-xs text-ink"
                  value={sql}
                  onChange={(e) => setSql(e.target.value)}
                />
              </label>
              <Button
                size="sm"
                className="w-fit"
                disabled={!sql.trim() || run.isPending}
                onClick={() => run.mutate(sql)}
              >
                Exécuter
              </Button>
              {run.isError && (
                <p role="alert" className="text-sm text-danger">
                  {(run.error as Error).message}
                </p>
              )}
              {result && (
                <div>
                  <table className="w-full text-left text-sm">
                    <thead>
                      <tr>
                        {result.columns.map((col) => (
                          <th key={col} className="border-b border-rule p-1 text-ink">
                            {col}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {result.rows.map((row, i) => (
                        <tr key={i}>
                          {row.map((cell, j) => (
                            <td key={j} className="border-b border-rule-2 p-1 text-ink">
                              {cell === null || cell === undefined ? "" : String(cell)}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  {result.truncated && (
                    <p className="mt-1 text-xs text-ink-2">
                      Résultat tronqué aux {result.rows.length} premières lignes.
                    </p>
                  )}
                </div>
              )}
            </div>
          ),
        }}
        inspect={{
          id: "history",
          label: "Historique",
          content: (
            <div className="flex flex-col gap-2 p-3">
              {history.length === 0 ? (
                <EmptyState title="Aucune requête exécutée pour l'instant." />
              ) : (
                <ul className="flex flex-col gap-1">
                  {history.map((entry, i) => (
                    <li key={i} className="flex items-center gap-2 text-xs">
                      <span aria-hidden="true">{entry.status === "error" ? "✕" : "✓"}</span>
                      <button
                        type="button"
                        aria-label={`Recharger la requête : ${entry.sql}`}
                        className="text-left font-mono text-ink-2 hover:underline"
                        onClick={() => setSql(entry.sql)}
                      >
                        {entry.sql}
                      </button>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          ),
        }}
      />
    </div>
  );
}
```

- [ ] **Step 3: Réécrire `SqlLabPage.test.tsx`**

Remplacer tout le contenu du fichier par :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { SqlLabPage } from "./SqlLabPage";

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. Stub local, avec vi.unstubAllGlobals()
// en afterEach dès son introduction (même patron que ReportEditPage.test.tsx
// et PipelineBuilderPage.test.tsx) — SqlLabPage ne rendait pas
// TriptychLayout avant ce plan, ce stub est nouveau dans ce fichier.
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
  localStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <SqlLabPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("exécute une requête et affiche le tableau de résultat", async () => {
  let posted: unknown;
  server.use(
    http.post("https://core.test/analytics/sql", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json({
        columns: ["nom", "surface"],
        rows: [
          ["Parc A", 12],
          ["Parc B", 30],
        ],
        truncated: false,
      });
    }),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select nom, surface from parcs");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByRole("columnheader", { name: "nom" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "Parc A" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "30" })).toBeInTheDocument();
  await waitFor(() => expect(posted).toEqual({ sql: "select nom, surface from parcs" }));
});

test("affiche l'avis de troncature quand le résultat a été plafonné", async () => {
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json({ columns: ["id"], rows: [["1"]], truncated: true }),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select id from x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByText("Résultat tronqué aux 1 premières lignes.")).toBeInTheDocument();
});

test("affiche le message d'erreur du serveur et conserve le texte SQL en cas d'échec", async () => {
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json(
        {
          errors: [{ field: "sql", code: "sql_error", message: "Parser Error: syntax error" }],
        },
        { status: 400 },
      ),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select * fro x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Parser Error: syntax error");
  expect(textarea).toHaveValue("select * fro x");
});

test("enregistre l'historique au succès et recharge une requête passée au clic", async () => {
  server.use(
    http.post("https://core.test/analytics/sql", () =>
      HttpResponse.json({ columns: ["id"], rows: [["1"]], truncated: false }),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select id from x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  await screen.findByRole("columnheader", { name: "id" });
  await userEvent.clear(textarea);
  const historyButton = await screen.findByRole("button", {
    name: "Recharger la requête : select id from x",
  });
  await userEvent.click(historyButton);
  expect(textarea).toHaveValue("select id from x");
});

test("affiche un état vide dans l'onglet Historique tant qu'aucune requête n'a été exécutée", async () => {
  render(<Harness />);
  await screen.findByLabelText("Requête SQL");
  expect(screen.getByText("Aucune requête exécutée pour l'instant.")).toBeInTheDocument();
});

test("sous viewport étroit, affiche trois onglets Catalogue/Requête/Historique avec Requête actif par défaut", async () => {
  stubMatchMedia(true);
  render(<Harness />);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Requête", "Historique"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Requête");
});
```

Note : le test « shows an access-denied message for a non-analyst user » de
l'ancien fichier disparaît — ce comportement est désormais couvert par
`RequireRole.test.tsx` (Task 1), qui teste le garde indépendamment de
`SqlLabPage`. `SqlLabPage` elle-même ne connaît plus `useMe()` ni le rôle de
l'utilisateur (Décision explicite 4).

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/pages/SqlLabPage.test.tsx
```

Expected: PASS — 6 tests.

- [ ] **Step 5: Vérifier l'absence de couleur Tailwind en dur**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/pages/SqlLabPage.tsx
```

Expected: aucune sortie.

- [ ] **Step 6: Vérifier l'absence d'ancien import `ui/button`**

```bash
grep -n 'ui/button"\|ui/dialog"\|ui/input"\|ui/card"' shell/src/pages/SqlLabPage.tsx
```

Expected: aucune sortie.

- [ ] **Step 7: Vérifier l'absence de toute comparaison de droits résiduelle**

```bash
grep -n 'isAnalyst\|isAdmin\|useMe' shell/src/pages/SqlLabPage.tsx
```

Expected: aucune sortie — `SqlLabPage.tsx` ne mentionne plus ni `useMe`, ni
`isAdmin`, ni `isAnalyst`.

- [ ] **Step 8: Suite E2E complète (piège n°6 — pas de liste de specs nommée)**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed, ou mieux (aucune
régression croisée sur les pages non touchées par ce plan).

- [ ] **Step 9: Commit**

```bash
cd shell && git add src/pages/SqlLabPage.tsx src/pages/SqlLabPage.test.tsx
git commit -m "feat(shell): sqlLabPage sur TriptychLayout (Catalogue/Requête/Historique)"
```

---

## Task 4: Vérification finale

Ce plan ne se termine pas par un commit propre — c'est une tâche de
vérification. Si un des steps échoue, revenir à la tâche responsable
(identifiable par le fichier en cause) pour corriger, jamais par un
correctif générique ici.

- [ ] **Step 1: Suite Vitest complète**

```bash
cd shell && npx vitest run
```

Expected: PASS — 223 fichiers / 1829 tests (222/1824 avant ce plan, +4
`RequireRole.test.tsx`, +1 net sur `SqlLabPage.test.tsx` : -1 test
« access-denied » déplacé vers `RequireRole.test.tsx`, +2 tests nouveaux —
état vide de l'historique, onglets sous viewport étroit), aucune régression
sur les fichiers non touchés par ce plan.

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

- [ ] **Step 6: Recherche exhaustive de couleurs Tailwind en dur résiduelles dans les trois fichiers touchés par ce plan**

```bash
grep -rnE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/auth/RequireRole.tsx \
  shell/src/pages/SqlLabPage.tsx \
  shell/src/shell/routes.tsx
```

Expected: aucune sortie.

- [ ] **Step 7: Confirmer qu'une seule occurrence de comparaison de droits en dur subsiste dans ce périmètre (les six de la famille 8, hors plan)**

```bash
grep -rn "isAnalyst\|isAdmin" shell/src --include="*.tsx" --include="*.ts" \
  | grep -v test | grep -v "capabilities.ts\|permissions.ts\|generated\|itemClient.ts\|types.ts\|RequireRole.tsx"
```

Expected : uniquement `AccountMenu.tsx` (affichage du badge de rôle, hors
doctrine — lit `me.isAdmin`/`me.isAnalyst` déjà résolus, ne compare rien),
`AppLayout.tsx` (2, hors périmètre), `AdminExtensionsPage.tsx` (2),
`HarvestSourcesAdminPage.tsx` (2), `CollectionsAdminPage.tsx` (2) — 8
occurrences dans 4 fichiers, contre 9 dans 5 avant ce plan.
`SqlLabPage.tsx` n'apparaît plus dans cette liste.
