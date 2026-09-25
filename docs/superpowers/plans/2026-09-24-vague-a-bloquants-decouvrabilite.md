# Vague A — bloquants et découvrabilité — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer les 7 SP proposés par la vague A du diagnostic UI/UX
(`docs/revue/2026-09-24-diagnostic-ui-ux.md` §3) : découvrabilité de
`/bookmarks`/`/analytics/sql`, édition d'un item Site, garde rôle×flag sur
la création de pipeline + message d'indisponibilité, auto-cadrage carte sur
l'emprise des données, parité de couches du widget carte, suppression de
secret (UI+MCP), réouverture d'un pipeline wizard vers son éditeur d'origine.

**Architecture :** Chaque tâche modifie un sous-système déjà existant et
testé — aucune nouvelle capacité d'infrastructure. Toutes les décisions de
conception sont tranchées dans
`docs/superpowers/specs/2026-09-24-vague-a-bloquants-decouvrabilite-design.md` ;
ce plan ne rediscute rien, il exécute.

**Tech Stack :** React 18 + TypeScript (shell), Vitest + Testing Library +
MSW, FastAPI + SQLAlchemy (core), pytest, MapLibre GL JS + deck.gl.

## Global Constraints

- Docs et commentaires en français, identifiants/code en anglais (CLAUDE.md).
- Commits conventional, petits, un sujet par tâche.
- TDD systématique : test qui échoue → implémentation minimale → test qui
  passe → commit.
- Jamais de `window.confirm` pour une action destructive : toujours
  `ui/kit/ConfirmDialog` (convention tranchée 2026-09-01, D26).
- Toute garde MCP dupliquant une garde REST doit être **strictement
  identique** (REV-009, piège CLAUDE.md n°4) — jamais plus permissive.
- Ne pas dupliquer un calcul déjà factorisé : réutiliser
  `lib/geometryBbox.ts`, `LayerPicker`/`LayersPanel`,
  `decompilePipelineToWizardState`, jamais les réécrire.

---

### Task 1 : Item Site — branche d'édition manquante (SP-A2, D02)

**Files:**
- Modify: `shell/src/pages/ItemDetailPage.tsx:116`
- Test: `shell/src/pages/ItemDetailPage.test.tsx`

**Interfaces:**
- Consumes: rien de nouveau — `onOpenEditor?: (type: string) => void` déjà
  prop de `ItemDetailPage`.
- Produces: rien consommé par une tâche ultérieure.

- [ ] **Step 1: Write the failing test**

Ajouter dans `shell/src/pages/ItemDetailPage.test.tsx`, juste après le test
`"shows 'Ouvrir dans l'éditeur' for a pipeline item..."` (fin ~ligne 100) :

```tsx
test("shows 'Ouvrir dans l'éditeur' for a site item and calls onOpenEditor('site')", async () => {
  server.use(
    http.get("https://core.test/v1/items/7", () =>
      HttpResponse.json({
        pk: "7",
        resourceType: "site",
        title: "Item 7",
        abstract: "Abstract 7",
        owner: "alice",
        thumbnailUrl: null,
        date: "2026-01-01T00:00:00Z",
        configId: null,
        isPublished: false,
      }),
    ),
  );
  const onOpenEditor = vi.fn();
  render(<ItemDetailPage pk="7" onOpenEditor={onOpenEditor} />, { wrapper });
  const button = await screen.findByRole("button", { name: /éditeur/i });
  expect(button).not.toBeDisabled();
  await userEvent.click(button);
  expect(onOpenEditor).toHaveBeenCalledWith("site");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/pages/ItemDetailPage.test.tsx -t "site item"`
Expected: FAIL — le bouton est rendu `disabled` (branche `else` de
`ItemDetailPage.tsx:120-123`), `expect(button).not.toBeDisabled()` échoue.

- [ ] **Step 3: Write minimal implementation**

Dans `shell/src/pages/ItemDetailPage.tsx:116`, remplacer :

```tsx
{["map", "app", "dashboard", "dataset", "pipeline"].includes(item.resourceType) ? (
```

par :

```tsx
{["map", "app", "dashboard", "dataset", "pipeline", "site"].includes(item.resourceType) ? (
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/pages/ItemDetailPage.test.tsx`
Expected: PASS (tous les tests du fichier, pas seulement le nouveau).

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/ItemDetailPage.tsx shell/src/pages/ItemDetailPage.test.tsx
git commit -m "fix(shell): active l'édition d'un item Site depuis sa fiche (D02)"
```

---

### Task 2 : Liens de découvrabilité `/bookmarks` et `/analytics/sql` (SP-A1, D01)

**Files:**
- Modify: `shell/src/pages/CatalogPage.tsx` (près des lignes 147-151)
- Modify: `shell/src/i18n/catalog.fr.ts` (près de la ligne 100)
- Test: `shell/src/pages/CatalogPage.test.tsx` (près des lignes 241-277)

**Interfaces:**
- Consumes: `useMe` déjà importé dans `CatalogPage.tsx:4`
  (`import { useItemFacets, useItems, useMe } from "../api/hooks";`), mais
  pas encore appelé dans le composant — à instancier.
- Produces: rien consommé par une tâche ultérieure.

- [ ] **Step 1: Write the failing tests**

Dans `shell/src/i18n/catalog.fr.ts`, ajouter juste après la ligne
`"catalog.scheduledReportsLink": "Rapports planifiés →",` :

```ts
"catalog.bookmarksLink": "Signets →",
"catalog.sqlLabLink": "SQL Lab →",
```

Dans `shell/src/pages/CatalogPage.test.tsx`, ajouter après le test
`"masque le lien vers /reports sur une vue à fixedType fixé..."` (fin
~ligne 277) :

```tsx
test("propose un lien vers /bookmarks quand le type de la barre de domaines est bookmark (atterrissage Analytique)", async () => {
  function wrapperWithBookmarkType({ children }: { children: ReactNode }) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "test-token" });
    return (
      <MemoryRouter initialEntries={["/?type=bookmark"]}>
        <QueryClientProvider client={queryClient}>
          <ItemClientProvider client={client}>{children}</ItemClientProvider>
        </QueryClientProvider>
      </MemoryRouter>
    );
  }
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper: wrapperWithBookmarkType });
  expect(await screen.findByRole("link", { name: "Signets →" })).toHaveAttribute(
    "href",
    "/bookmarks",
  );
});

test("masque le lien vers /bookmarks hors de l'atterrissage Analytique (catalogue général)", async () => {
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  await screen.findByRole("combobox", { name: "Type" });
  expect(screen.queryByRole("link", { name: "Signets →" })).not.toBeInTheDocument();
});

test("masque le lien vers /bookmarks sur /bookmarks lui-même (fixedType fixé)", async () => {
  render(<CatalogPage onOpenItem={() => {}} fixedType="bookmark" />, { wrapper });
  expect(screen.queryByRole("link", { name: "Signets →" })).not.toBeInTheDocument();
});

test("propose un lien vers /analytics/sql sur l'atterrissage Analytique pour un privilège analytics.sql_lab.access", async () => {
  server.use(
    http.get("https://core.test/v1/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        tenantId: "t1",
        role: { id: "r1", name: "Analyste", slug: "analyst" },
        privileges: ["analytics.sql_lab.access"],
        version: "0.1.0",
        tenantSlug: "demo",
      }),
    ),
  );
  function wrapperWithBookmarkType({ children }: { children: ReactNode }) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "test-token" });
    return (
      <MemoryRouter initialEntries={["/?type=bookmark"]}>
        <QueryClientProvider client={queryClient}>
          <ItemClientProvider client={client}>{children}</ItemClientProvider>
        </QueryClientProvider>
      </MemoryRouter>
    );
  }
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper: wrapperWithBookmarkType });
  expect(await screen.findByRole("link", { name: "SQL Lab →" })).toHaveAttribute(
    "href",
    "/analytics/sql",
  );
});

test("masque le lien vers /analytics/sql sans le privilège analytics.sql_lab.access", async () => {
  function wrapperWithBookmarkType({ children }: { children: ReactNode }) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "test-token" });
    return (
      <MemoryRouter initialEntries={["/?type=bookmark"]}>
        <QueryClientProvider client={queryClient}>
          <ItemClientProvider client={client}>{children}</ItemClientProvider>
        </QueryClientProvider>
      </MemoryRouter>
    );
  }
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper: wrapperWithBookmarkType });
  await screen.findByRole("link", { name: "Signets →" });
  expect(screen.queryByRole("link", { name: "SQL Lab →" })).not.toBeInTheDocument();
});
```

Note : le MSW par défaut (`test/msw/handlers.ts`) sert un profil `/me`
sans `analytics.sql_lab.access` — le premier des deux derniers tests
doit donc surcharger la route comme montré ; le second utilise le défaut
tel quel (aucune surcharge).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/pages/CatalogPage.test.tsx -t "bookmarks\|analytics/sql\|Signets\|SQL Lab"`
Expected: FAIL — `findByRole("link", { name: "Signets →" })` timeout, la
clé i18n existe déjà (ajoutée à l'étape 1) mais aucun `<Link>` ne la rend
encore.

- [ ] **Step 3: Write minimal implementation**

Dans `shell/src/pages/CatalogPage.tsx`, ajouter `useMe` à l'appel du hook
juste après la ligne `const type = fixedType ?? validUrlType;` (ou tout
autre point où les hooks du composant sont déclarés) :

```tsx
const meQuery = useMe();
```

Puis, juste après le bloc existant :

```tsx
{type === "pipeline" && !fixedType && (
  <Link to="/reports" className="text-accent hover:underline">
    {t("catalog.scheduledReportsLink")}
  </Link>
)}
```

ajouter :

```tsx
{type === "bookmark" && !fixedType && (
  <Link to="/bookmarks" className="text-accent hover:underline">
    {t("catalog.bookmarksLink")}
  </Link>
)}
{type === "bookmark" &&
  !fixedType &&
  meQuery.data?.privileges.includes("analytics.sql_lab.access") === true && (
    <Link to="/analytics/sql" className="text-accent hover:underline">
      {t("catalog.sqlLabLink")}
    </Link>
  )}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/CatalogPage.test.tsx`
Expected: PASS (fichier entier).

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/CatalogPage.tsx shell/src/i18n/catalog.fr.ts shell/src/pages/CatalogPage.test.tsx
git commit -m "feat(shell): liens de découvrabilité vers /bookmarks et /analytics/sql (D01)"
```

---

### Task 3 : Filet anti-régression — inventaire de routes sans lien entrant (D01)

**Files:**
- Create: `shell/src/shell/routeReachability.test.ts`

**Interfaces:**
- Consumes: `shell/src/shell/routes.tsx` (fichier source, lu comme texte
  brut par le test — pas d'import du module React).
- Produces: rien consommé par une tâche ultérieure ; ce test protège
  contre la régression classée D01 dans le diagnostic (§4).

- [ ] **Step 1: Write the failing test**

```ts
// SPDX-License-Identifier: Apache-2.0
// Filet anti-régression D01 (docs/revue/2026-09-24-diagnostic-ui-ux.md §4) :
// une route déclarée dans routes.tsx sans aucun lien entrant ailleurs dans
// le shell est un écran fonctionnel mais invisible (cf. GAP-80/GAP-81,
// SP-46). Ce test lit routes.tsx en texte brut (pas d'exécution du routeur :
// un test générique par exécution devrait mocker tout l'arbre applicatif
// pour peu de valeur ajoutée) et vérifie que chaque chemin statique déclaré
// apparaît au moins une fois ailleurs dans shell/src (un <Link to="...">,
// un navigate("..."), ou une entrée du registre ci-dessous pour les routes
// dont l'absence de lien est un choix assumé).
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { test, expect } from "vitest";

const SHELL_SRC = join(__dirname, "..");
const ROUTES_FILE = join(__dirname, "routes.tsx");

// Routes volontairement atteignables uniquement par deep-link (paramétrées,
// ou dont le seul point d'entrée légitime est hors du shell — email,
// partage externe, publication) : ne pas ajouter une route ici pour faire
// taire ce test sans avoir vérifié qu'elle est vraiment deep-link-only.
const DEEP_LINK_ONLY_ROUTES = new Set<string>([
  "/", // racine : atteinte par tout <Link to="/">, trop générique pour un grep utile
  "/login",
  "/logout",
  "/embed/:token",
  "/sites/:slug",
  "/items/:pk",
  "/maps/:pk",
  "/datasets/:pk/edit",
  "/apps/:pk/edit",
  "/pipelines/new",
  "/pipelines/:pk/edit",
  "/datasets/visual-query/new",
  "/datasets/visual-query/:pipelinePk/edit",
  "/reports/new",
  "/reports/:pk/edit",
]);

function extractStaticRoutePaths(): string[] {
  const content = readFileSync(ROUTES_FILE, "utf-8");
  const matches = [...content.matchAll(/<Route\s+path="([^"]+)"/g)].map((m) => m[1]);
  // Seules les routes statiques (sans ":") sont vérifiables par un grep
  // littéral du chemin — les routes paramétrées sont couvertes une à une
  // dans DEEP_LINK_ONLY_ROUTES ci-dessus ou par leurs propres tests.
  return matches.filter((p) => !p.includes(":") && !DEEP_LINK_ONLY_ROUTES.has(p));
}

function allSourceFilesExcludingRoutes(): string[] {
  const files: string[] = [];
  function walk(dir: string) {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      const stat = statSync(full);
      if (stat.isDirectory()) {
        if (entry === "node_modules") continue;
        walk(full);
      } else if (
        (entry.endsWith(".ts") || entry.endsWith(".tsx")) &&
        !entry.endsWith(".test.ts") &&
        !entry.endsWith(".test.tsx") &&
        full !== ROUTES_FILE
      ) {
        files.push(full);
      }
    }
  }
  walk(SHELL_SRC);
  return files;
}

test("chaque route statique de routes.tsx a un lien entrant ailleurs dans shell/src, ou est listée deep-link-only", () => {
  const paths = extractStaticRoutePaths();
  const files = allSourceFilesExcludingRoutes();
  const contents = files.map((f) => readFileSync(f, "utf-8"));
  const unreachable = paths.filter((p) => !contents.some((c) => c.includes(`"${p}"`)));
  expect(unreachable).toEqual([]);
});
```

- [ ] **Step 2: Run test to verify it fails or passes correctly first**

Run: `cd shell && npx vitest run src/shell/routeReachability.test.ts`
Expected: PASS immédiatement (Task 2 a déjà ajouté les liens vers
`/bookmarks` et `/analytics/sql`, donc plus aucune route statique n'est
orpheline). C'est attendu : ce test capture un filet, il ne corrige pas
un bug déjà réglé par Task 2. S'il échouait, cela signalerait soit une
route statique oubliée par Task 2, soit une route à ajouter à
`DEEP_LINK_ONLY_ROUTES` avec une justification.

- [ ] **Step 3: Falsifier le filet (obligatoire, piège CLAUDE.md n°10)**

Temporairement, retirer la ligne `<Link to="/bookmarks" ...>` ajoutée en
Task 2 (ne pas commiter ce retrait), relancer le test :

Run: `cd shell && npx vitest run src/shell/routeReachability.test.ts`
Expected: FAIL — `unreachable` contient `/bookmarks`. Confirme que le
filet détecte réellement une régression. Remettre la ligne retirée.

- [ ] **Step 4: Run test to verify it passes again**

Run: `cd shell && npx vitest run src/shell/routeReachability.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/shell/routeReachability.test.ts
git commit -m "test(shell): filet anti-régression — route sans lien entrant (D01)"
```

---

### Task 4 : `NewItemButton` — garde privilège `automation.manage` (SP-A3, D03) + matrice rôle×flag

**Files:**
- Modify: `shell/src/shell/NewItemButton.tsx`
- Test: `shell/src/shell/NewItemButton.test.tsx`

**Interfaces:**
- Consumes: `privileges: string[] | undefined` déjà disponible via
  `meQuery.data?.privileges` (ligne 60-61 existante).
- Produces: `canCreatePipeline: boolean` (nouvelle constante locale),
  consommée uniquement dans ce fichier.

- [ ] **Step 1: Write the failing tests**

Dans `shell/src/shell/NewItemButton.test.tsx`, la fixture `CREATOR_ME` (
lignes ~40-50) doit gagner `"automation.manage"` puisque le rôle Créateur
réel l'a (`core/app/roles/privileges.py`, rôle `creator`) :

```ts
const CREATOR_ME = {
  id: "u1",
  username: "alice",
  firstName: "Alice",
  lastName: "Martin",
  email: "alice@example.com",
  tenantId: "t1",
  role: { id: "role-creator", name: "Créateur", slug: "creator" },
  privileges: [
    "catalog.manage",
    "maps.manage",
    "data.view",
    "data.manage",
    "apps.manage",
    "automation.manage",
  ],
  version: "0.1.0",
  tenantSlug: "demo",
};
```

Remplacer le test existant `"the Pipeline option is present when etlEnabled
is true"` (qui utilisait implicitement `CREATOR_ME.privileges`, désormais
avec `automation.manage`) — il doit continuer à passer tel quel, aucune
modification de son corps nécessaire.

Ajouter deux nouveaux tests juste après lui :

```tsx
test("the Pipeline option is absent when etlEnabled is true but automation.manage is missing (D03)", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () =>
      HttpResponse.json({ readOnly: false, etlEnabled: true }),
    ),
  );
  render(
    <Harness queryClient={makeQueryClient(CREATOR_ME.privileges.filter((p) => p !== "automation.manage"))}>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  expect(screen.queryByRole("option", { name: "Pipeline" })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: /Requête visuelle/i })).not.toBeInTheDocument();
});

test("matrice rôle×flag : l'option Pipeline n'est visible que si automation.manage ET etlEnabled sont réunis (filet D03)", async () => {
  const ROLE_PRIVILEGES: Record<string, string[]> = {
    administrateur: [
      "catalog.manage",
      "maps.manage",
      "data.manage",
      "apps.manage",
      "automation.manage",
    ],
    createur: ["maps.manage", "data.manage", "apps.manage", "automation.manage"],
    analyste: ["data.view", "analytics.view"],
    lecteur: [],
  };
  for (const [role, privileges] of Object.entries(ROLE_PRIVILEGES)) {
    for (const etlEnabled of [true, false]) {
      server.use(
        http.get("https://core.test/v1/instance", () =>
          HttpResponse.json({ readOnly: false, etlEnabled }),
        ),
      );
      const { unmount } = render(
        <Harness queryClient={makeQueryClient(privileges)}>
          <NewItemButton />
        </Harness>,
      );
      const trigger = screen.queryByRole("button", { name: "Nouveau" });
      const expectPipelineVisible = privileges.includes("automation.manage") && etlEnabled;
      if (trigger) {
        await userEvent.click(trigger);
        const option = screen.queryByRole("option", { name: "Pipeline" });
        expect(
          option !== null,
          `role=${role} etlEnabled=${etlEnabled} : présence attendue=${expectPipelineVisible}`,
        ).toBe(expectPipelineVisible);
      } else {
        // Bouton absent (0 kind créable) : l'option Pipeline n'est a fortiori
        // jamais visible, cohérent avec expectPipelineVisible=false ici.
        expect(expectPipelineVisible).toBe(false);
      }
      unmount();
    }
  }
});
```

Cette dernière assume l'existence d'un composant `Harness` acceptant une
prop `queryClient` optionnelle — vérifier le fichier de test existant :
s'il expose déjà un tel composant (probable, vu l'usage de
`makeQueryClient` dans les tests déjà en place), l'utiliser tel quel ; sinon
l'ajouter en tête de fichier :

```tsx
function Harness({
  children,
  queryClient = makeQueryClient(),
}: {
  children: ReactNode;
  queryClient?: QueryClient;
}) {
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "test-token" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>{children}</ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/shell/NewItemButton.test.tsx -t "D03\|matrice"`
Expected: FAIL — le composant actuel ne lit jamais `automation.manage`,
l'option Pipeline reste visible dès que `etlEnabled` est vrai quel que
soit le privilège.

- [ ] **Step 3: Write minimal implementation**

Dans `shell/src/shell/NewItemButton.tsx`, remplacer :

```tsx
const canCreateApp = privileges === undefined || privileges.includes("apps.manage");
const canCreateMap = privileges === undefined || privileges.includes("maps.manage");
const canCreateDataset = privileges === undefined || privileges.includes("data.manage");
const hasAnyCreatableKind = canCreateApp || canCreateMap || canCreateDataset || etlEnabled;
```

par :

```tsx
const canCreateApp = privileges === undefined || privileges.includes("apps.manage");
const canCreateMap = privileges === undefined || privileges.includes("maps.manage");
const canCreateDataset = privileges === undefined || privileges.includes("data.manage");
// D03 : pipeline/visual-query gatés uniquement sur etlEnabled jusqu'ici —
// un rôle sans automation.manage remplissait tout le formulaire pour
// échouer sur un 403 serveur final. Même doublet privilège+capacité que
// la barre de domaines (capabilities.ts:61-66, doctrine "un privilège
// manquant MASQUE, une capacité coupée VERROUILLE").
const canCreatePipeline =
  (privileges === undefined || privileges.includes("automation.manage")) && etlEnabled;
const hasAnyCreatableKind = canCreateApp || canCreateMap || canCreateDataset || canCreatePipeline;
```

Remplacer les deux options du `<select>` :

```tsx
{etlEnabled && (
  <option value="visual-query">{t("newItem.datasetVisualQueryOption")}</option>
)}
{etlEnabled && <option value="pipeline">{t("newItem.pipelineOption")}</option>}
```

par :

```tsx
{canCreatePipeline && (
  <option value="visual-query">{t("newItem.datasetVisualQueryOption")}</option>
)}
{canCreatePipeline && <option value="pipeline">{t("newItem.pipelineOption")}</option>}
```

Et dans l'effet de repli (`useEffect` qui recalcule `stillAllowed`/
`fallback`), remplacer chaque occurrence de la condition
`((kind === "pipeline" || kind === "visual-query") && etlEnabled)` par
`((kind === "pipeline" || kind === "visual-query") && canCreatePipeline)`,
et `etlEnabled ? "visual-query" : undefined` par
`canCreatePipeline ? "visual-query" : undefined`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/shell/NewItemButton.test.tsx`
Expected: PASS (fichier entier, y compris les tests pré-existants sur
etlEnabled seul, désormais couverts par la fixture `CREATOR_ME` mise à
jour).

- [ ] **Step 5: Commit**

```bash
git add shell/src/shell/NewItemButton.tsx shell/src/shell/NewItemButton.test.tsx
git commit -m "fix(shell): garde automation.manage sur la création pipeline/visual-query (D03)"
```

---

### Task 5 : `/pipelines/new` — message d'indisponibilité au lieu du spinner infini (D09)

**Files:**
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/pages/PipelineBuilderPage.test.tsx`

**Interfaces:**
- Consumes: `useInstanceInfo` déjà utilisé ailleurs dans le shell
  (`NewItemButton.tsx`, `AdminInfrastructurePage.tsx`), pas encore importé
  dans ce fichier.
- Produces: rien consommé par une tâche ultérieure.

- [ ] **Step 1: Write the failing test**

Dans `shell/src/i18n/catalog.fr.ts`, ajouter près de
`"infrastructure.disabled"` :

```ts
"pipelineBuilder.etlDisabled": "Non activé sur cette instance (CORE_ETL_ENABLED).",
```

Dans `shell/src/pages/PipelineBuilderPage.test.tsx`, ajouter un nouveau
test (l'emplacement exact dépend de la structure du fichier — le placer
dans le groupe des tests "unsaved mode" pour `pk={null}`) :

```tsx
test("affiche un message de désactivation au lieu du spinner infini quand CORE_ETL_ENABLED est faux (D09)", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () =>
      HttpResponse.json({ readOnly: false, etlEnabled: false }),
    ),
    http.get("https://core.test/v1/pipelines/ops", () => new HttpResponse(null, { status: 404 })),
  );
  render(<PipelineBuilderPage pk={null} />, { wrapper });
  expect(await screen.findByText("Non activé sur cette instance (CORE_ETL_ENABLED).")).toBeInTheDocument();
  expect(screen.queryByText("Chargement…")).not.toBeInTheDocument();
});
```

Adapter `wrapper` au patron déjà utilisé par les autres tests de ce
fichier (import `server`/`http`/`HttpResponse` depuis les mêmes modules
que les tests voisins).

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx -t "D09"`
Expected: FAIL — timeout sur `findByText`, la page reste bloquée sur
`t("common.loading")` indéfiniment (confirmé par la recherche : `opsQuery`
passe en erreur mais `!opsQuery.data` reste vrai pour toujours).

- [ ] **Step 3: Write minimal implementation**

Dans `shell/src/pages/PipelineBuilderPage.tsx`, ajouter l'import :

```ts
import { useCreatePipeline, useInstanceInfo, useItem, usePipelineConfig, usePipelineOps, useSavePipeline } from "../api/hooks";
```

(fusionner avec l'import existant plutôt que le dupliquer). Puis, juste
après la déclaration de `opsQuery` :

```ts
const opsQuery = usePipelineOps();
const instanceQuery = useInstanceInfo();
const etlEnabled = instanceQuery.data?.etlEnabled === true;
```

Et juste avant la ligne `if (opsQuery.isLoading || !opsQuery.data) return
<p role="status">{t("common.loading")}</p>;`, insérer une garde
supplémentaire :

```tsx
// D09 : CORE_ETL_ENABLED=false → les routes pipeline ne sont pas montées
// côté cœur (core/app/pipelines/routes.py), opsQuery termine en erreur
// (404) et !opsQuery.data reste vrai pour toujours sans cette garde —
// spinner infini. Vérifier le flag AVANT d'attendre opsQuery, pas après :
// tant que instanceQuery lui-même charge, ne rien affirmer sur etlEnabled.
if (!instanceQuery.isLoading && !etlEnabled) {
  return <p className="text-sm text-ink-2">{t("pipelineBuilder.etlDisabled")}</p>;
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx`
Expected: PASS (fichier entier — vérifier qu'aucun test existant ne
supposait un rendu de `PipelineBuilderPage` avec `etlEnabled` absent du
mock `/instance` par défaut ; le mock MSW par défaut sert probablement déjà
`etlEnabled: true` ou équivalent, sans quoi d'autres tests du fichier
casseraient aussi — dans ce cas, ajuster le handler MSW par défaut plutôt
que chaque test individuellement).

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/PipelineBuilderPage.tsx shell/src/i18n/catalog.fr.ts shell/src/pages/PipelineBuilderPage.test.tsx
git commit -m "fix(shell): message explicite au lieu du spinner infini sur /pipelines/new (D09)"
```

---

### Task 6 : `fitBounds` sur `MapViewHandle` + factorisation du calcul de bbox client (SP-A4, D18 — socle)

**Files:**
- Modify: `shell/src/lib/geometryBbox.ts`
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/builder/pipeline/PipelinePreviewMap.tsx`
- Test: `shell/src/lib/geometryBbox.test.ts` (créer si absent, sinon étendre)
- Test: `shell/src/map/MapView.test.tsx`
- Test: `shell/src/builder/pipeline/PipelinePreviewMap.test.tsx`

**Interfaces:**
- Produces: `bboxFromFeatureCollection(features: GeoJSON.Feature[]):
  [number, number, number, number] | null` (nouvelle fonction exportée de
  `lib/geometryBbox.ts`) — **consommée par Task 8 et Task 9**.
- Produces: `MapViewHandle.fitBounds(bbox: [number, number, number,
  number], opts?: { padding?: number; maxZoom?: number }): void` —
  **consommée par Task 8 et Task 9**.

- [ ] **Step 1: Write the failing test — `bboxFromFeatureCollection`**

Créer (ou étendre) `shell/src/lib/geometryBbox.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "vitest";
import { bboxFromFeatureCollection, bboxFromGeometry } from "./geometryBbox";

test("bboxFromFeatureCollection computes the union bbox of several features", () => {
  const features: GeoJSON.Feature[] = [
    { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [1, 10] } },
    { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [3, 20] } },
  ];
  expect(bboxFromFeatureCollection(features)).toEqual([1, 10, 3, 20]);
});

test("bboxFromFeatureCollection returns null when no feature has a geometry", () => {
  const features: GeoJSON.Feature[] = [{ type: "Feature", properties: {}, geometry: null }];
  expect(bboxFromFeatureCollection(features)).toBeNull();
});
```

(Le test existant `bboxFromGeometry` importé ci-dessus doit continuer de
passer inchangé — pas de régression sur la fonction déjà en place.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/lib/geometryBbox.test.ts`
Expected: FAIL — `bboxFromFeatureCollection` n'existe pas encore
(`TypeError` ou erreur d'import TS).

- [ ] **Step 3: Write minimal implementation — `bboxFromFeatureCollection`**

Dans `shell/src/lib/geometryBbox.ts`, ajouter après `bboxFromGeometry` :

```ts
// Union bbox de plusieurs features — remplace le calcul dupliqué de
// builder/pipeline/PipelinePreviewMap.tsx (collectCoordinates/computeBounds),
// factorisé ici pour SP-A4 (D18) qui a besoin du même calcul côté éditeur
// de carte et widget carte. Réutilise walk() : bboxFromGeometry gère déjà
// une géométrie unique, il suffit d'accumuler sur toutes les features.
export function bboxFromFeatureCollection(
  features: GeoJSON.Feature[],
): [number, number, number, number] | null {
  const acc: [number, number, number, number] = [Infinity, Infinity, -Infinity, -Infinity];
  let found = false;
  for (const f of features) {
    if (!f.geometry) continue;
    const bbox = bboxFromGeometry(f.geometry);
    if (!bbox) continue;
    found = true;
    if (bbox[0] < acc[0]) acc[0] = bbox[0];
    if (bbox[1] < acc[1]) acc[1] = bbox[1];
    if (bbox[2] > acc[2]) acc[2] = bbox[2];
    if (bbox[3] > acc[3]) acc[3] = bbox[3];
  }
  return found ? acc : null;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/lib/geometryBbox.test.ts`
Expected: PASS.

- [ ] **Step 5: Write the failing test — `MapViewHandle.fitBounds`**

Dans `shell/src/map/MapView.test.tsx`, ajouter après le bloc de tests
`onReady` (~ligne 525) :

```tsx
test("fitBounds calls the underlying MapLibre fitBounds with the given bbox", () => {
  const ref = createRef<MapViewHandle>();
  render(<MapView ref={ref} config={config} />);
  ref.current?.fitBounds([1, 10, 3, 20], { padding: 40, maxZoom: 14 });
  const map = mapInstances[0];
  expect(map.fitBoundsArgs).toHaveLength(1);
  expect(map.fitBoundsArgs[0]).toEqual({
    bounds: [
      [1, 10],
      [3, 20],
    ],
    opts: { padding: 40, maxZoom: 14 },
  });
});
```

Ajouter `createRef` à l'import `react` en tête de fichier si absent, et
`MapViewHandle` à l'import de type depuis `./MapView` si absent.

- [ ] **Step 6: Run test to verify it fails**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t "fitBounds"`
Expected: FAIL — `ref.current?.fitBounds` n'existe pas (`TypeError:
ref.current.fitBounds is not a function` ou l'appel est silencieusement un
no-op selon TypeScript strict — en tout cas `map.fitBoundsArgs` reste
vide).

- [ ] **Step 7: Write minimal implementation — `fitBounds`**

Dans `shell/src/map/MapView.tsx`, étendre le type exporté :

```ts
export type MapViewHandle = {
  flyTo: (opts: {
    center: [number, number];
    zoom?: number;
    pitch?: number;
    bearing?: number;
  }) => void;
  highlight: (geometry: unknown | null) => void;
  fitBounds: (
    bbox: [number, number, number, number],
    opts?: { padding?: number; maxZoom?: number },
  ) => void;
};
```

Puis dans le bloc `useImperativeHandle(ref, () => ({ ... }))`, ajouter la
méthode à côté de `flyTo`/`highlight` :

```ts
fitBounds: (bbox, opts) => {
  mapRef.current?.fitBounds(
    [
      [bbox[0], bbox[1]],
      [bbox[2], bbox[3]],
    ],
    opts,
  );
},
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS (fichier entier).

- [ ] **Step 9: Faire pointer `PipelinePreviewMap.tsx` sur la fonction factorisée**

Dans `shell/src/builder/pipeline/PipelinePreviewMap.tsx`, remplacer les
définitions locales `collectCoordinates`/`computeBounds` par un import :

```ts
import { bboxFromFeatureCollection } from "../../lib/geometryBbox";
```

Et au site d'appel (`const bounds = computeBounds(features); if (bounds)
map.fitBounds(bounds, { padding: 20, maxZoom: 16 });`), adapter à la
nouvelle signature `[minX, minY, maxX, maxY]` (plate) au lieu de
`[[minLng,minLat],[maxLng,maxLat]]` :

```ts
const bbox = bboxFromFeatureCollection(features);
if (bbox) {
  map.fitBounds(
    [
      [bbox[0], bbox[1]],
      [bbox[2], bbox[3]],
    ],
    { padding: 20, maxZoom: 16 },
  );
}
```

Supprimer les fonctions `collectCoordinates`/`computeBounds` désormais
mortes dans ce fichier.

- [ ] **Step 10: Run test to verify no regression**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelinePreviewMap.test.tsx`
Expected: PASS — le test existant
`"fits the map to the bounds of the rendered features"` continue de
passer avec le même résultat numérique (la factorisation ne change pas le
calcul, seulement son point de définition).

- [ ] **Step 11: Commit**

```bash
git add shell/src/lib/geometryBbox.ts shell/src/lib/geometryBbox.test.ts \
  shell/src/map/MapView.tsx shell/src/map/MapView.test.tsx \
  shell/src/builder/pipeline/PipelinePreviewMap.tsx
git commit -m "feat(shell): fitBounds sur MapViewHandle, factorise le calcul de bbox client (D18 socle)"
```

---

### Task 7 : Auto-cadrage de l'éditeur de carte autonome sur `Item.bbox` (SP-A4, D18 — éditeur)

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/pages/MapEditorPage.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/pages/MapEditorPage.test.tsx`

**Interfaces:**
- Consumes: `MapViewHandle.fitBounds` (Task 6).
- Produces: `Item.bbox: [number, number, number, number] | null` (nouveau
  champ du type `Item`) — potentiellement utile à d'autres écrans plus
  tard, mais aucune tâche de ce plan n'en dépend d'autre que celle-ci.

- [ ] **Step 1: Write the failing test**

Dans `shell/src/pages/MapEditorPage.test.tsx`, ajouter (adapter le patron
de mock d'item déjà utilisé dans ce fichier pour `GET /items/{pk}`) :

```tsx
test("ajuste automatiquement la vue à l'emprise des données quand la vue est encore la valeur par défaut (D18)", async () => {
  server.use(
    http.get("https://core.test/v1/items/map-1", () =>
      HttpResponse.json({
        pk: "map-1",
        resourceType: "map",
        title: "Carte test",
        abstract: "",
        owner: "alice",
        thumbnailUrl: null,
        date: "2026-01-01T00:00:00Z",
        configId: "cfg-1",
        isPublished: false,
        bbox: [1, 10, 3, 20],
      }),
    ),
    http.get("https://core.test/v1/configs/cfg-1", () =>
      HttpResponse.json({
        kind: "map",
        basemap: { style: "https://demotiles.maplibre.org/style.json" },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: [{ id: "l1", title: "Couche", visible: true, kind: "feature", url: "https://x" }],
      }),
    ),
  );
  render(<MapEditorPage pk="map-1" />, { wrapper });
  await screen.findByText("Carte…");
  await waitFor(() => {
    expect(mapInstances[0]?.fitBoundsArgs).toHaveLength(1);
  });
  expect(mapInstances[0].fitBoundsArgs[0].bounds).toEqual([
    [1, 10],
    [3, 20],
  ]);
});

test("ne réajuste pas la vue quand elle diffère déjà de la valeur par défaut (vue sauvegardée par l'utilisateur, D18)", async () => {
  server.use(
    http.get("https://core.test/v1/items/map-2", () =>
      HttpResponse.json({
        pk: "map-2",
        resourceType: "map",
        title: "Carte test 2",
        abstract: "",
        owner: "alice",
        thumbnailUrl: null,
        date: "2026-01-01T00:00:00Z",
        configId: "cfg-2",
        isPublished: false,
        bbox: [1, 10, 3, 20],
      }),
    ),
    http.get("https://core.test/v1/configs/cfg-2", () =>
      HttpResponse.json({
        kind: "map",
        basemap: { style: "https://demotiles.maplibre.org/style.json" },
        view: { center: [5, 5], zoom: 9 },
        layers: [],
      }),
    ),
  );
  render(<MapEditorPage pk="map-2" />, { wrapper });
  await screen.findByText("Carte…");
  await waitFor(() => expect(mapInstances).toHaveLength(1));
  expect(mapInstances[0].fitBoundsArgs).toHaveLength(0);
});
```

Adapter les URLs mockées exactement au patron déjà en usage dans ce
fichier de test (nom du endpoint config, wrapper, import de
`mapInstances` depuis `../test/MockMaplibreMap`).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/pages/MapEditorPage.test.tsx -t "D18"`
Expected: FAIL — `mapInstances[0].fitBoundsArgs` reste vide dans le
premier test (aucun appel `fitBounds` n'est encore déclenché), et le
deuxième test échoue à la compilation TS si `Item.bbox` n'existe pas
encore sur le type (le mock JSON reste accepté au runtime, mais si le
test importe `Item` pour typer une variable intermédiaire, ça casserait
la compilation — sinon ignorer cette remarque).

- [ ] **Step 3: Write minimal implementation**

Dans `shell/src/api/types.ts`, ajouter au type `Item` (juste avant
`permissions: ItemPermissions;`) :

```ts
  bbox?: [number, number, number, number] | null;
```

Dans `shell/src/pages/MapEditorPage.tsx`, ajouter la constante de
comparaison et l'effet d'auto-cadrage. Juste après la déclaration de
`mapViewRef` :

```ts
const mapViewRef = useRef<MapViewHandle>(null);
const hasAutoFitted = useRef(false);
```

Et juste après le bloc `useEffect(() => { if (query.data) setDraft(query.data); }, [query.data]);`,
ajouter un nouvel effet :

```ts
// D18 : n'auto-cadrer que si la vue est encore la valeur par défaut
// littérale posée à la création (layers.ts:43) — jamais écraser un
// cadrage que l'utilisateur a explicitement enregistré. Le bouton manuel
// "Ajuster à l'emprise des données" (ci-dessous) reste la voie pour
// re-déclencher l'ajustement dans les autres cas.
useEffect(() => {
  if (hasAutoFitted.current) return;
  if (!draft) return;
  const isDefaultView = draft.view.center[0] === 2.4 && draft.view.center[1] === 46.6 && draft.view.zoom === 5;
  if (!isDefaultView) return;
  const bbox = itemQuery.data?.bbox;
  if (!bbox) return;
  hasAutoFitted.current = true;
  mapViewRef.current?.fitBounds(bbox);
}, [draft, itemQuery.data?.bbox]);
```

Ajouter le bouton manuel juste après `<CameraControls ... />` dans le
panneau `inspect` :

```tsx
<Button
  variant="outline"
  size="sm"
  disabled={!itemQuery.data?.bbox}
  onClick={() => {
    const bbox = itemQuery.data?.bbox;
    if (bbox) mapViewRef.current?.fitBounds(bbox);
  }}
>
  {t("mapEditor.fitToDataButton")}
</Button>
```

Dans `shell/src/i18n/catalog.fr.ts`, ajouter près de
`"cameraControls.resetButton"` :

```ts
"mapEditor.fitToDataButton": "Ajuster à l'emprise des données",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/MapEditorPage.test.tsx`
Expected: PASS (fichier entier).

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/types.ts shell/src/pages/MapEditorPage.tsx \
  shell/src/i18n/catalog.fr.ts shell/src/pages/MapEditorPage.test.tsx
git commit -m "feat(shell): auto-cadrage de l'éditeur de carte sur l'emprise des données (D18)"
```

---

### Task 8 : Auto-cadrage du widget carte sur les données chargées (SP-A4, D18 — widget)

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `MapViewHandle.fitBounds` et `bboxFromFeatureCollection`
  (Task 6).
- Produces: rien consommé par une tâche ultérieure.

- [ ] **Step 1: Write the failing test**

Dans `shell/src/builder/widgets/mapWidget.test.tsx`, étendre le mock de
`MapView` pour exposer un `fitBoundsSpy`, à côté de `flyToSpy`/
`highlightSpy` :

```ts
const flyToSpy = vi.fn();
const highlightSpy = vi.fn();
const fitBoundsSpy = vi.fn();
```

et dans `useImperativeHandle(ref, () => ({ flyTo: flyToSpy, highlight:
highlightSpy }));`, ajouter `fitBounds: fitBoundsSpy`.

Ajouter un nouveau test (utiliser le patron de montage déjà en place dans
ce fichier pour le widget `map`, avec un `ctx.data` contenant des
`records` géométriques — cf. les tests voisins de flyTo pour le patron
exact de construction du contexte) :

```tsx
test("ajuste automatiquement la vue à l'emprise des enregistrements chargés (D18)", async () => {
  fitBoundsSpy.mockClear();
  const records = [
    { id: 1, properties: {}, geometry: { type: "Point", coordinates: [1, 10] } },
    { id: 2, properties: {}, geometry: { type: "Point", coordinates: [3, 20] } },
  ];
  // Monter le widget map avec ce jeu de records dans ctx.data, selon le
  // patron déjà utilisé par les tests voisins "map flyTo action..." de ce
  // fichier (ActionBus/ExplorerProvider/AnalyticsContextProvider).
  // ... (rendu identique au patron existant, seul ctx.data.records change)
  await waitFor(() => expect(fitBoundsSpy).toHaveBeenCalledTimes(1));
  expect(fitBoundsSpy).toHaveBeenCalledWith([1, 10, 3, 20]);
});
```

Note pour l'implémenteur : ce fichier de test construit son contexte via
un helper de rendu déjà en place plus haut dans le fichier (utilisé par
les tests `"map flyTo action..."`) — reprendre exactement ce helper, en
substituant seulement le contenu de `records` passé à `ctx.data`. Ne pas
réinventer le montage.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx -t "D18"`
Expected: FAIL — `fitBoundsSpy` jamais appelé (le widget ne calcule
aucune emprise aujourd'hui).

- [ ] **Step 3: Write minimal implementation**

Dans `shell/src/builder/widgets/mapWidget.tsx`, ajouter l'import :

```ts
import { bboxFromFeatureCollection } from "../../lib/geometryBbox";
```

Dans `Component`, juste après la déclaration de `handle` :

```ts
const handle = useRef<MapViewHandle>(null);
const client = useItemClient();
const lastFittedUrl = useRef<string | null>(null);
```

Et juste avant le `return (`, ajouter :

```ts
const records = ctx.data?.records;
useEffect(() => {
  if (!url || !records || records.length === 0) return;
  if (lastFittedUrl.current === url) return;
  const features: GeoJSON.Feature[] = records
    .filter((r) => r.geometry)
    .map((r) => ({ type: "Feature", properties: {}, geometry: r.geometry as GeoJSON.Geometry }));
  const bbox = bboxFromFeatureCollection(features);
  if (!bbox) return;
  lastFittedUrl.current = url;
  handle.current?.fitBounds(bbox);
}, [url, records]);
```

(`useEffect` doit être importé depuis `react` en tête de fichier — vérifier
qu'il l'est déjà, sinon l'ajouter à l'import existant.)

Ajouter le bouton manuel dans le `PropsPanel`, juste après
`<CameraControls .../>` :

```tsx
<Button
  variant="outline"
  size="sm"
  onClick={() => {
    // Le PropsPanel n'a pas accès à ctx.data (c'est une prop du seul
    // Component) — ce bouton ne peut donc pas ajuster la vue lui-même ici ;
    // ré-émettre un événement du bus vers l'action déjà exposée serait
    // hors-scope pour ce lot (le widget n'expose pas d'action fitBounds au
    // bus). Choix de scope : bouton visible côté auteur, mais l'unique
    // ajustement garanti reste l'automatique déclenché par les données.
  }}
  disabled
  title={t("widgetMap.fitToDataUnavailableInPropsPanel")}
>
  {t("mapEditor.fitToDataButton")}
</Button>
```

Repenser cette étape : le `PropsPanel` n'a pas accès aux données de la
`DataSource` de la même manière que le `Component` (il connaît la
`DataSource` sélectionnée, pas ses enregistrements chargés) — **ne pas
ajouter de bouton manuel désactivé sans valeur** ; à la place, supprimer
ce bloc et se limiter à l'auto-cadrage automatique (déjà suffisant : le
widget n'a de toute façon aucune vue persistée à préserver, contrairement
à l'éditeur autonome de Task 7, donc l'automatique seul couvre le besoin).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: PASS (fichier entier).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx
git commit -m "feat(shell): auto-cadrage du widget carte sur les données chargées (D18)"
```

---

### Task 9 : Widget carte — couches additionnelles raster/vector-direct/deck/tiles3d (SP-A5, D13)

**Files:**
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Test: `shell/src/builder/widgets/mapWidget.test.tsx`

**Interfaces:**
- Consumes: `LayerPicker` (`shell/src/map/LayerPicker.tsx`, prop `onAdd:
  (layer: MapLayer) => void`), `LayersPanel` (`shell/src/map/LayersPanel.tsx`,
  props `layers: MapLayer[]`, `onChange: (layers: MapLayer[]) => void`) —
  tous deux déjà existants, non modifiés par cette tâche.
- Produces: `props.layers: MapLayer[]` (nouvelle prop du widget carte,
  persistée dans `AppConfig`) — ne casse pas les configs existantes
  (absence de `layers` ⇒ `[]` par défaut).

- [ ] **Step 1: Write the failing test**

Dans `shell/src/builder/widgets/mapWidget.test.tsx`, ajouter :

```tsx
test("le widget carte fusionne la couche feature liée à la DataSource avec les couches additionnelles de props.layers (D13)", () => {
  // Monter le widget map avec dataSourceId défini (ctx.data.url non vide,
  // patron déjà utilisé par les tests voisins) et
  // props = { dataSourceId: "ds-1", layers: [{ id: "raster-1", title: "Ortho",
  // visible: true, kind: "raster", tilesUrl: "https://x/{z}/{x}/{y}.png" }] }
  // ... (rendu identique au patron existant "map flyTo action...")
  expect(lastConfig?.layers).toHaveLength(2);
  expect(lastConfig?.layers[0].kind).toBe("feature");
  expect(lastConfig?.layers[1]).toMatchObject({ id: "raster-1", kind: "raster" });
});

test("le PropsPanel du widget carte permet d'ajouter une couche raster via LayerPicker (D13)", async () => {
  const onChange = vi.fn();
  const PropsPanel = getWidget("map")!.PropsPanel!;
  render(
    <PropsPanel
      props={{ dataSourceId: "ds-1", layers: [] }}
      onChange={onChange}
      dataSources={[{ id: "ds-1", type: "features", label: "Source", datasetId: "d1", layer: "col-1" }]}
      theme={undefined}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: /ajouter une couche/i }));
  // Reprendre exactement le flux d'ajout déjà testé dans LayerPicker.test.tsx
  // (choix "raster" puis renseignement de l'URL de tuiles), puis :
  await waitFor(() =>
    expect(onChange).toHaveBeenCalledWith(
      expect.objectContaining({ layers: expect.arrayContaining([expect.objectContaining({ kind: "raster" })]) }),
    ),
  );
});
```

Note pour l'implémenteur : reprendre le patron exact de rendu du
`PropsPanel` déjà utilisé par les tests existants de ce fichier (fonction
`renderPropsPanel` mentionnée par la recherche à la ligne 126) plutôt que
d'en écrire un nouveau ; et reprendre le libellé/flux exact du bouton
"Ajouter une couche" de `LayerPicker.test.tsx` pour le second test (ne
pas deviner le texte du bouton — le lire dans ce fichier de test existant
avant d'écrire l'assertion).

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx -t "D13"`
Expected: FAIL — `lastConfig?.layers` a toujours longueur ≤ 1
aujourd'hui, et aucun `LayerPicker` n'est monté dans le `PropsPanel`
actuel (`screen.getByRole("button", { name: /ajouter une couche/i })`
lève une erreur "not found").

- [ ] **Step 3: Write minimal implementation**

Dans `shell/src/builder/widgets/mapWidget.tsx`, ajouter les imports :

```ts
import { LayerPicker } from "../../map/LayerPicker";
import { LayersPanel } from "../../map/LayersPanel";
import type { MapLayer } from "../../api/types";
```

Changer `defaultProps` :

```ts
defaultProps: { dataSourceId: "", layers: [] },
```

Dans `PropsPanel`, ajouter juste avant le `<PopupEditor ... />` final :

```tsx
<div className="flex flex-col gap-2 border-t border-rule pt-2">
  <h3 className="text-xs font-semibold uppercase text-ink-2">
    {t("widgetMap.additionalLayersHeading")}
  </h3>
  <LayerPicker
    onAdd={(layer) =>
      onChange({ ...props, layers: [...((props.layers as MapLayer[] | undefined) ?? []), layer] })
    }
  />
  <LayersPanel
    layers={(props.layers as MapLayer[] | undefined) ?? []}
    onChange={(layers) => onChange({ ...props, layers })}
  />
</div>
```

Dans `Component`, remplacer la construction de `config.layers` :

```ts
layers: url
  ? [
      {
        id: `ds-${String(props.dataSourceId)}`,
        title: t("widgetMap.layerTitle"),
        visible: true,
        kind: "feature",
        url,
        renderAs,
        ...(symbology ? { symbology } : {}),
        popup: props.popup as PopupConfig | undefined,
        collectionId: ctx.data?.collectionId,
        pkColumn: ctx.data?.pkColumn,
      },
    ]
  : [],
```

par :

```ts
layers: [
  ...(url
    ? [
        {
          id: `ds-${String(props.dataSourceId)}`,
          title: t("widgetMap.layerTitle"),
          visible: true,
          kind: "feature" as const,
          url,
          renderAs,
          ...(symbology ? { symbology } : {}),
          popup: props.popup as PopupConfig | undefined,
          collectionId: ctx.data?.collectionId,
          pkColumn: ctx.data?.pkColumn,
        },
      ]
    : []),
  ...((props.layers as MapLayer[] | undefined) ?? []),
],
```

Dans `shell/src/i18n/catalog.fr.ts`, ajouter :

```ts
"widgetMap.additionalLayersHeading": "Couches additionnelles",
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/mapWidget.test.tsx`
Expected: PASS (fichier entier — vérifier notamment qu'aucun test
existant n'affirmait `config.layers` à longueur exactement 1 sans tenir
compte de `props.layers` désormais toujours défini par `defaultProps`
comme `[]`, ce qui ne devrait rien changer pour les configs sans couche
additionnelle).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/widgets/mapWidget.tsx shell/src/builder/widgets/mapWidget.test.tsx shell/src/i18n/catalog.fr.ts
git commit -m "feat(shell): le widget carte peut porter des couches additionnelles raster/deck/tiles3d (D13)"
```

---

### Task 10 : Suppression de secret côté shell (SP-A6, D05 — UI)

**Files:**
- Modify: `shell/src/builder/pipeline/SecretParamSelect.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/pipeline/SecretParamSelect.test.tsx`

**Interfaces:**
- Consumes: `useDeleteSecret` (`shell/src/api/domains/secrets.hooks.ts`,
  déjà implémenté et testé au niveau `itemClient.ts`), `ConfirmDialog`
  (`shell/src/ui/kit/ConfirmDialog.tsx`, props `open, title, message,
  confirmLabel, onConfirm, onCancel, pending?`).
- Produces: rien consommé par une tâche ultérieure.

- [ ] **Step 1: Write the failing test**

Dans `shell/src/builder/pipeline/SecretParamSelect.test.tsx` (créer si le
fichier n'existe pas encore — vérifier d'abord), ajouter :

```tsx
test("supprime un secret après confirmation (D05)", async () => {
  server.use(
    http.get("https://core.test/v1/secrets", () =>
      HttpResponse.json([{ id: "s1", name: "api-key", kind: "generic", createdAt: "", updatedAt: "" }]),
    ),
    http.delete("https://core.test/v1/secrets/s1", () => new HttpResponse(null, { status: 204 })),
  );
  render(<SecretParamSelect value="" onChange={() => {}} ariaLabel="Secret" />, { wrapper });
  await screen.findByRole("option", { name: "api-key" });
  await userEvent.click(screen.getByRole("button", { name: /supprimer.*api-key/i }));
  await screen.findByRole("dialog");
  await userEvent.click(screen.getByRole("button", { name: t("confirmDialog.cancel") }));
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /supprimer.*api-key/i }));
  await userEvent.click(await screen.findByRole("button", { name: /^supprimer$/i }));
  await waitFor(() => expect(screen.queryByRole("option", { name: "api-key" })).not.toBeInTheDocument());
});
```

Adapter `wrapper`/imports (`server`, `http`, `HttpResponse`, `t`) au
patron déjà utilisé par les autres fichiers de test de
`builder/pipeline/`.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/SecretParamSelect.test.tsx -t "D05"`
Expected: FAIL — aucun bouton "supprimer" n'existe encore, `getByRole`
lève une erreur.

- [ ] **Step 3: Write minimal implementation**

Dans `shell/src/builder/pipeline/SecretParamSelect.tsx`, ajouter les
imports :

```ts
import { useDeleteSecret, useListSecrets } from "../../api/domains/secrets.hooks";
import { ConfirmDialog } from "../../ui/kit/ConfirmDialog";
```

Remplacer le rendu `<select>` par une liste avec un bouton de suppression
par option. Ajouter l'état local nécessaire en tête du composant :

```ts
const deleteSecret = useDeleteSecret();
const [pendingDeleteId, setPendingDeleteId] = useState<string | null>(null);
```

Remplacer le bloc du `<select>` (garder le `<select>` inchangé pour la
sélection, ajouter la liste de gestion juste en dessous) :

```tsx
<ul className="flex flex-col gap-1">
  {options.map((s) => (
    <li key={s.id} className="flex items-center justify-between gap-2 text-xs text-ink-2">
      <span>{s.name}</span>
      <button
        type="button"
        className="text-danger hover:underline"
        onClick={() => setPendingDeleteId(s.id)}
      >
        {t("secretParamSelect.deleteButton", { name: s.name })}
      </button>
    </li>
  ))}
</ul>
<ConfirmDialog
  open={pendingDeleteId !== null}
  title={t("secretParamSelect.deleteConfirmTitle")}
  message={t("secretParamSelect.deleteConfirmMessage")}
  confirmLabel={t("secretParamSelect.deleteConfirmButton")}
  pending={deleteSecret.isPending}
  onCancel={() => setPendingDeleteId(null)}
  onConfirm={() => {
    if (!pendingDeleteId) return;
    deleteSecret.mutate(pendingDeleteId, { onSuccess: () => setPendingDeleteId(null) });
  }}
/>
```

Dans `shell/src/i18n/catalog.fr.ts`, ajouter :

```ts
"secretParamSelect.deleteButton": "Supprimer {name}",
"secretParamSelect.deleteConfirmTitle": "Supprimer ce secret ?",
"secretParamSelect.deleteConfirmMessage": "Cette action est irréversible. Tout pipeline référençant ce secret échouera à sa prochaine exécution.",
"secretParamSelect.deleteConfirmButton": "Supprimer",
```

(Adapter `t(...)` à la convention d'interpolation réellement supportée
par `shell/src/i18n/index.ts` — si l'interpolation `{name}` n'est pas
supportée par ce système de traduction minimal, utiliser à la place
`t("secretParamSelect.deleteButton") + " " + s.name` et ajuster le test
en conséquence.)

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/builder/pipeline/SecretParamSelect.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/SecretParamSelect.tsx shell/src/i18n/catalog.fr.ts shell/src/builder/pipeline/SecretParamSelect.test.tsx
git commit -m "feat(shell): suppression de secret avec confirmation (D05)"
```

---

### Task 11 : Outil MCP `delete_secret` (SP-A6, D05 — MCP)

**Files:**
- Create: `core/app/mcp/tools/secrets.py`
- Modify: `core/app/mcp/tools/__init__.py`
- Test: `core/tests/mcp/test_secrets_tools.py` (créer — vérifier d'abord le
  chemin exact des tests MCP existants, ex. `core/tests/mcp/test_sharing_tools.py`,
  et suivre son patron de fixtures)

**Interfaces:**
- Consumes: `repo.get_secret`, `repo.delete_secret`
  (`core/app/secrets/repository.py`), `require_any_privilege`
  (`app/roles/guards`), `Privilege.ADMIN_SECRETS_MANAGE`,
  `Privilege.AUTOMATION_SECRETS_MANAGE` (`app/roles/privileges.py`),
  `resolve_actor`/`http_exception_to_value_error`
  (`app/mcp/tools/identity.py`), `write_tool`
  (`app/mcp/tools/write_tools.py`), `write_audit` (`app/audit/writer.py`).
- Produces: tool MCP `delete_secret(secret_id: str) -> None`, enregistré
  dans `register_tools`.

- [ ] **Step 1: Write the failing test**

D'abord, lire `core/tests/mcp/test_sharing_tools.py` (ou équivalent le
plus proche) pour reprendre exactement son patron de fixtures
(`session_factory`, création d'un utilisateur/tenant de test, appel du
tool via le serveur MCP de test). Écrire ensuite
`core/tests/mcp/test_secrets_tools.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.roles.privileges import Privilege
from app.secrets import repository as secrets_repo
from app.secrets.schemas import SecretCreate, SecretPayload


def test_delete_secret_removes_it_and_writes_audit(mcp_test_context, tenant, session_factory):
    with session_factory() as session:
        secret = secrets_repo.create_secret(
            session,
            tenant_id=tenant.id,
            created_by="u1",
            name="api-key",
            kind="generic",
            ciphertext=b"x",
            nonce=b"y",
        )
        session.commit()
        secret_id = secret.id

    mcp_test_context.call_tool("delete_secret", {"secret_id": secret_id})

    with session_factory() as session:
        assert secrets_repo.get_secret(session, tenant_id=tenant.id, secret_id=secret_id) is None


def test_delete_secret_requires_the_same_privilege_as_the_rest_route(mcp_test_context_without_privilege):
    with pytest.raises(ValueError):
        mcp_test_context_without_privilege.call_tool("delete_secret", {"secret_id": "does-not-matter"})
```

Adapter les noms de fixtures (`mcp_test_context`, `tenant`,
`session_factory`, `mcp_test_context_without_privilege`) à ceux
réellement définis dans `core/tests/mcp/conftest.py` ou équivalent — ne
pas les inventer sans avoir vérifié leur nom exact dans le fichier de
test voisin choisi comme modèle.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/mcp/test_secrets_tools.py -v`
Expected: FAIL — le module `app/mcp/tools/secrets.py` n'existe pas
encore, ou le tool `delete_secret` n'est pas enregistré.

- [ ] **Step 3: Write minimal implementation**

Créer `core/app/mcp/tools/secrets.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Tool MCP du domaine secrets : delete_secret (SP-A6/D05). Garde
strictement identique à DELETE /secrets/{id} (app/secrets/routes.py) —
REV-009 : ne jamais rouvrir côté MCP un trou fermé côté REST."""

from fastapi import HTTPException
from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.audit.writer import write_audit
from app.auth.dependency import is_read_only_mode
from app.db import request_scoped_session
from app.mcp.tools.identity import http_exception_to_value_error, resolve_actor
from app.mcp.tools.write_tools import write_tool
from app.roles.guards import require_any_privilege
from app.roles.privileges import Privilege
from app.secrets import repository as repo


def register(server: FastMCP, session_factory) -> None:
    @server.tool()
    @write_tool
    async def delete_secret(ctx: Context, secret_id: str) -> None:
        """Delete a connector secret — mirrors DELETE /secrets/{id}."""
        if is_read_only_mode():
            raise ValueError("Mode démo : lecture seule, écritures désactivées.")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            try:
                require_any_privilege(
                    session,
                    user,
                    [
                        Privilege.ADMIN_SECRETS_MANAGE.value,
                        Privilege.AUTOMATION_SECRETS_MANAGE.value,
                    ],
                )
            except HTTPException as exc:
                raise http_exception_to_value_error(exc) from exc
            secret = repo.get_secret(session, tenant_id=user.tenant_id, secret_id=secret_id)
            if secret is None:
                raise ValueError("secret not found")
            name, kind = secret.name, secret.kind
            repo.delete_secret(session, secret)
            write_audit(
                session,
                tenant_id=user.tenant_id,
                actor_id=user.id,
                actor_kind="agent",
                action="secret.delete",
                object_type="secret",
                object_id=secret_id,
                payload={"name": name, "kind": kind},
            )
```

Dans `core/app/mcp/tools/__init__.py`, ajouter `secrets` à l'import et à
la boucle `register_tools` :

```python
from app.mcp.tools import (
    alerts,
    analytics,
    attachments,
    bookmark,
    catalog,
    configs,
    dataset,
    identity,
    pipelines,
    query_generation,
    reports,
    secrets,
    sharing,
)
```

```python
def register_tools(server: FastMCP, session_factory) -> None:
    for module in (
        identity,
        catalog,
        configs,
        dataset,
        bookmark,
        analytics,
        query_generation,
        pipelines,
        alerts,
        reports,
        sharing,
        attachments,
        secrets,
    ):
        module.register(server, session_factory)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/mcp/test_secrets_tools.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full core test suite to check for registration-order regressions**

Run: `cd core && uv run pytest tests/test_feature_inventory.py -v`
Expected: FAIL attendu à ce stade précis (le nouveau tool MCP
`delete_secret` n'est pas encore inventorié) — traité en Task 13
(clôture). Noter ce point, ne pas tenter de le corriger ici.

- [ ] **Step 6: Commit**

```bash
git add core/app/mcp/tools/secrets.py core/app/mcp/tools/__init__.py core/tests/mcp/test_secrets_tools.py
git commit -m "feat(core): outil MCP delete_secret, garde identique à la route REST (D05)"
```

---

### Task 12 : Réouverture d'un pipeline wizard vers son éditeur d'origine (SP-A7, D58)

**Files:**
- Create: `shell/src/shell/resolvePipelineEditorPath.ts`
- Modify: `shell/src/shell/useOpenItem.ts`
- Modify: `shell/src/shell/routes.tsx`
- Test: `shell/src/shell/resolvePipelineEditorPath.test.ts`
- Test: `shell/src/shell/routes.test.tsx`

**Interfaces:**
- Produces: `resolvePipelineEditorPath(client: ItemClient, pk: string):
  Promise<string>` — **consommée par `useOpenItem.ts` et
  `ItemDetailRoute` (`routes.tsx`)**, dans cette même tâche.

- [ ] **Step 1: Write the failing test — `resolvePipelineEditorPath`**

Créer `shell/src/shell/resolvePipelineEditorPath.test.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect, vi } from "vitest";
import { resolvePipelineEditorPath } from "./resolvePipelineEditorPath";
import type { ItemClient, PipelinePayload } from "../api/types";

function fakeClient(config: PipelinePayload | (() => Promise<PipelinePayload>)): ItemClient {
  return {
    getPipelineConfig: vi.fn(async () => (typeof config === "function" ? await config() : config)),
  } as unknown as ItemClient;
}

test("route vers le wizard quand la forme du pipeline est reconnaissable", async () => {
  const wizardShaped: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.collection", params: { collectionId: "c1" } },
      { id: "w1", kind: "writer", op: "writer.dataset", params: {} },
    ],
    edges: [{ from: "r1", to: "w1" }],
  };
  const path = await resolvePipelineEditorPath(fakeClient(wizardShaped), "pl-1");
  expect(path).toBe("/datasets/visual-query/pl-1/edit");
});

test("route vers le DAG complet quand la forme n'est pas reconnaissable par le wizard", async () => {
  const handEdited: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.connector.rest", params: {} },
      { id: "w1", kind: "writer", op: "writer.dataset", params: {} },
    ],
    edges: [{ from: "r1", to: "w1" }],
  };
  const path = await resolvePipelineEditorPath(fakeClient(handEdited), "pl-2");
  expect(path).toBe("/pipelines/pl-2/edit");
});

test("retombe sur le DAG complet si la récupération de la config échoue", async () => {
  const path = await resolvePipelineEditorPath(
    fakeClient(() => Promise.reject(new Error("network"))),
    "pl-3",
  );
  expect(path).toBe("/pipelines/pl-3/edit");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/shell/resolvePipelineEditorPath.test.ts`
Expected: FAIL — le module n'existe pas.

- [ ] **Step 3: Write minimal implementation**

Créer `shell/src/shell/resolvePipelineEditorPath.ts` :

```ts
// SPDX-License-Identifier: Apache-2.0
// D58 : un pipeline créé par le wizard no-code (SP-14o) doit se rouvrir
// dans le wizard s'il est toujours dans une forme qu'il sait relire, et
// dans le DAG complet sinon — jamais l'inverse systématique d'avant. Point
// d'entrée unique appelé par useOpenItem.ts ET ItemDetailRoute
// (routes.tsx) : évite la duplication qui avait laissé les deux dispatchers
// hardcoder /pipelines/{pk}/edit indépendamment (piège CLAUDE.md n°4).
import { decompilePipelineToWizardState } from "../builder/visualQuery/compilePipeline";
import type { ItemClient } from "../api/types";

export async function resolvePipelineEditorPath(client: ItemClient, pk: string): Promise<string> {
  try {
    const config = await client.getPipelineConfig(pk);
    const wizardState = decompilePipelineToWizardState(config);
    return wizardState !== null ? `/datasets/visual-query/${pk}/edit` : `/pipelines/${pk}/edit`;
  } catch {
    return `/pipelines/${pk}/edit`;
  }
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/shell/resolvePipelineEditorPath.test.ts`
Expected: PASS.

- [ ] **Step 5: Write the failing test — intégration dans `useOpenItem`**

Dans `shell/src/shell/routes.test.tsx`, le test existant
`"opening a pipeline navigates to its editor, not a generic app editor"`
(lignes ~358-384) mocke `PipelineBuilderPage` mais pas
`VisualQueryWizardPage` ni l'endpoint de config pipeline. Ajouter un mock
pour `VisualQueryWizardPage` à côté du mock existant de
`PipelineBuilderPage` :

```ts
vi.mock("../pages/VisualQueryWizardPage", () => ({
  VisualQueryWizardPage: () => <div>visual-query-wizard</div>,
}));
```

Ajouter deux nouveaux tests juste après le test existant :

```tsx
test("opening a wizard-shaped pipeline navigates to the visual query wizard (D58)", async () => {
  server.use(
    http.get("https://core.test/v1/items", () =>
      HttpResponse.json([
        {
          pk: "pl-2",
          resourceType: "pipeline",
          title: "Pipeline wizard",
          abstract: "",
          owner: "alice",
          thumbnailUrl: null,
          date: "",
          configId: "cfg-2",
          isPublished: false,
        },
      ]),
    ),
    http.get("https://core.test/v1/pipelines/pl-2", () =>
      HttpResponse.json({
        nodes: [
          { id: "r1", kind: "reader", op: "reader.collection", params: { collectionId: "c1" } },
          { id: "w1", kind: "writer", op: "writer.dataset", params: {} },
        ],
        edges: [{ from: "r1", to: "w1" }],
      }),
    ),
  );
  render(<AppRoutes />, { wrapper });
  await userEvent.click(await screen.findByRole("button", { name: /ouvrir/i }));
  expect(await screen.findByText("visual-query-wizard")).toBeInTheDocument();
});

test("opening a hand-edited pipeline still navigates to the full DAG editor (D58, non-régression)", async () => {
  server.use(
    http.get("https://core.test/v1/items", () =>
      HttpResponse.json([
        {
          pk: "pl-1",
          resourceType: "pipeline",
          title: "Pipeline DAG",
          abstract: "",
          owner: "alice",
          thumbnailUrl: null,
          date: "",
          configId: "cfg-1",
          isPublished: false,
        },
      ]),
    ),
    http.get("https://core.test/v1/pipelines/pl-1", () =>
      HttpResponse.json({
        nodes: [
          { id: "r1", kind: "reader", op: "reader.connector.rest", params: {} },
          { id: "w1", kind: "writer", op: "writer.dataset", params: {} },
        ],
        edges: [{ from: "r1", to: "w1" }],
      }),
    ),
  );
  render(<AppRoutes />, { wrapper });
  await userEvent.click(await screen.findByRole("button", { name: /ouvrir/i }));
  expect(await screen.findByText("pipeline-builder-pl-1")).toBeInTheDocument();
});
```

Adapter les URLs mockées exactement au chemin réel de
`client.getPipelineConfig` (vérifier dans `api/domains/pipelines.ts` le
chemin exact — `GET /pipelines/{pk}` supposé ici par cohérence avec le
reste du domaine, à confirmer en lisant ce fichier avant d'écrire le test
définitif).

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx -t "D58"`
Expected: FAIL — `useOpenItem`/`ItemDetailRoute` naviguent encore
inconditionnellement vers `/pipelines/${pk}/edit`.

- [ ] **Step 7: Write minimal implementation**

Dans `shell/src/shell/useOpenItem.ts`, ajouter l'import :

```ts
import { resolvePipelineEditorPath } from "./resolvePipelineEditorPath";
```

Remplacer :

```ts
if (type === "pipeline") {
  navigate(`/pipelines/${pk}/edit`);
  return;
}
```

par :

```ts
if (type === "pipeline") {
  const path = await resolvePipelineEditorPath(client, pk);
  navigate(path);
  return;
}
```

Dans `shell/src/shell/routes.tsx`, `ItemDetailRoute` doit devenir capable
d'un dispatch asynchrone. Remplacer :

```tsx
function ItemDetailRoute() {
  const { pk } = useParams();
  const navigate = useNavigate();
  return (
    <ItemDetailPage
      pk={pk!}
      onDeleted={() => navigate("/")}
      onOpenEditor={(type) =>
        navigate(
          type === "map"
            ? `/maps/${pk}`
            : type === "dataset"
              ? `/datasets/${pk}/edit`
              : type === "pipeline"
                ? `/pipelines/${pk}/edit`
                : `/apps/${pk}/edit`,
        )
      }
    />
  );
}
```

par :

```tsx
function ItemDetailRoute() {
  const { pk } = useParams();
  const navigate = useNavigate();
  const client = useItemClient();
  return (
    <ItemDetailPage
      pk={pk!}
      onDeleted={() => navigate("/")}
      onOpenEditor={(type) => {
        if (type === "pipeline") {
          void resolvePipelineEditorPath(client, pk!).then((path) => navigate(path));
          return;
        }
        navigate(
          type === "map"
            ? `/maps/${pk}`
            : type === "dataset"
              ? `/datasets/${pk}/edit`
              : `/apps/${pk}/edit`,
        );
      }}
    />
  );
}
```

(`useItemClient` doit être importé dans `routes.tsx` — vérifier qu'il
l'est déjà pour un autre composant du fichier, sinon ajouter
`import { useItemClient } from "../api/ItemClientProvider";`.)

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/shell/useOpenItem.test.ts src/shell/routes.test.tsx src/shell/resolvePipelineEditorPath.test.ts`

(Si `useOpenItem.test.ts` n'existe pas — confirmé probable par la
recherche — ignorer ce chemin, seul `routes.test.tsx` couvre ce hook
indirectement.)

Expected: PASS (tous les fichiers).

- [ ] **Step 9: Commit**

```bash
git add shell/src/shell/resolvePipelineEditorPath.ts shell/src/shell/resolvePipelineEditorPath.test.ts \
  shell/src/shell/useOpenItem.ts shell/src/shell/routes.tsx shell/src/shell/routes.test.tsx
git commit -m "feat(shell): réouvre un pipeline wizard-shaped dans le wizard, pas systématiquement le DAG (D58)"
```

---

### Task 13 : Clôture — OpenAPI/types, inventaire de fonctionnalités, CLAUDE.md, backlog

**Files:**
- Modify: `shell/src/api/generated/core-schema.d.ts` (régénéré, pas édité
  à la main)
- Modify: `core/openapi.json` (régénéré, pas édité à la main)
- Modify: `docs/revue/inventaire-fonctionnalites.jsonl`
- Modify: `docs/revue/bilan-fonctionnalites.md` / `.html` (régénérés)
- Modify: `docs/revue/2026-09-04-backlog.md`
- Modify: `CLAUDE.md`

**Interfaces:** aucune — tâche de clôture documentaire/génération, pas de
code produit ni consommé.

- [ ] **Step 1: Régénérer la spec OpenAPI et les types TS**

Run:
```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Expected: `core/openapi.json` gagne le champ `bbox` sur `ItemRead` (déjà
exposé avant ce plan, donc probablement déjà présent — vérifier par
`git diff` que rien d'inattendu ne change) ; pas de nouvelle route REST
introduite par ce plan (Task 11 n'ajoute qu'un tool MCP), donc le diff
attendu ici est **vide ou quasi vide**, ce qui est normal et volontaire —
ne pas chercher à forcer un diff.

- [ ] **Step 2: Ajouter la nouvelle surface MCP à l'inventaire de fonctionnalités**

Dans `docs/revue/inventaire-fonctionnalites.jsonl`, lire d'abord une
entrée existante de tool MCP (ex. `create_group`) pour reprendre son
schéma JSON exact ligne par ligne, puis ajouter une entrée pour
`delete_secret` avec le même schéma, `surface: "mcp_tool"`,
`nom: "delete_secret"`, domaine `secrets`.

- [ ] **Step 3: Régénérer le bilan de fonctionnalités**

Run: `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --write`

Expected: exit 0, `docs/revue/bilan-fonctionnalites.md`/`.html` mis à
jour, aucune surface non inventoriée signalée.

- [ ] **Step 4: Mettre à jour le statut des REV proposées dans le backlog**

Dans `docs/revue/2026-09-04-backlog.md`, marquer `REV-201` (D02),
`REV-202` (D03), `REV-203` (D09), `REV-204` (D05), `REV-205` (D58),
`REV-206` (D13) comme fermées, chacune avec une ligne pointant vers ce
plan (`docs/superpowers/plans/2026-09-24-vague-a-bloquants-decouvrabilite.md`)
et le commit de clôture. D01 n'a pas de numéro REV propre dans la liste
proposée (déjà couvert par `GAP-80`/`GAP-81` existants) — mettre à jour
leur statut dans `docs/revue/2026-09-04-analyse-gaps.md` si ce document
les listait encore comme ouverts.

- [ ] **Step 5: Une ligne dans `CLAUDE.md` § Livré**

Ajouter, dans l'ordre chronologique du fichier :

```markdown
- **Vague A diagnostic UI/UX (7 SP)** — découvrabilité `/bookmarks`/
  `/analytics/sql`, édition d'item Site, garde `automation.manage` +
  message d'indisponibilité sur la création de pipeline, auto-cadrage
  carte sur l'emprise des données (éditeur + widget), widget carte
  multi-couches (raster/deck/tiles3d additionnels), suppression de
  secret (UI+MCP), réouverture d'un pipeline wizard vers son éditeur
  d'origine. Ferme REV-201 à REV-206.
```

Ne pas ajouter de récit détaillé ici (garde-fou taille CLAUDE.md, cf.
§ Livré du fichier lui-même) — le détail va dans
`docs/superpowers/2026-08-27-historique-execution-continu.md`.

- [ ] **Step 6: Run every quality gate**

Run:
```bash
cd shell && npm run lint && npm run format:check && npx tsc --noEmit
cd shell && npm test -- --run
cd shell && npm run e2e
cd core && uv run ruff check . && uv run ruff format --check .
cd core && uv run pytest
cd core && uv run lint-imports
python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold
```

Expected: tout vert. Tout échec ici doit être diagnostiqué et corrigé
avant de considérer la vague A terminée — ne pas committer cette tâche
tant qu'un de ces gates est rouge.

- [ ] **Step 7: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts \
  docs/revue/inventaire-fonctionnalites.jsonl docs/revue/bilan-fonctionnalites.md \
  docs/revue/bilan-fonctionnalites.html docs/revue/2026-09-04-backlog.md \
  docs/revue/2026-09-04-analyse-gaps.md CLAUDE.md
git commit -m "docs: clôture la vague A du diagnostic UI/UX (REV-201 à REV-206)"
```

---

## Self-Review

**1. Couverture du spec** : SP-A1→A7 = Tasks 2/3, 1, 4/5, 6/7/8, 9, 10/11,
12. Les 2 filets anti-régression de vague A = Task 3 (route reachability)
et Task 4 (matrice rôle×flag). Clôture documentaire (piège CLAUDE.md n°1 :
OpenAPI/types ; obligation de clôture SP : inventaire+bilan+CLAUDE.md+backlog)
= Task 13. Aucun défaut de la vague A sans tâche.

**2. Placeholders** : aucun "TBD"/"TODO" laissé. Les quelques points
signalés "vérifier le patron exact dans le fichier voisin avant d'écrire"
(Tasks 5, 8, 9, 11, 12) sont des instructions de vérification concrètes
avec le fichier exact à lire, pas des trous — l'implémenteur dispose du
chemin exact et du patron à reproduire dans chaque cas, la recherche
préalable n'a simplement pas extrait l'intégralité du texte source (fichiers
de plusieurs centaines de lignes).

**3. Cohérence des types** : `bboxFromFeatureCollection` (Task 6) —
`[number, number, number, number] | null`, consommé identiquement par
Task 7 (`Item.bbox`, même forme) et Task 8 (calcul depuis `ctx.data.records`).
`MapViewHandle.fitBounds(bbox: [number, number, number, number], opts?)`
(Task 6) — même signature appelée par Task 7 et Task 8.
`resolvePipelineEditorPath(client, pk): Promise<string>` (Task 12) — même
signature aux deux call sites (`useOpenItem.ts`, `routes.tsx`).
`canCreatePipeline` (Task 4) — nom cohérent avec `canCreateApp`/
`canCreateMap`/`canCreateDataset` déjà en place dans le même fichier.
