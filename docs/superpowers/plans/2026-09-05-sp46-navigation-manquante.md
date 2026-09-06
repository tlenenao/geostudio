# SP-46 — Découvrabilité : navigation manquante : implementation plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre atteignables par un lien réel — et non plus seulement par
saisie manuelle d'URL — les quatre écrans identifiés par l'analyse de gaps
SP-42 (`/admin/collections`, `/admin/harvest`, `/reports`) et fermer le défaut
de confort qui affiche ces liens sans vérifier le privilège de la personne
qui les regarde (GAP-67).

**Architecture:** 4 tâches = les 4 gaps (GAP-30, GAP-39, GAP-67, GAP-32),
dans l'ordre qui introduit le moins de code non gardé transitoirement : les
deux nouveaux liens (GAP-30/GAP-39) sont ajoutés **déjà gardés** par
privilège dès leur introduction, puis GAP-67 retrofit la garde sur les trois
liens existants qui ne l'ont pas encore. GAP-32 est indépendant (fichier
différent) et vient en dernier. Une 5e tâche de clôture rejoue les suites
complètes.

**Tech Stack:** TypeScript/React + Vitest + Testing Library (shell) — aucun
changement côté cœur (`core/`) : les quatre routes/écrans ciblés existent et
sont gardés côté serveur, seule leur découvrabilité change.

**Document source :**
`docs/superpowers/specs/2026-09-05-sp46-navigation-manquante-design.md`
(§2 primitive de garde, §3 GAP-30/GAP-39, §4 GAP-32, §6 risques).

## Global Constraints

- **Aucun changement de comportement de garde côté serveur.** Les quatre
  routes ciblées gardent exactement le `RequirePrivilege`/l'absence de garde
  qu'elles ont déjà (`shell/src/shell/routes.tsx`) — ce plan ne touche qu'à
  ce qui est **montré**, jamais à ce qui est **autorisé**.
- **TDD / filet-avant-code** : chaque tâche pose ou modifie son test
  **avant** de toucher le composant.
- Commits **conventional**, un sujet par commit, français
  (`feat(shell): ...`, `test(shell): ...`).
- **Suite shell complète rejouée avant de clore chaque tâche** (piège
  CLAUDE.md n°6) : `cd shell && npm run test -- <fichiers concernés>` pendant
  la tâche, puis la suite complète en Tâche 5.
- **Tout filet de test modifié ou ajouté doit être vérifié par
  falsification** (piège CLAUDE.md n°10) : pour la Tâche 3 en particulier,
  confirmer qu'un test de masquage échoue bien si la garde est retirée, pas
  seulement qu'il passe une fois la garde posée.
- Pas de régénération OpenAPI/types TS : aucune route ni modèle de réponse
  du cœur ne change (piège CLAUDE.md n°1) — diff vide attendu et légitime si
  vérifié.
- **Hors périmètre** (spec §5) : lien retour symétrique
  Collections/Moissonnage → Extensions, hook `usePrivilege()` partagé,
  création de rapport sans signet préexistant, `ADMIN_DESTINATIONS`
  (`domainRoutes.ts`, déjà complet).

---

## Task 1 (GAP-30) : lien vers `/admin/collections` depuis `AdminExtensionsPage`, gardé par privilège dès l'ajout

Risque : bas — ajout pur, un nouveau lien conditionnel dans un fichier déjà
familier du patron (`Link` déjà importé).

**Files:**
- Modify: `shell/src/pages/AdminExtensionsPage.tsx`
- Test: `shell/src/pages/AdminExtensionsPage.test.tsx`

**Interfaces:**
- Consumes: `useMe()` (`shell/src/api/domains/identity.hooks.ts:6-9`, déjà
  exporté par `../api/hooks`), `Me.privileges: string[]`.
- Produces : rien de nouveau exposé hors du composant — introduit le
  tableau local `ADMIN_LINKS` (spec §2) qui sera réutilisé et complété par
  les Tâches 2 et 3.

- [ ] **Step 1 : écrire les deux tests (visible avec le privilège, absent
      sans) — avant de toucher le composant**

```tsx
// shell/src/pages/AdminExtensionsPage.test.tsx — ajouter
function mockMe(privileges: string[]) {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        role: { id: "role-1", name: "Administrateur", slug: "admin" },
        privileges,
      }),
    ),
  );
}

test("le volet Catalogue propose un lien vers /admin/collections quand le privilège est détenu", async () => {
  mockMe(["admin.collections.manage"]);
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  await screen.findByRole("table");
  expect(screen.getByRole("link", { name: "Collections →" })).toHaveAttribute(
    "href",
    "/admin/collections",
  );
});

test("masque le lien vers /admin/collections quand le privilège est absent", async () => {
  mockMe([]);
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  await screen.findByRole("table");
  expect(screen.queryByRole("link", { name: "Collections →" })).not.toBeInTheDocument();
});
```

Note : `mockMe` n'existe pas encore dans ce fichier de test — l'ajouter une
fois ici, la Tâche 2 et la Tâche 3 la réutilisent telle quelle (même patron
que `RequirePrivilege.test.tsx:10-23`).

- [ ] **Step 2 : lancer les deux tests, vérifier qu'ils échouent**

```bash
cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx -t "admin/collections"
```

Le premier échoue (lien absent, composant ne le rend pas encore) ; le second
passe déjà par hasard (le lien n'existe pas du tout) — attendu, il sera un
oracle utile seulement après le Step 3.

- [ ] **Step 3 : ajouter le lien, gardé par privilège, dans le composant**

```tsx
// shell/src/pages/AdminExtensionsPage.tsx
import { Link } from "react-router-dom";
import { useAllExtensions, useInstanceInfo, useMe, useSetExtensionEnabled } from "../api/hooks";
// ...

const ADMIN_LINKS: { to: string; label: string; privilege: string }[] = [
  { to: "/admin/infrastructure", label: "Outils d'infrastructure →", privilege: "settings.instance.manage" },
  { to: "/admin/roles", label: "Rôles et privilèges →", privilege: "admin.roles.manage" },
  { to: "/admin/users", label: "Utilisateurs →", privilege: "admin.users.manage" },
  { to: "/admin/collections", label: "Collections →", privilege: "admin.collections.manage" },
];

export function AdminExtensionsPage() {
  const extensionsQuery = useAllExtensions();
  const setEnabled = useSetExtensionEnabled();
  const instanceQuery = useInstanceInfo();
  const meQuery = useMe();
  const readOnly = instanceQuery.data?.readOnly === true;
  const visibleLinks = ADMIN_LINKS.filter((link) =>
    meQuery.data?.privileges.includes(link.privilege) === true,
  );
  // ...
```

Dans le JSX du volet `browse`, remplacer les trois `<Link>` en dur par :

```tsx
<Link to="/" className="text-accent hover:underline">
  ← Retour au catalogue
</Link>
{visibleLinks.map((link) => (
  <Link key={link.to} to={link.to} className="text-accent hover:underline">
    {link.label}
  </Link>
))}
```

Cette étape referme **déjà** GAP-67 pour ce lien précis (il n'existe jamais
sans garde) — les trois liens historiques (Infrastructure/Rôles/Utilisateurs)
restent en dur pour l'instant, la Tâche 3 les bascule dans `ADMIN_LINKS`.
Donc à ce stade, dupliquer temporairement l'entrée `admin.collections.manage`
dans `ADMIN_LINKS` ET garder les trois autres en `<Link>` en dur est
transitoire et assumé — cf. Step 3 de la Tâche 3 qui supprime la duplication.

- [ ] **Step 4 : lancer les deux tests du Step 1, vérifier qu'ils passent —
      puis la suite complète du fichier**

```bash
cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx
```

Vérifier qu'aucun des tests existants (Step 138-156 de la spec §1, liens
Rôles/Utilisateurs) ne casse — ils ne mockent pas encore `/me` avec les
privilèges requis, donc ils doivent encore passer tels quels tant que ces
deux liens restent en dur (non gardés) jusqu'à la Tâche 3.

- [ ] **Step 5 : commit**

```bash
git add shell/src/pages/AdminExtensionsPage.tsx shell/src/pages/AdminExtensionsPage.test.tsx
git commit -m "feat(shell): ajoute un lien vers /admin/collections depuis AdminExtensionsPage"
```

---

## Task 2 (GAP-39) : lien vers `/admin/harvest` depuis `AdminExtensionsPage`, même patron

Risque : bas — même fichier, même patron que la Tâche 1, aucune nouvelle
décision de conception.

**Files:**
- Modify: `shell/src/pages/AdminExtensionsPage.tsx`
- Test: `shell/src/pages/AdminExtensionsPage.test.tsx`

- [ ] **Step 1 : écrire les deux tests (visible / masqué), sur le modèle de
      la Tâche 1**

```tsx
test("le volet Catalogue propose un lien vers /admin/harvest quand le privilège est détenu", async () => {
  mockMe(["admin.harvest.manage"]);
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  await screen.findByRole("table");
  expect(screen.getByRole("link", { name: "Moissonnage →" })).toHaveAttribute(
    "href",
    "/admin/harvest",
  );
});

test("masque le lien vers /admin/harvest quand le privilège est absent", async () => {
  mockMe([]);
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  await screen.findByRole("table");
  expect(screen.queryByRole("link", { name: "Moissonnage →" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2 : lancer, vérifier l'échec du premier**

```bash
cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx -t "admin/harvest"
```

- [ ] **Step 3 : ajouter l'entrée à `ADMIN_LINKS`**

```tsx
// shell/src/pages/AdminExtensionsPage.tsx — ADMIN_LINKS, ajouter
{ to: "/admin/harvest", label: "Moissonnage →", privilege: "admin.harvest.manage" },
```

- [ ] **Step 4 : lancer les deux tests, vérifier qu'ils passent, puis la
      suite complète du fichier**

```bash
cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx
```

- [ ] **Step 5 : commit**

```bash
git add shell/src/pages/AdminExtensionsPage.tsx shell/src/pages/AdminExtensionsPage.test.tsx
git commit -m "feat(shell): ajoute un lien vers /admin/harvest depuis AdminExtensionsPage"
```

---

## Task 3 (GAP-67) : garder par privilège les trois liens historiques

Risque : moyen — seule tâche qui **retire** un comportement observable
existant (les liens `/admin/infrastructure`/`/admin/roles`/`/admin/users`
s'affichaient inconditionnellement) ; deux tests existants doivent être
réécrits, pas seulement complétés.

**Files:**
- Modify: `shell/src/pages/AdminExtensionsPage.tsx`
- Test: `shell/src/pages/AdminExtensionsPage.test.tsx`

**Interfaces:**
- Consumes: rien de nouveau — complète `ADMIN_LINKS` introduit Tâche 1.

- [ ] **Step 1 : falsifier d'abord le défaut, pour vérifier qu'un test le
      détecte** — lancer la suite existante telle quelle et confirmer que
      les deux tests ci-dessous passent aujourd'hui **sans** mocker `/me`
      avec les privilèges requis (donc avec le handler par défaut, qui ne
      les contient pas) :

```bash
cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx \
  -t "propose un lien vers /admin/roles"
cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx \
  -t "propose un lien vers /admin/users"
```

Confirmer qu'ils passent (c'est la preuve du bug GAP-67 : le lien s'affiche
sans le privilège) — noter ce résultat avant de continuer, il justifie la
réécriture du Step 2.

- [ ] **Step 2 : réécrire les deux tests existants pour mocker un
      utilisateur privilégié (ils testent désormais le cas nominal), et
      ajouter les trois tests de masquage manquants — avant de toucher au
      composant**

```tsx
// Remplacer les deux tests existants (lignes ~138-156) :
test("le volet Catalogue propose un lien vers /admin/roles quand le privilège est détenu", async () => {
  mockMe(["admin.roles.manage"]);
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  await screen.findByRole("table");
  expect(screen.getByRole("link", { name: "Rôles et privilèges →" })).toHaveAttribute(
    "href",
    "/admin/roles",
  );
});

test("le volet Catalogue propose un lien vers /admin/users quand le privilège est détenu", async () => {
  mockMe(["admin.users.manage"]);
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  await screen.findByRole("table");
  expect(screen.getByRole("link", { name: "Utilisateurs →" })).toHaveAttribute(
    "href",
    "/admin/users",
  );
});

// Ajouter — les trois nouveaux tests de masquage :
test("masque le lien vers /admin/infrastructure quand le privilège est absent", async () => {
  mockMe([]);
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  await screen.findByRole("table");
  expect(screen.queryByRole("link", { name: "Outils d'infrastructure →" })).not.toBeInTheDocument();
});

test("masque le lien vers /admin/roles quand le privilège est absent", async () => {
  mockMe([]);
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  await screen.findByRole("table");
  expect(screen.queryByRole("link", { name: "Rôles et privilèges →" })).not.toBeInTheDocument();
});

test("masque le lien vers /admin/users quand le privilège est absent", async () => {
  mockMe([]);
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  await screen.findByRole("table");
  expect(screen.queryByRole("link", { name: "Utilisateurs →" })).not.toBeInTheDocument();
});

test("un profil qui détient plusieurs privilèges admin voit tous les liens correspondants", async () => {
  mockMe([
    "admin.roles.manage",
    "admin.users.manage",
    "admin.collections.manage",
    "admin.harvest.manage",
    "settings.instance.manage",
  ]);
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  await screen.findByRole("table");
  expect(screen.getByRole("link", { name: "Outils d'infrastructure →" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Rôles et privilèges →" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Utilisateurs →" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Collections →" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Moissonnage →" })).toBeInTheDocument();
});
```

- [ ] **Step 3 : lancer la suite, vérifier que les tests de masquage
      échouent (les trois liens historiques sont encore en dur) et que les
      deux tests réécrits passent déjà (le mock leur donne le privilège que
      le lien en dur affiche de toute façon)**

```bash
cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx
```

- [ ] **Step 4 : basculer les trois liens historiques dans `ADMIN_LINKS`,
      retirer les `<Link>` en dur devenus redondants**

```tsx
// shell/src/pages/AdminExtensionsPage.tsx
// ADMIN_LINKS porte déjà les 5 entrées depuis les Tâches 1/2 — vérifier
// qu'aucune n'est dupliquée, puis dans le JSX du volet browse :
<Link to="/" className="text-accent hover:underline">
  ← Retour au catalogue
</Link>
{visibleLinks.map((link) => (
  <Link key={link.to} to={link.to} className="text-accent hover:underline">
    {link.label}
  </Link>
))}
// (aucun autre <Link> en dur dans ce volet)
```

- [ ] **Step 5 : lancer la suite complète du fichier, vérifier que tous les
      tests passent — y compris les cinq de masquage/regroupement**

```bash
cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx
```

- [ ] **Step 6 : suite shell complète (ce fichier touche une page visitée
      par plusieurs tests d'intégration croisés — DomainBar/routes.test.tsx
      pourraient réagir à `useMe` appelé une fois de plus)**

```bash
cd shell && npm run test
```

- [ ] **Step 7 : commit**

```bash
git add shell/src/pages/AdminExtensionsPage.tsx shell/src/pages/AdminExtensionsPage.test.tsx
git commit -m "fix(shell): masque les liens d'administration sans le privilège requis (GAP-67)"
```

---

## Task 4 (GAP-32) : lien vers `/reports` depuis l'atterrissage du domaine Automatisation

Risque : bas — fichier différent des trois tâches précédentes, changement
additif borné par une condition déjà dérivée d'un état existant (`type`).

**Files:**
- Modify: `shell/src/pages/CatalogPage.tsx`
- Test: `shell/src/pages/CatalogPage.test.tsx`

**Interfaces:**
- Consumes: `type`/`fixedType` déjà calculés en tête du composant
  (`CatalogPage.tsx:34-42`).
- Produces: rien de nouveau exposé — un `<Link>` conditionnel local.

- [ ] **Step 1 : écrire les tests (présent sur l'atterrissage Automatisation,
      absent partout ailleurs) — avant de toucher le composant**

```tsx
// shell/src/pages/CatalogPage.test.tsx — ajouter
test("propose un lien vers /reports quand le type de la barre de domaines est pipeline (atterrissage Automatisation)", async () => {
  render(
    <MemoryRouter initialEntries={["/?type=pipeline"]}>
      <Harness />
    </MemoryRouter>,
  );
  expect(await screen.findByRole("link", { name: "Rapports planifiés →" })).toHaveAttribute(
    "href",
    "/reports",
  );
});

test("masque le lien vers /reports hors de l'atterrissage Automatisation (catalogue général)", async () => {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <Harness />
    </MemoryRouter>,
  );
  // Attendre un rendu stable (le sélecteur Type, toujours présent hors
  // fixedType) avant l'assertion négative, plutôt qu'un sleep arbitraire.
  await screen.findByRole("combobox", { name: "Type" });
  expect(screen.queryByRole("link", { name: "Rapports planifiés →" })).not.toBeInTheDocument();
});

test("masque le lien vers /reports sur une vue à fixedType fixé (ex. /reports lui-même)", async () => {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <CatalogPageHarnessWithFixedType fixedType="report" />
    </MemoryRouter>,
  );
  expect(screen.queryByRole("link", { name: "Rapports planifiés →" })).not.toBeInTheDocument();
});
```

Adapter aux harnais réels déjà présents dans `CatalogPage.test.tsx` (le
fichier a déjà un rendu paramétré par `fixedType`, cf.
`fixedType locks the type filter and hides the selector`, ligne 123 — suivre
exactement son patron de rendu plutôt que ce pseudo-code, notamment pour la
troisième assertion qui doit réutiliser le même harnais que ce test existant
plutôt qu'un composant `CatalogPageHarnessWithFixedType` inventé ici).

- [ ] **Step 2 : lancer les trois tests, vérifier que le premier échoue (lien
      absent) et que les deux autres passent déjà par absence totale du
      lien**

```bash
cd shell && npx vitest run src/pages/CatalogPage.test.tsx -t "reports"
```

- [ ] **Step 3 : ajouter le lien conditionnel**

```tsx
// shell/src/pages/CatalogPage.tsx
import { Link } from "react-router-dom";
// ...
// dans le volet browse, juste après le </label> du sélecteur Type (avant le
// sélecteur Portée) :
{type === "pipeline" && !fixedType && (
  <Link to="/reports" className="text-accent hover:underline">
    Rapports planifiés →
  </Link>
)}
```

- [ ] **Step 4 : lancer les trois tests, vérifier qu'ils passent, puis la
      suite complète du fichier**

```bash
cd shell && npx vitest run src/pages/CatalogPage.test.tsx
```

- [ ] **Step 5 : suite shell complète**

```bash
cd shell && npm run test
```

- [ ] **Step 6 : commit**

```bash
git add shell/src/pages/CatalogPage.tsx shell/src/pages/CatalogPage.test.tsx
git commit -m "feat(shell): ajoute un lien vers /reports depuis l'atterrissage du domaine Automatisation"
```

---

## Task 5 : clôture

- [ ] **Suite complète shell** (aucun changement côté cœur dans ce plan) :

```bash
cd shell && npm run lint && npm run format:check \
  && npm run test && npm run build \
  && node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```

Nettoyer `dist/`/`dist-export/` avant la mesure de couverture (piège
CLAUDE.md documenté 4 fois).

- [ ] **E2E ciblée** — confirmer qu'aucune régression sur les parcours qui
      naviguent aujourd'hui par URL directe vers les quatre écrans concernés :

```bash
cd shell && npx playwright test admin-collections harvest-stac harvest-csw \
  harvest-wms harvest-ogc-records harvest-ckan harvest-arcgis report-schedule
```

- [ ] **`uvx pre-commit run --all-files`** (5 hooks — commitlint ne sort
      qu'au commit, déjà respecté par les messages ci-dessus).
- [ ] **Mettre à jour `CLAUDE.md`** (`### Livré`) avec une ligne SP-46 :
  liens ajoutés vers `/admin/collections` et `/admin/harvest` depuis
  `AdminExtensionsPage`, lien vers `/reports` depuis l'atterrissage du
  domaine Automatisation, et les cinq liens de `AdminExtensionsPage`
  désormais masqués sans le privilège requis (GAP-67 clos) — puis retirer
  GAP-30/GAP-32/GAP-39/GAP-67 de la liste des suivis non bloquants s'ils y
  sont cités nommément (vérifier `docs/revue/2026-09-04-backlog.md` avant
  d'affirmer qu'ils le sont).
- [ ] **Vérifier qu'aucune régénération OpenAPI/TS n'est nécessaire** — diff
  vide attendu (aucune route ni modèle de réponse du cœur n'a changé) :

```bash
cd core && git diff --stat -- openapi.json
cd ../shell && git diff --stat -- src/api/generated/core-schema.d.ts
```
