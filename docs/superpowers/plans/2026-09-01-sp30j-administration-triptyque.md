# SP-30j — Administration (Extensions/Collections/Moissonnage) sur le socle triptyque Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Basculer les trois pages d'administration existantes
(`AdminExtensionsPage`, `CollectionsAdminPage`, `HarvestSourcesAdminPage` —
famille 8 « Administration »,
`docs/superpowers/specs/2026-08-30-sp30-bascule-triptyque-design.md` §6.1,
dernière famille de pages de SP-30) sur `TriptychLayout`, en réutilisant
`RequireRole` (déjà livré par SP-30i, famille 7) comme garde de rôle au
niveau route au lieu des six comparaisons `meQuery.data?.isAdmin` en dur que
ces trois pages répètent aujourd'hui. Les cinq boîtes de dialogue propres à
ces pages (`EditCollectionDialog`, `CollectionShareDialog`,
`RegisterCollectionDialog`, `CreateHarvestSourceDialog`,
`EditHarvestSourceDialog`) deviennent du contenu de volet — l'onglet
« Détail » de chaque page — conformément à la spec §2.2 (« convertis en
parcours plein écran ou en contenu de volet »). `ConfirmDialog` seul reste
une vraie boîte de dialogue modale (migré vers `ui/kit/ConfirmDialog`), pour
la confirmation de suppression sur les deux pages qui en ont une.

**Ce que ce plan NE fait PAS** :
- **Aucune nouvelle capacité d'administration.** La maquette
  (`docs/design/triptyque-geostudio.html:836-895`, bloc `<!-- ADMIN / AUDIT
  -->`) montre un domaine Administration unifié à sept sections
  (Utilisateurs, Groupes, Collections, Moissonnage, Extensions, Journal
  d'audit, Secrets) dans un unique gabarit triptyque avec arborescence de
  sections en volet Catalogue. C'est la cible **long terme** du domaine — la
  spec SP-30 l'exclut explicitement (« Toute nouvelle capacité (…) :
  SP-31/32/33 », §2.2, hors périmètre) y compris pour les trois sections qui
  existent déjà : ce plan bascule les trois pages **telles qu'elles sont**
  sur le gabarit, il ne construit ni l'arborescence de sections, ni
  Utilisateurs/Groupes/Journal d'audit/Secrets.
- **Aucune navigation inter-pages nouvelle entre les trois pages
  d'administration.** `shell/src/shell/chrome/domainRoutes.ts` ne pointe le
  domaine « Administration » de la barre de domaines que vers
  `/admin/extensions` (`DOMAIN_PATHS.admin`) — un seul lien pour tout le
  domaine, déjà le cas avant ce plan (SP-30a). L'ancien chrome (5 liens
  texte, retiré par SP-30a/Task 12) avait trois liens distincts
  (`/admin/extensions`, `/admin/collections`, `/admin/harvest`) ; la barre de
  domaines ne les a pas remplacés — seule une arborescence de sections
  (hors périmètre ci-dessus) le referait proprement. Les deux pages non
  reliées à la barre de domaines restent donc atteignables par URL directe
  uniquement (navigation directe, favori) — état déjà vrai avant ce plan
  (confirmé par les commentaires de `e2e/admin-collections.spec.ts:140-144`
  et `e2e/admin-extensions.spec.ts:54-57`, écrits par SP-30a lui-même), pas
  une régression introduite ici. L'onglet « Catalogue » de chacune des trois
  pages reste donc un simple lien de retour (« ← Retour au catalogue »),
  même patron que `SqlLabPage` (SP-30i) — pas une liste de sections
  inventée.
- **Aucun changement au cœur (`core/`).** Ni schéma, ni endpoint. Diff vide
  attendu sur `core/` (vérifié en Task 5). `CollectionPermissions` (spec §4)
  est déjà livrée par SP-30a — vérifié par lecture directe de
  `shell/src/api/types.ts:544-557` avant d'écrire ce plan (piège n°3) :
  `CollectionAdmin.permissions: ItemPermissions` existe déjà, `canWrite` a
  déjà disparu du type. Aucune régénération OpenAPI/TS nécessaire.
- **`/internal/kit-gallery` (`KitGalleryPage.tsx:203`) n'est pas touchée.**
  Cette page porte elle aussi une comparaison `meQuery.data?.isAdmin !==
  true` en dur, mais ce n'est ni une des « pages basculées » listées par la
  spec (§2.1) ni un domaine de la barre (c'est un outil de référence interne
  pour SP-30, ajouté par SP-29b, routé sur `/internal/kit-gallery` —
  `shell/src/shell/routes.tsx:278` — jamais lié depuis aucune navigation
  produit). Hors périmètre de la famille 8, laissée telle quelle.

**Décisions explicites de ce plan (à ne pas re-débattre en exécution) :**

1. **`RequireRole` est réutilisé sans modification** (`shell/src/auth/
   RequireRole.tsx`, livré par SP-30i/Task 1) — `role="admin"`,
   `deniedMessage="Accès réservé aux administrateurs."` sur les trois
   routes. Aucun nouveau composant de garde dans ce plan.
2. **L'onglet inspect s'appelle « Détail »** sur les trois pages — son
   contenu varie (rien / formulaire de création / formulaire d'édition /
   formulaire de partage) selon l'action en cours, il n'y a donc pas de nom
   unique décrivant un seul type de contenu fixe (à la différence de
   « Historique » sur `SqlLabPage`, SP-30i, qui n'affiche toujours qu'une
   liste). Quand rien n'est sélectionné, l'onglet est vide — **aucun message
   de repli inventé** (même règle que `PipelineNodeInspector` sur
   `PipelineBuilderPage`, SP-30f : `content: null` est un `ReactNode`
   valide).
3. **Les cinq boîtes de dialogue deviennent des composants `*Panel.tsx`
   renommés** (pas des composants inline dans la page) : `EditCollectionDialog.tsx`
   → `EditCollectionPanel.tsx`, `CollectionShareDialog.tsx` →
   `CollectionSharePanel.tsx`, `RegisterCollectionDialog.tsx` →
   `RegisterCollectionPanel.tsx`, `CreateHarvestSourceDialog.tsx` →
   `CreateHarvestSourcePanel.tsx`, `EditHarvestSourceDialog.tsx` →
   `EditHarvestSourcePanel.tsx` — même répertoire (`shell/src/shell/`), même
   test-par-composant (sauf `EditHarvestSourceDialog`, qui n'avait pas de
   fichier de test dédié ; son comportement est couvert par un nouveau test
   dans `HarvestSourcesAdminPage.test.tsx`, Task 3). Un fichier appelé
   `XDialog.tsx` qui ne rend plus de `<Dialog>` serait trompeur — cohérent
   avec le renommage `ExportPanel`/`Terrain3DUploadButton` de SP-30c (déjà
   nommés `Panel`, pas de renommage à l'époque, mais même principe).
4. **La prop `open: boolean` disparaît des cinq composants renommés.** Le
   parent les monte déjà conditionnellement
   (`{editing && <EditCollectionDialog collection={editing} open={true}
   onClose={...} />}` — `open` valait toujours `true` quand le composant
   était monté) : la prop était redondante avec le montage conditionnel
   lui-même. Sa suppression simplifie aussi la logique de synchronisation —
   voir décision 5.
5. **Les `useEffect` de resynchronisation d'état interne disparaissent** sur
   `EditCollectionPanel`/`EditHarvestSourcePanel` (`EditCollectionDialog.tsx:26-34`,
   `EditHarvestSourceDialog.tsx:24-30` dans leur forme actuelle) : ils
   existaient pour reseeder `title`/`description`/... quand `source`/
   `collection` changeait **alors que le composant restait monté** (le
   `Dialog` restait affiché, seul son contenu changeait de ligne). Le
   nouveau patron d'inspecteur sélectionné (même principe que
   `PipelineNodeInspector` sur `PipelineBuilderPage`, SP-30f) **démonte et
   remonte** le panneau à chaque changement de ligne via `key={editing.id}`
   posée par le parent (Tasks 3/4) — `useState(collection.title)` /
   `useState(source.url)` suffit alors, aucun `useEffect` nécessaire.
   `CollectionSharePanel` **garde** son `useEffect`, lui, parce qu'il
   reseede depuis une réponse serveur asynchrone (`sharingQuery.data`), pas
   depuis une prop synchrone — `key={sharing.id}` posée par le parent
   garantit seulement qu'un changement de collection partagée remonte le
   composant (requête refaite), pas que la resynchronisation devienne
   inutile.
6. **Exclusivité mutuelle entre `registering`/`editing`/`sharing`
   (`CollectionsAdminPage`) et `creating`/`editing` (`HarvestSourcesAdminPage`)
   posée explicitement par ce plan — pas dans le code actuel.** Dans
   l'ancien code, rien n'empêchait `editing` et `sharing` d'être tous deux
   non nuls en même temps (cliquer Éditer puis Partager sans fermer) ; ça ne
   se voyait jamais parce que le `<Dialog>` de Radix, modal, bloquait
   l'interaction avec la ligne du tableau tant qu'il restait ouvert — un
   second clic sur une action de ligne était impossible pendant qu'un
   premier dialogue était affiché. Le nouveau panneau en ligne dans l'onglet
   Détail **n'a plus cette barrière** (le tableau, en onglet Travail, reste
   pleinement interactif pendant que Détail affiche un formulaire) : sans
   correction, cliquer Éditer puis Partager sur deux lignes différentes
   empilerait désormais deux formulaires dans le même onglet. Chaque
   gestionnaire de clic remet donc explicitement les deux autres états à
   `null`/`false` avant de poser le sien (Tasks 3/4) — une vraie correction
   de comportement rendue nécessaire par la suppression du modal, pas une
   fonctionnalité nouvelle. `deleting` n'a pas besoin de cette même remise à
   zéro : `ConfirmDialog` reste un vrai modal Radix, qui bloque déjà
   l'interaction avec le reste de la page tant qu'il est ouvert.
7. **Aucune bascule automatique de l'onglet actif** (viewport étroit) vers
   « Détail » quand une action de ligne est déclenchée. `TriptychLayout` ne
   permet pas de contrôler `activeId` depuis l'extérieur (état interne du
   composant, spec chrome de SP-30a) et aucune page de la famille 3 à 7 ne
   le fait — cohérent, pas une régression propre à cette famille. Sur
   viewport large, les trois volets sont visibles simultanément (pas de
   souci) ; sur viewport étroit, l'utilisateur doit naviguer manuellement
   vers l'onglet Détail après avoir cliqué Éditer/Partager/Ajouter — même
   limitation déjà acceptée ailleurs.
8. **Ordre des tâches : câblage du garde d'abord (Task 1), pages ensuite
   (Tasks 2-4), vérification finale (Task 5)** — même séquencement que
   SP-30i : à aucun moment entre les commits de ce plan une route
   d'administration ne se retrouve sans garde d'accès (la vérification
   interne de chaque page reste du code mort inatteignable entre son propre
   Task et Task 1, jamais supprimée avant que `RequireRole` ne bloque déjà
   le rendu).

**Architecture:** `shell/src/shell/routes.tsx` enveloppe les trois routes
`/admin/extensions`, `/admin/collections`, `/admin/harvest` dans
`<RequireRole role="admin" deniedMessage="Accès réservé aux
administrateurs.">`. Chaque page s'enveloppe dans `<div className="-m-6
flex flex-1 flex-col overflow-hidden">` (même technique que les six familles
précédentes) et instancie `TriptychLayout` : **browse** = « Catalogue »
(`Panel` avec lien retour seul, comme `SqlLabPage`) ; **work** = le tableau
existant + bouton d'ajout, dans un conteneur `overflow-y-auto` propre (le
volet `work` de `TriptychLayout` est `overflow-hidden` par construction,
piège documenté par SP-30d/e/f/g/h) ; **inspect** = « Détail » — le
formulaire de création/édition/partage actif, ou `null`. Les cinq anciennes
boîtes de dialogue deviennent des composants `*Panel.tsx` sans prop `open`,
consommant `Button`/`Input` du kit (`shell/src/ui/kit/`), rendus dans une
`<section aria-label="…">` (pas de `Dialog`). `ConfirmDialog` (suppression)
reste `ui/kit/ConfirmDialog`, migré depuis `ui/ConfirmDialog`.

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
- Aucun ancien import `ui/button`, `ui/input`, `ui/dialog`, `ui/ConfirmDialog`
  ne subsiste dans les fichiers de ce plan après leur tâche respective —
  remplacés par leurs équivalents `ui/kit/*`.
- `-m-6` est une technique de transition **locale à chacune des trois pages**
  dans ce plan, jamais un changement à `AppLayout.tsx`.
- Régression jsdom (piège n°10) : `window.matchMedia` n'existe pas sous
  jsdom — `TriptychLayout` l'appelle via `useNarrowViewport`. Stub local à
  chaque fichier de test touché, **avec** `afterEach(() =>
  vi.unstubAllGlobals())` dès son introduction — jamais dans
  `shell/src/test/setup.ts`.
- Pas de changement au cœur (`core/`) dans ce plan. Diff vide attendu
  (vérifié en Task 5 par `git status --short core/`). Régénération
  OpenAPI/TS **non nécessaire**.
- Après ce plan, les six occurrences `meQuery.data?.isAdmin` des trois pages
  d'administration ont disparu ; il ne reste que `AccountMenu.tsx` (2, lit
  `me.isAdmin`/`me.isAnalyst` déjà résolus pour l'affichage du badge, ne
  compare rien — hors doctrine), `AppLayout.tsx` (2, construit `Profile`
  pour `capabilities.ts`, hors périmètre par doctrine SP-29a/SP-30i) et
  `KitGalleryPage.tsx` (1, outil interne, hors périmètre — voir « Ce que ce
  plan NE fait PAS »). `RequireRole.tsx` lui-même fait la comparaison une
  seule fois, exclu du grep de vérification comme dans SP-30i.
- Suite E2E **complète** exigée avant tout commit qui change la structure
  DOM d'une page (Tasks 2-4) — pas de liste de specs nommée dans ce plan
  pour cette raison-là (recommandation actée par SP-30e/f/g/h/i après
  plusieurs occurrences du piège n°6). **Exception documentée** : les
  fichiers E2E qui scopent explicitement sur `getByRole("dialog", { name:
  "Ajouter une source" })` ou `getByRole("dialog", { name: "Enregistrer une
  table" })` sont connus par avance (grep fait avant l'écriture de ce plan)
  et **doivent** être mis à jour dans la même tâche que la conversion du
  dialogue correspondant (Task 3 pour les six occurrences harvest, Task 4
  pour l'occurrence collections) — sans quoi la suite E2E complète exigée en
  fin de tâche échouerait à coup sûr, pas une simple précaution.

---

## Task 1: Shell — câbler `RequireRole` sur les trois routes d'administration

**Files:**
- Modify: `shell/src/shell/routes.tsx`

**Interfaces:**
- Consumes: `RequireRole` (`shell/src/auth/RequireRole.tsx`, déjà livré par
  SP-30i, déjà importé en tête de `routes.tsx`).
- Produces: aucune API changée — les trois routes rendent désormais
  `<RequireRole role="admin" deniedMessage="…"><XxxPage /></RequireRole>` au
  lieu de `<XxxPage />` seule.

- [ ] **Step 1: Baseline E2E**

```bash
cd shell && npx playwright test e2e/admin-extensions.spec.ts e2e/admin-collections.spec.ts \
  e2e/harvest-wms.spec.ts e2e/harvest-stac.spec.ts e2e/harvest-csw.spec.ts \
  e2e/harvest-ckan.spec.ts e2e/harvest-ogc-records.spec.ts e2e/harvest-arcgis.spec.ts
```

Expected: PASS (tous) — avant toute modification.

- [ ] **Step 2: Envelopper les trois routes**

Dans `shell/src/shell/routes.tsx`, remplacer :

```tsx
        <Route path="/admin/extensions" element={<AdminExtensionsPage />} />
        <Route path="/admin/collections" element={<CollectionsAdminPage />} />
        <Route path="/admin/harvest" element={<HarvestSourcesAdminPage />} />
```

par :

```tsx
        <Route
          path="/admin/extensions"
          element={
            <RequireRole role="admin" deniedMessage="Accès réservé aux administrateurs.">
              <AdminExtensionsPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin/collections"
          element={
            <RequireRole role="admin" deniedMessage="Accès réservé aux administrateurs.">
              <CollectionsAdminPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin/harvest"
          element={
            <RequireRole role="admin" deniedMessage="Accès réservé aux administrateurs.">
              <HarvestSourcesAdminPage />
            </RequireRole>
          }
        />
```

Note : chacune des trois pages contient encore, à ce stade, sa propre
vérification interne (`meQuery.data?.isAdmin !== true`) — elle devient du
code mort inatteignable (`RequireRole` bloque déjà le rendu de la page avant
qu'elle ne s'exécute pour un non-admin), retirée explicitement dans la tâche
de chaque page (Tasks 2-4). Aucune fenêtre de régression : les routes
restent gardées à tout moment.

- [ ] **Step 3: Relancer l'E2E, vérifier le succès**

```bash
cd shell && npx playwright test e2e/admin-extensions.spec.ts e2e/admin-collections.spec.ts \
  e2e/harvest-wms.spec.ts e2e/harvest-stac.spec.ts e2e/harvest-csw.spec.ts \
  e2e/harvest-ckan.spec.ts e2e/harvest-ogc-records.spec.ts e2e/harvest-arcgis.spec.ts
```

Expected: PASS (tous), y compris les tests « accès refusé » des deux specs
admin — désormais servis par `RequireRole`, pas par la page.

- [ ] **Step 4: Commit**

```bash
cd shell && git add src/shell/routes.tsx
git commit -m "feat(shell): routes /admin/* — câblent requireRole(admin)"
```

---

## Task 2: Shell — `AdminExtensionsPage` sur `TriptychLayout` (Catalogue/Extensions/Détail)

**Files:**
- Modify: `shell/src/pages/AdminExtensionsPage.tsx`
- Modify: `shell/src/pages/AdminExtensionsPage.test.tsx`

**Interfaces:**
- Consumes: `TriptychLayout` (`shell/src/shell/chrome/TriptychLayout.tsx`,
  props `browse`/`work`/`inspect`, chacun `{id, label, content}`) ;
  `Button`/`Panel` du kit (`shell/src/ui/kit/`) ; `useAllExtensions`/
  `useInstanceInfo`/`useSetExtensionEnabled` (`shell/src/api/hooks.ts`,
  inchangés, seul l'appel à `useAllExtensions` perd son option `{enabled:
  meQuery.data?.isAdmin === true}` — `RequireRole` garantit déjà `isAdmin`
  avant que la page ne rende).
- Produces: `AdminExtensionsPage()` — aucune prop (inchangé) ; consommée par
  `shell/routes.tsx` via `RequireRole` (Task 1).

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx
```

Expected: PASS (4 tests, état actuel avant modification).

- [ ] **Step 2: Réécrire `AdminExtensionsPage.tsx`**

Remplacer tout le contenu du fichier par :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { Link } from "react-router-dom";
import { useAllExtensions, useInstanceInfo, useSetExtensionEnabled } from "../api/hooks";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

export function AdminExtensionsPage() {
  const extensionsQuery = useAllExtensions();
  const setEnabled = useSetExtensionEnabled();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
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
          id: "extensions",
          label: "Extensions",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">Extensions</h1>
              {extensionsQuery.isLoading && <p role="status">Chargement…</p>}
              {extensionsQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec du chargement des extensions.
                </p>
              )}
              {setEnabled.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec de la mise à jour de l'extension.
                </p>
              )}
              {extensionsQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">Étiquette</th>
                      <th className="py-2 text-ink">Balise</th>
                      <th className="py-2 text-ink">Module</th>
                      <th className="py-2 text-ink">Actif</th>
                    </tr>
                  </thead>
                  <tbody>
                    {extensionsQuery.data.map((ext) => (
                      <tr key={ext.type} className="border-b border-rule-2">
                        <td className="py-2 text-ink">{ext.label}</td>
                        <td className="py-2 text-ink">{ext.tag}</td>
                        <td className="py-2 text-xs text-ink-2">{ext.moduleUrl}</td>
                        <td className="py-2">
                          <input
                            type="checkbox"
                            aria-label={`Actif : ${ext.label}`}
                            checked={ext.enabled}
                            disabled={setEnabled.isPending || readOnly}
                            onChange={(e) =>
                              setEnabled.mutate({ id: ext.type, enabled: e.target.checked })
                            }
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ),
        }}
        inspect={{ id: "detail", label: "Détail", content: null }}
      />
    </div>
  );
}
```

- [ ] **Step 3: Réécrire `AdminExtensionsPage.test.tsx`**

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
import { AdminExtensionsPage } from "./AdminExtensionsPage";

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. Stub local, avec vi.unstubAllGlobals()
// en afterEach dès son introduction (même patron que SqlLabPage.test.tsx,
// SP-30i).
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

beforeEach(() => stubMatchMedia(false));
afterEach(() => vi.unstubAllGlobals());

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <AdminExtensionsPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("lists extensions (including disabled) and toggles enabled via PATCH", async () => {
  let patchedBody: unknown;
  server.use(
    http.get("https://core.test/extensions", ({ request }) => {
      expect(new URL(request.url).searchParams.get("all")).toBe("true");
      return HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge",
            tag: "gauge-extension-widget",
            label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [],
            events: [],
            actions: [],
            defaultSize: { w: 2, h: 2 },
            permissions: { collections: "all" },
            enabled: false,
          },
        ],
      });
    }),
    http.patch("https://core.test/extensions/acme.gauge", async ({ request }) => {
      patchedBody = await request.json();
      return HttpResponse.json({ id: "acme.gauge", enabled: true });
    }),
  );
  render(<Harness />);
  const toggle = await screen.findByRole("checkbox", { name: "Actif : Jauge (extension)" });
  expect(toggle).not.toBeChecked();
  await userEvent.click(toggle);
  await waitFor(() => expect(patchedBody).toEqual({ enabled: true }));
});

test("surfaces an alert when the PATCH to toggle an extension fails", async () => {
  server.use(
    http.get("https://core.test/extensions", () =>
      HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge",
            tag: "gauge-extension-widget",
            label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [],
            events: [],
            actions: [],
            defaultSize: { w: 2, h: 2 },
            permissions: { collections: "all" },
            enabled: false,
          },
        ],
      }),
    ),
    http.patch("https://core.test/extensions/acme.gauge", () =>
      HttpResponse.json({}, { status: 500 }),
    ),
  );
  render(<Harness />);
  const toggle = await screen.findByRole("checkbox", { name: "Actif : Jauge (extension)" });
  await userEvent.click(toggle);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Échec de la mise à jour de l'extension."),
  );
});

test("disables the enabled toggle when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/extensions", () =>
      HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge",
            tag: "gauge-extension-widget",
            label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [],
            events: [],
            actions: [],
            defaultSize: { w: 2, h: 2 },
            permissions: { collections: "all" },
            enabled: false,
          },
        ],
      }),
    ),
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  const toggle = await screen.findByRole("checkbox", { name: "Actif : Jauge (extension)" });
  expect(toggle).toBeDisabled();
});

test("sous viewport étroit, affiche trois onglets Catalogue/Extensions/Détail avec Extensions actif par défaut", async () => {
  stubMatchMedia(true);
  server.use(
    http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })),
  );
  render(<Harness />);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Extensions", "Détail"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Extensions");
});
```

Note : le test « shows an access-denied message and never calls /extensions
when the user is not admin » de l'ancien fichier disparaît — ce comportement
est désormais couvert par `RequireRole.test.tsx` (SP-30i), qui teste le
garde indépendamment de la page. `AdminExtensionsPage` elle-même ne connaît
plus `useMe()` ni le rôle de l'utilisateur.

- [ ] **Step 4: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx
```

Expected: PASS — 4 tests.

- [ ] **Step 5: Vérifier l'absence de couleur Tailwind en dur**

```bash
grep -nE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/pages/AdminExtensionsPage.tsx
```

Expected: aucune sortie.

- [ ] **Step 6: Vérifier l'absence de toute comparaison de droits résiduelle**

```bash
grep -n 'isAdmin\|isAnalyst\|useMe' shell/src/pages/AdminExtensionsPage.tsx
```

Expected: aucune sortie.

- [ ] **Step 7: Suite E2E complète (piège n°6)**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed, ou mieux.

- [ ] **Step 8: Commit**

```bash
cd shell && git add src/pages/AdminExtensionsPage.tsx src/pages/AdminExtensionsPage.test.tsx
git commit -m "feat(shell): adminExtensionsPage sur TriptychLayout (Catalogue/Extensions/Détail)"
```

---

## Task 3: Shell — `HarvestSourcesAdminPage` sur `TriptychLayout`, dialogues convertis en panneaux

**Files:**
- Create: `shell/src/shell/CreateHarvestSourcePanel.tsx`
- Create: `shell/src/shell/EditHarvestSourcePanel.tsx`
- Delete: `shell/src/shell/CreateHarvestSourceDialog.tsx`
- Delete: `shell/src/shell/CreateHarvestSourceDialog.test.tsx`
- Delete: `shell/src/shell/EditHarvestSourceDialog.tsx`
- Modify: `shell/src/pages/HarvestSourcesAdminPage.tsx`
- Modify: `shell/src/pages/HarvestSourcesAdminPage.test.tsx`
- Modify: `shell/e2e/harvest-wms.spec.ts`
- Modify: `shell/e2e/harvest-stac.spec.ts`
- Modify: `shell/e2e/harvest-csw.spec.ts`
- Modify: `shell/e2e/harvest-ckan.spec.ts`
- Modify: `shell/e2e/harvest-ogc-records.spec.ts`
- Modify: `shell/e2e/harvest-arcgis.spec.ts`

**Interfaces:**
- Consumes: `TriptychLayout` ; `Button`/`Panel`/`Input`/`ConfirmDialog` du
  kit (`shell/src/ui/kit/`) ; `useHarvestSources`/`useDeleteHarvestSource`/
  `useRunHarvestSource`/`useCreateHarvestSource`/`useUpdateHarvestSource`/
  `useInstanceInfo` (`shell/src/api/hooks.ts`, inchangés).
- Produces: `CreateHarvestSourcePanel({ onClose: () => void }): ReactNode` ;
  `EditHarvestSourcePanel({ source: HarvestSource, onClose: () => void }):
  ReactNode` — consommés uniquement par `HarvestSourcesAdminPage` ;
  `HarvestSourcesAdminPage()` — aucune prop (inchangé).

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/pages/HarvestSourcesAdminPage.test.tsx src/shell/CreateHarvestSourceDialog.test.tsx
cd shell && npx playwright test e2e/harvest-wms.spec.ts e2e/harvest-stac.spec.ts e2e/harvest-csw.spec.ts \
  e2e/harvest-ckan.spec.ts e2e/harvest-ogc-records.spec.ts e2e/harvest-arcgis.spec.ts
```

Expected: PASS (tous, état actuel avant modification).

- [ ] **Step 2: Créer `CreateHarvestSourcePanel.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCreateHarvestSource, useInstanceInfo } from "../api/hooks";
import type { HarvestSourceType } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";

const COPY_TYPES: HarvestSourceType[] = ["stac", "arcgis", "wfs", "ckan"];

export function CreateHarvestSourcePanel({ onClose }: { onClose: () => void }) {
  const createSource = useCreateHarvestSource();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [type, setType] = useState<HarvestSourceType>("stac");
  const [url, setUrl] = useState("");
  const [mode, setMode] = useState<"reference" | "copy">("reference");
  const copyAllowed = COPY_TYPES.includes(type);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!url) return;
    try {
      await createSource.mutateAsync({ type, url, mode, enabled: true });
      onClose();
    } catch {
      // surfaced via createSource.isError
    }
  }

  return (
    <section aria-label="Ajouter une source" className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">Ajouter une source</h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          Type
          <select
            aria-label="Type"
            className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
            value={type}
            onChange={(e) => {
              const next = e.target.value as HarvestSourceType;
              setType(next);
              if (!COPY_TYPES.includes(next)) setMode("reference");
            }}
          >
            <option value="stac">STAC</option>
            <option value="arcgis">ArcGIS Feature Service</option>
            <option value="wms">WMS</option>
            <option value="wfs">WFS</option>
            <option value="wmts">WMTS</option>
            <option value="csw">CSW</option>
            <option value="ogc-records">OGC API - Records</option>
            <option value="ckan">CKAN</option>
          </select>
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink">
          URL
          <Input aria-label="URL" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink">
          Mode
          <select
            aria-label="Mode"
            className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
            value={mode}
            onChange={(e) => setMode(e.target.value as "reference" | "copy")}
          >
            <option value="reference">Référence</option>
            <option value="copy" disabled={!copyAllowed}>
              Copie
            </option>
          </select>
        </label>
        {createSource.isError && (
          <p role="alert" className="text-sm text-danger">
            Échec de la création.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={!url || createSource.isPending || readOnly}>
            Enregistrer
          </Button>
        </div>
      </form>
    </section>
  );
}
```

- [ ] **Step 3: Créer `EditHarvestSourcePanel.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useInstanceInfo, useUpdateHarvestSource } from "../api/hooks";
import type { HarvestSource } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";

export function EditHarvestSourcePanel({
  source,
  onClose,
}: {
  source: HarvestSource;
  onClose: () => void;
}) {
  const updateSource = useUpdateHarvestSource(source.id);
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [url, setUrl] = useState(source.url);
  const [enabled, setEnabled] = useState(source.enabled);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateSource.mutateAsync({ url, enabled });
      onClose();
    } catch {
      // surfaced via updateSource.isError
    }
  }

  return (
    <section aria-label={`Éditer ${source.url}`} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">Éditer {source.url}</h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          URL
          <Input aria-label="URL" value={url} onChange={(e) => setUrl(e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            aria-label="Actif"
            checked={enabled}
            onChange={(e) => setEnabled(e.target.checked)}
          />
          Actif
        </label>
        {updateSource.isError && (
          <p role="alert" className="text-sm text-danger">
            Échec de la mise à jour.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={updateSource.isPending || readOnly}>
            Enregistrer
          </Button>
        </div>
      </form>
    </section>
  );
}
```

- [ ] **Step 4: Supprimer les anciens fichiers**

```bash
cd shell && git rm src/shell/CreateHarvestSourceDialog.tsx src/shell/CreateHarvestSourceDialog.test.tsx \
  src/shell/EditHarvestSourceDialog.tsx
```

- [ ] **Step 5: Réécrire `HarvestSourcesAdminPage.tsx`**

Remplacer tout le contenu du fichier par :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  useDeleteHarvestSource,
  useHarvestSources,
  useInstanceInfo,
  useRunHarvestSource,
} from "../api/hooks";
import type { HarvestSource } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { CreateHarvestSourcePanel } from "../shell/CreateHarvestSourcePanel";
import { EditHarvestSourcePanel } from "../shell/EditHarvestSourcePanel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

export function HarvestSourcesAdminPage() {
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const sourcesQuery = useHarvestSources();
  const deleteSource = useDeleteHarvestSource();
  const runSource = useRunHarvestSource();
  const [creating, setCreating] = useState(false);
  const [editing, setEditing] = useState<HarvestSource | null>(null);
  const [deleting, setDeleting] = useState<HarvestSource | null>(null);

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await deleteSource.mutateAsync(deleting.id);
      setDeleting(null);
    } catch {
      // surfaced via deleteSource.isError
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
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
          id: "sources",
          label: "Moissonnage",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <div className="flex items-center justify-between">
                <h1 className="text-lg font-bold text-ink">Moissonnage</h1>
                {!readOnly && (
                  <Button
                    size="sm"
                    onClick={() => {
                      // Exclusivité mutuelle avec editing (décision 5, plan
                      // SP-30j) : plus de barrière modale pour l'empêcher.
                      setEditing(null);
                      setCreating(true);
                    }}
                  >
                    Ajouter une source
                  </Button>
                )}
              </div>
              {sourcesQuery.isLoading && <p role="status">Chargement…</p>}
              {sourcesQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec du chargement des sources.
                </p>
              )}
              {deleteSource.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec de la suppression.
                </p>
              )}
              {sourcesQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">Type</th>
                      <th className="py-2 text-ink">URL</th>
                      <th className="py-2 text-ink">Mode</th>
                      <th className="py-2 text-ink">Actif</th>
                      <th className="py-2 text-ink">Dernier statut</th>
                      <th className="py-2 text-ink">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {sourcesQuery.data.map((source) => (
                      <tr key={source.id} className="border-b border-rule-2">
                        <td className="py-2 text-ink">{source.type}</td>
                        <td className="py-2 text-xs text-ink-2">{source.url}</td>
                        <td className="py-2 text-ink">{source.mode}</td>
                        <td className="py-2 text-ink">{source.enabled ? "Oui" : "Non"}</td>
                        <td className="py-2 text-ink">{source.lastStatus ?? "—"}</td>
                        <td className="py-2 flex gap-2">
                          {!readOnly && (
                            <>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => runSource.mutate(source.id)}
                              >
                                Moissonner maintenant
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => {
                                  setCreating(false);
                                  setEditing(source);
                                }}
                              >
                                Éditer
                              </Button>
                              <Button
                                type="button"
                                variant="outline"
                                size="sm"
                                onClick={() => setDeleting(source)}
                              >
                                Supprimer
                              </Button>
                            </>
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ),
        }}
        inspect={{
          id: "detail",
          label: "Détail",
          content: (
            <div className="flex flex-col gap-3 p-3">
              {creating && <CreateHarvestSourcePanel onClose={() => setCreating(false)} />}
              {editing && (
                <EditHarvestSourcePanel
                  key={editing.id}
                  source={editing}
                  onClose={() => setEditing(null)}
                />
              )}
            </div>
          ),
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        title="Supprimer la source"
        message={
          deleting
            ? `Supprimer la source « ${deleting.url} » ? Les items/collections déjà produits survivent.`
            : ""
        }
        confirmLabel="Supprimer"
        pending={deleteSource.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
```

- [ ] **Step 6: Réécrire `HarvestSourcesAdminPage.test.tsx`**

Remplacer tout le contenu du fichier par :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { HarvestSourcesAdminPage } from "./HarvestSourcesAdminPage";

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. Stub local, avec vi.unstubAllGlobals()
// en afterEach dès son introduction (même patron que SqlLabPage.test.tsx,
// SP-30i).
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

beforeEach(() => stubMatchMedia(false));
afterEach(() => vi.unstubAllGlobals());

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <HarvestSourcesAdminPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("admin creates a STAC source and triggers a manual run", async () => {
  let created: Record<string, unknown> | null = null;
  let ran = false;
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: created
          ? [
              {
                id: "src-1",
                type: "stac",
                url: "https://stac.example.com/collections",
                mode: "reference",
                enabled: true,
                intervalMinutes: null,
                lastRunAt: null,
                lastStatus: ran ? "ok" : null,
                lastError: null,
              },
            ]
          : [],
      }),
    ),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      created = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        { id: "src-1", ...created, lastRunAt: null, lastStatus: null, lastError: null },
        { status: 201 },
      );
    }),
    http.post("https://core.test/harvest/sources/src-1/run", () => {
      ran = true;
      return HttpResponse.json({ status: "queued" }, { status: 202 });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.type(
    await screen.findByLabelText("URL"),
    "https://stac.example.com/collections",
  );
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(created).not.toBeNull());
  expect(await screen.findByText("https://stac.example.com/collections")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Moissonner maintenant" }));
  await waitFor(() => expect(ran).toBe(true));
});

test("edits a source via the row action", async () => {
  let patched: unknown;
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: [
          {
            id: "src-1",
            type: "stac",
            url: "https://a",
            mode: "reference",
            enabled: true,
            intervalMinutes: null,
            lastRunAt: null,
            lastStatus: null,
            lastError: null,
          },
        ],
      }),
    ),
    http.patch("https://core.test/harvest/sources/src-1", async ({ request }) => {
      patched = await request.json();
      return HttpResponse.json({
        id: "src-1",
        type: "stac",
        url: "https://a (édité)",
        mode: "reference",
        enabled: true,
        intervalMinutes: null,
        lastRunAt: null,
        lastStatus: null,
        lastError: null,
      });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Éditer" }));
  const urlInput = await screen.findByLabelText("URL");
  await userEvent.clear(urlInput);
  await userEvent.type(urlInput, "https://a (édité)");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(patched).toMatchObject({ url: "https://a (édité)" }));
});

test("delete removes the source from the list", async () => {
  let deleted = false;
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: deleted
          ? []
          : [
              {
                id: "src-1",
                type: "stac",
                url: "https://a",
                mode: "reference",
                enabled: true,
                intervalMinutes: null,
                lastRunAt: null,
                lastStatus: null,
                lastError: null,
              },
            ],
      }),
    ),
    http.delete("https://core.test/harvest/sources/src-1", () => {
      deleted = true;
      return HttpResponse.text("", { status: 204 });
    }),
  );
  render(<Harness />);
  await screen.findByText("https://a");
  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  // Le bouton de la ligne et celui du ConfirmDialog partagent le même nom
  // accessible une fois le dialogue ouvert — on scope au dialogue (même
  // patron que CollectionsAdminPage.test.tsx : within(dialog).getByRole).
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(deleted).toBe(true));
  await waitFor(() => expect(screen.queryByText("https://a")).not.toBeInTheDocument());
});

test("masque les boutons d'écriture en mode démo (read-only)", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: [
          {
            id: "s1",
            type: "stac",
            url: "https://stac/x",
            mode: "reference",
            enabled: true,
            intervalMinutes: null,
            lastRunAt: null,
            lastStatus: "ok",
            lastError: null,
          },
        ],
      }),
    ),
  );
  render(<Harness />);
  await screen.findByText("https://stac/x");
  expect(screen.queryByRole("button", { name: "Ajouter une source" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Moissonner maintenant" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Éditer" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Supprimer" })).toBeNull();
});

test("sends the selected type (arcgis) on creation", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "s1",
          type: "arcgis",
          url: "https://x/FeatureServer",
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.type(await screen.findByLabelText("URL"), "https://x/FeatureServer");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "arcgis");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(body).toEqual({
      type: "arcgis",
      url: "https://x/FeatureServer",
      mode: "reference",
      enabled: true,
    }),
  );
});

test("envoie le type WMS et force le mode référence (copie désactivée)", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "s1",
          type: "wms",
          url: "https://ows/x",
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.type(await screen.findByLabelText("URL"), "https://ows/x");
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "copy");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "wms");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(body).toEqual({ type: "wms", url: "https://ows/x", mode: "reference", enabled: true }),
  );
});

test("garde le mode copie disponible pour WFS", async () => {
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.selectOptions(await screen.findByLabelText("Type"), "wfs");
  const copyOption = screen.getByRole("option", { name: "Copie" }) as HTMLOptionElement;
  expect(copyOption.disabled).toBe(false);
});

test("envoie le type CSW et force le mode référence (copie désactivée)", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "s1",
          type: "csw",
          url: "https://geonetwork.example.com/csw",
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.type(await screen.findByLabelText("URL"), "https://geonetwork.example.com/csw");
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "copy");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "csw");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(body).toEqual({
      type: "csw",
      url: "https://geonetwork.example.com/csw",
      mode: "reference",
      enabled: true,
    }),
  );
});

test("garde le mode copie désactivé pour OGC API - Records", async () => {
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.selectOptions(await screen.findByLabelText("Type"), "ogc-records");
  const copyOption = screen.getByRole("option", { name: "Copie" }) as HTMLOptionElement;
  expect(copyOption.disabled).toBe(true);
});

test("envoie le type CKAN en mode copie", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "s1",
          type: "ckan",
          url: "https://demo.data.gouv.fr",
          mode: "copy",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.type(await screen.findByLabelText("URL"), "https://demo.data.gouv.fr");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "ckan");
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "copy");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(body).toEqual({
      type: "ckan",
      url: "https://demo.data.gouv.fr",
      mode: "copy",
      enabled: true,
    }),
  );
});

test("garde le mode copie disponible pour CKAN", async () => {
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.selectOptions(await screen.findByLabelText("Type"), "ckan");
  const copyOption = screen.getByRole("option", { name: "Copie" }) as HTMLOptionElement;
  expect(copyOption.disabled).toBe(false);
});

test("sous viewport étroit, affiche trois onglets Catalogue/Moissonnage/Détail avec Moissonnage actif par défaut", async () => {
  stubMatchMedia(true);
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
  );
  render(<Harness />);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Moissonnage", "Détail"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Moissonnage");
});
```

Note : le test « shows an access-denied message… » de l'ancien fichier
disparaît (couvert par `RequireRole.test.tsx`, SP-30i). Les six tests
type/mode viennent de `CreateHarvestSourceDialog.test.tsx` (supprimé Step 4),
adaptés pour cliquer d'abord sur « Ajouter une source » (plus de rendu
synchrone via `open={true}`). Le test « edits a source via the row action »
est **nouveau** — `EditHarvestSourceDialog` n'avait pas de fichier de test
dédié avant ce plan ; cette couverture n'existait nulle part.

- [ ] **Step 7: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/pages/HarvestSourcesAdminPage.test.tsx
```

Expected: PASS — 12 tests.

- [ ] **Step 8: Mettre à jour les six occurrences E2E qui scopaient sur le dialogue**

Dans chacun des six fichiers suivants, remplacer le bloc qui scope sur
`getByRole("dialog", { name: "Ajouter une source" })` par un scope sur
`getByRole("region", ...)` — la `<section aria-label="Ajouter une source">`
de `CreateHarvestSourcePanel` porte un rôle ARIA implicite `region` (élément
`<section>` avec nom accessible). La scoping reste nécessaire pour la même
raison que documentée dans `admin-collections.spec.ts` (le nom accessible du
conteneur contiendrait "Type"/"URL" en substring sur un `getByLabel` non
scopé dans certains cas) — même schéma de remplacement partout, seule la
variable est renommée `dialog` → `panel` pour ne pas laisser un nom trompeur.

`e2e/harvest-wms.spec.ts:122-124` — remplacer :

```ts
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(CAPS);
  await dialog.getByLabel("Type").selectOption("wms");
```

par :

```ts
  const panel = page.getByRole("region", { name: "Ajouter une source" });
  await panel.getByLabel("URL").fill(CAPS);
  await panel.getByLabel("Type").selectOption("wms");
```

(La ligne 149, `getByRole("dialog", { name: "Nouvel élément" })`, est le
dialogue de `NewItemButton` — dette de chrome distincte, hors périmètre de
ce plan, **ne pas toucher**.)

`e2e/harvest-stac.spec.ts:104-105` — remplacer :

```ts
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill("https://stac.example.com/collections");
```

par :

```ts
  const panel = page.getByRole("region", { name: "Ajouter une source" });
  await panel.getByLabel("URL").fill("https://stac.example.com/collections");
```

`e2e/harvest-csw.spec.ts:92-94` — remplacer :

```ts
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(CSW_URL);
  await dialog.getByLabel("Type").selectOption("csw");
```

par :

```ts
  const panel = page.getByRole("region", { name: "Ajouter une source" });
  await panel.getByLabel("URL").fill(CSW_URL);
  await panel.getByLabel("Type").selectOption("csw");
```

`e2e/harvest-ckan.spec.ts:92-94` (première occurrence) — remplacer :

```ts
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(PORTAL);
  await dialog.getByLabel("Type").selectOption("ckan");
```

par :

```ts
  const panel = page.getByRole("region", { name: "Ajouter une source" });
  await panel.getByLabel("URL").fill(PORTAL);
  await panel.getByLabel("Type").selectOption("ckan");
```

`e2e/harvest-ckan.spec.ts:258-261` (seconde occurrence, mode copie) —
remplacer :

```ts
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(PORTAL);
  await dialog.getByLabel("Type").selectOption("ckan");
  await dialog.getByLabel("Mode").selectOption("copy");
```

par :

```ts
  const panel = page.getByRole("region", { name: "Ajouter une source" });
  await panel.getByLabel("URL").fill(PORTAL);
  await panel.getByLabel("Type").selectOption("ckan");
  await panel.getByLabel("Mode").selectOption("copy");
```

`e2e/harvest-ogc-records.spec.ts:92-94` — remplacer :

```ts
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(OGC_URL);
  await dialog.getByLabel("Type").selectOption("ogc-records");
```

par :

```ts
  const panel = page.getByRole("region", { name: "Ajouter une source" });
  await panel.getByLabel("URL").fill(OGC_URL);
  await panel.getByLabel("Type").selectOption("ogc-records");
```

`e2e/harvest-arcgis.spec.ts:104-106` — remplacer :

```ts
  const dialog = page.getByRole("dialog", { name: "Ajouter une source" });
  await dialog.getByLabel("URL").fill(FS);
  await dialog.getByLabel("Type").selectOption("arcgis");
```

par :

```ts
  const panel = page.getByRole("region", { name: "Ajouter une source" });
  await panel.getByLabel("URL").fill(FS);
  await panel.getByLabel("Type").selectOption("arcgis");
```

- [ ] **Step 9: Relancer les six specs E2E harvest, vérifier le succès**

```bash
cd shell && npx playwright test e2e/harvest-wms.spec.ts e2e/harvest-stac.spec.ts e2e/harvest-csw.spec.ts \
  e2e/harvest-ckan.spec.ts e2e/harvest-ogc-records.spec.ts e2e/harvest-arcgis.spec.ts
```

Expected: PASS (tous).

- [ ] **Step 10: Vérifier l'absence de couleur Tailwind en dur**

```bash
grep -rnE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/pages/HarvestSourcesAdminPage.tsx \
  shell/src/shell/CreateHarvestSourcePanel.tsx \
  shell/src/shell/EditHarvestSourcePanel.tsx
```

Expected: aucune sortie.

- [ ] **Step 11: Vérifier l'absence d'ancien import et de comparaison de droits résiduelle**

```bash
grep -n 'ui/button"\|ui/dialog"\|ui/input"\|ui/ConfirmDialog"\|isAdmin\|isAnalyst\|useMe' \
  shell/src/pages/HarvestSourcesAdminPage.tsx \
  shell/src/shell/CreateHarvestSourcePanel.tsx \
  shell/src/shell/EditHarvestSourcePanel.tsx
```

Expected: aucune sortie.

- [ ] **Step 12: Suite E2E complète (piège n°6)**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed, ou mieux.

- [ ] **Step 13: Commit**

```bash
cd shell && git add src/pages/HarvestSourcesAdminPage.tsx src/pages/HarvestSourcesAdminPage.test.tsx \
  src/shell/CreateHarvestSourcePanel.tsx src/shell/EditHarvestSourcePanel.tsx \
  src/shell/CreateHarvestSourceDialog.tsx src/shell/CreateHarvestSourceDialog.test.tsx \
  src/shell/EditHarvestSourceDialog.tsx \
  e2e/harvest-wms.spec.ts e2e/harvest-stac.spec.ts e2e/harvest-csw.spec.ts \
  e2e/harvest-ckan.spec.ts e2e/harvest-ogc-records.spec.ts e2e/harvest-arcgis.spec.ts
git commit -m "feat(shell): harvestSourcesAdminPage sur TriptychLayout, dialogues convertis en panneaux"
```

---

## Task 4: Shell — `CollectionsAdminPage` sur `TriptychLayout`, dialogues convertis en panneaux

**Files:**
- Create: `shell/src/shell/EditCollectionPanel.tsx`
- Create: `shell/src/shell/CollectionSharePanel.tsx`
- Create: `shell/src/shell/RegisterCollectionPanel.tsx`
- Delete: `shell/src/shell/EditCollectionDialog.tsx`
- Delete: `shell/src/shell/EditCollectionDialog.test.tsx`
- Delete: `shell/src/shell/CollectionShareDialog.tsx`
- Delete: `shell/src/shell/CollectionShareDialog.test.tsx`
- Delete: `shell/src/shell/RegisterCollectionDialog.tsx`
- Delete: `shell/src/shell/RegisterCollectionDialog.test.tsx`
- Modify: `shell/src/pages/CollectionsAdminPage.tsx`
- Modify: `shell/src/pages/CollectionsAdminPage.test.tsx`
- Modify: `shell/e2e/admin-collections.spec.ts`

**Interfaces:**
- Consumes: `TriptychLayout` ; `Button`/`Panel`/`Input`/`ConfirmDialog` du
  kit (`shell/src/ui/kit/`) ; `useCollectionsAdmin`/`useDeleteCollection`/
  `useUpdateCollection`/`useCreateCollection`/`useCandidateTables`/
  `useGroups`/`useCollectionSharing`/`useSetCollectionSharing`/
  `useInstanceInfo` (`shell/src/api/hooks.ts`, inchangés).
- Produces: `EditCollectionPanel({ collection: CollectionAdmin, onClose: ()
  => void }): ReactNode` ; `CollectionSharePanel({ collectionId: string,
  onClose: () => void }): ReactNode` ; `RegisterCollectionPanel({ onClose:
  () => void }): ReactNode` — consommés uniquement par `CollectionsAdminPage` ;
  `CollectionsAdminPage()` — aucune prop (inchangé).

- [ ] **Step 1: Baseline**

```bash
cd shell && npx vitest run src/pages/CollectionsAdminPage.test.tsx src/shell/EditCollectionDialog.test.tsx \
  src/shell/CollectionShareDialog.test.tsx src/shell/RegisterCollectionDialog.test.tsx
cd shell && npx playwright test e2e/admin-collections.spec.ts
```

Expected: PASS (tous, état actuel avant modification).

- [ ] **Step 2: Créer `EditCollectionPanel.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useInstanceInfo, useUpdateCollection } from "../api/hooks";
import type { CollectionAdmin } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";

export function EditCollectionPanel({
  collection,
  onClose,
}: {
  collection: CollectionAdmin;
  onClose: () => void;
}) {
  const updateCollection = useUpdateCollection(collection.id);
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [title, setTitle] = useState(collection.title);
  const [description, setDescription] = useState(collection.description);
  const [isPublic, setIsPublic] = useState(collection.isPublic);
  const [editable, setEditable] = useState(collection.editable);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateCollection.mutateAsync({ title, description, isPublic, editable });
      onClose();
    } catch {
      // surfaced via updateCollection.isError
    }
  }

  return (
    <section aria-label={`Éditer ${collection.title}`} className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">Éditer {collection.title}</h2>
      <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm text-ink">
          Titre
          <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm text-ink">
          Description
          <Input
            aria-label="Description"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
          />
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            aria-label="Public"
            checked={isPublic}
            onChange={(e) => setIsPublic(e.target.checked)}
          />
          Public
        </label>
        <label className="flex items-center gap-2 text-sm text-ink">
          <input
            type="checkbox"
            aria-label="Éditable"
            checked={editable}
            onChange={(e) => setEditable(e.target.checked)}
          />
          Éditable
        </label>
        {updateCollection.isError && (
          <p role="alert" className="text-sm text-danger">
            Échec de la mise à jour.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={updateCollection.isPending || readOnly}>
            Enregistrer
          </Button>
        </div>
      </form>
    </section>
  );
}
```

- [ ] **Step 3: Créer `CollectionSharePanel.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import {
  useCollectionSharing,
  useGroups,
  useInstanceInfo,
  useSetCollectionSharing,
} from "../api/hooks";
import type { ShareRole } from "../api/types";
import { Button } from "../ui/kit/Button";

export function CollectionSharePanel({
  collectionId,
  onClose,
}: {
  collectionId: string;
  onClose: () => void;
}) {
  const groupsQuery = useGroups();
  const sharingQuery = useCollectionSharing(collectionId);
  const setSharing = useSetCollectionSharing(collectionId);
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;

  const [isPublic, setIsPublic] = useState(false);
  const [roles, setRoles] = useState<Record<string, ShareRole | undefined>>({});

  useEffect(() => {
    if (!sharingQuery.data) return;
    setIsPublic(sharingQuery.data.public);
    const map: Record<string, ShareRole> = {};
    sharingQuery.data.groups.forEach((g) => {
      map[g.groupId] = g.role;
    });
    setRoles(map);
  }, [sharingQuery.data]);

  async function submit() {
    const groups = Object.entries(roles)
      .filter(([, role]) => role)
      .map(([groupId, role]) => ({ groupId, role: role as ShareRole }));
    try {
      await setSharing.mutateAsync({ public: isPublic, groups });
      onClose();
    } catch {
      /* surfaced via setSharing.isError */
    }
  }

  const loading = groupsQuery.isLoading || sharingQuery.isLoading;
  const failed = groupsQuery.isError || sharingQuery.isError;
  const ready = groupsQuery.isSuccess && sharingQuery.isSuccess;

  return (
    <section aria-label="Partager la collection" className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">Partager la collection</h2>
      {loading && <p role="status">Chargement…</p>}
      {failed && (
        <p role="alert" className="text-sm text-danger">
          Erreur de chargement.
        </p>
      )}
      {ready && (
        <div className="flex flex-col gap-3">
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              aria-label="Public"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            Public (visible par tous)
          </label>

          <div className="flex flex-col gap-2">
            {groupsQuery.data.map((g) => (
              <div key={g.id} className="flex items-center justify-between gap-2 text-sm text-ink">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={`Groupe ${g.title}`}
                    checked={!!roles[g.id]}
                    onChange={(e) =>
                      setRoles((r) => ({
                        ...r,
                        [g.id]: e.target.checked ? (r[g.id] ?? "viewer") : undefined,
                      }))
                    }
                  />
                  {g.title}
                </label>
                <select
                  aria-label={`Rôle ${g.title}`}
                  className="h-8 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
                  disabled={!roles[g.id]}
                  value={roles[g.id] ?? "viewer"}
                  onChange={(e) => setRoles((r) => ({ ...r, [g.id]: e.target.value as ShareRole }))}
                >
                  <option value="viewer">Lecteur</option>
                  <option value="editor">Éditeur</option>
                </select>
              </div>
            ))}
          </div>

          {setSharing.isError && (
            <p role="alert" className="text-sm text-danger">
              Échec du partage.
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              Annuler
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={setSharing.isPending || readOnly}
              onClick={() => void submit()}
            >
              Enregistrer
            </Button>
          </div>
        </div>
      )}
    </section>
  );
}
```

- [ ] **Step 4: Créer `RegisterCollectionPanel.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useCandidateTables, useCreateCollection, useInstanceInfo } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";

export function RegisterCollectionPanel({ onClose }: { onClose: () => void }) {
  const candidatesQuery = useCandidateTables();
  const createCollection = useCreateCollection();
  const instanceQuery = useInstanceInfo();
  const readOnly = instanceQuery.data?.readOnly === true;
  const [tableName, setTableName] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [isPublic, setIsPublic] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!tableName) return;
    try {
      await createCollection.mutateAsync({
        tableName,
        title: title.trim() || undefined,
        description: description.trim() || undefined,
        isPublic,
      });
      onClose();
    } catch {
      // surfaced via createCollection.isError
    }
  }

  return (
    <section aria-label="Enregistrer une table" className="flex flex-col gap-3">
      <h2 className="text-sm font-semibold text-ink">Enregistrer une table</h2>
      {candidatesQuery.isLoading && <p role="status">Chargement…</p>}
      {candidatesQuery.isError && (
        <p role="alert" className="text-sm text-danger">
          Échec du chargement des tables candidates.
        </p>
      )}
      {candidatesQuery.data && candidatesQuery.data.length === 0 && (
        <p className="text-sm text-ink-2">
          Aucune table à enregistrer — toutes les tables éligibles du schéma public sont déjà des
          collections, ou importez un fichier depuis le catalogue.
        </p>
      )}
      {candidatesQuery.data && candidatesQuery.data.length > 0 && (
        <form onSubmit={(e) => void submit(e)} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm text-ink">
            Table
            <select
              aria-label="Table"
              className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
              value={tableName}
              onChange={(e) => setTableName(e.target.value)}
            >
              <option value="" />
              {candidatesQuery.data.map((c) => (
                <option key={c.tableName} value={c.tableName} disabled={!c.registrable}>
                  {c.registrable ? c.tableName : `${c.tableName} (${c.reason})`}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm text-ink">
            Titre
            <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-sm text-ink">
            Description
            <Input
              aria-label="Description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </label>
          <label className="flex items-center gap-2 text-sm text-ink">
            <input
              type="checkbox"
              aria-label="Public"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            Public
          </label>
          {createCollection.isError && (
            <p role="alert" className="text-sm text-danger">
              Échec de l'enregistrement.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              Annuler
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={!tableName || createCollection.isPending || readOnly}
            >
              Enregistrer
            </Button>
          </div>
        </form>
      )}
    </section>
  );
}
```

- [ ] **Step 5: Supprimer les anciens fichiers**

```bash
cd shell && git rm src/shell/EditCollectionDialog.tsx src/shell/EditCollectionDialog.test.tsx \
  src/shell/CollectionShareDialog.tsx src/shell/CollectionShareDialog.test.tsx \
  src/shell/RegisterCollectionDialog.tsx src/shell/RegisterCollectionDialog.test.tsx
```

- [ ] **Step 6: Réécrire `CollectionsAdminPage.tsx`**

Remplacer tout le contenu du fichier par :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useCollectionsAdmin, useDeleteCollection } from "../api/hooks";
import type { CollectionAdmin } from "../api/types";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { CollectionSharePanel } from "../shell/CollectionSharePanel";
import { EditCollectionPanel } from "../shell/EditCollectionPanel";
import { RegisterCollectionPanel } from "../shell/RegisterCollectionPanel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

export function CollectionsAdminPage() {
  const collectionsQuery = useCollectionsAdmin();
  const deleteCollection = useDeleteCollection();
  const [registering, setRegistering] = useState(false);
  const [editing, setEditing] = useState<CollectionAdmin | null>(null);
  const [sharing, setSharing] = useState<CollectionAdmin | null>(null);
  const [deleting, setDeleting] = useState<CollectionAdmin | null>(null);

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await deleteCollection.mutateAsync(deleting.id);
      setDeleting(null);
    } catch {
      // surfaced via deleteCollection.isError
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
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
          id: "collections",
          label: "Collections",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <div className="flex items-center justify-between">
                <h1 className="text-lg font-bold text-ink">Collections</h1>
                <Button
                  size="sm"
                  onClick={() => {
                    // Exclusivité mutuelle avec editing/sharing (décision 5,
                    // plan SP-30j) : plus de barrière modale pour l'empêcher.
                    setEditing(null);
                    setSharing(null);
                    setRegistering(true);
                  }}
                >
                  Enregistrer une table
                </Button>
              </div>
              {collectionsQuery.isLoading && <p role="status">Chargement…</p>}
              {collectionsQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec du chargement des collections.
                </p>
              )}
              {deleteCollection.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec de la suppression.
                </p>
              )}
              {collectionsQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">Titre</th>
                      <th className="py-2 text-ink">Table</th>
                      <th className="py-2 text-ink">Public</th>
                      <th className="py-2 text-ink">Éditable</th>
                      <th className="py-2 text-ink">Entités</th>
                      <th className="py-2 text-ink">Propriétaire</th>
                      <th className="py-2 text-ink">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {collectionsQuery.data.map((col) => (
                      <tr key={col.id} className="border-b border-rule-2">
                        <td className="py-2 text-ink">{col.title}</td>
                        <td className="py-2 text-xs text-ink-2">{col.tableName}</td>
                        <td className="py-2 text-ink">{col.isPublic ? "Oui" : "Non"}</td>
                        <td className="py-2 text-ink">{col.editable ? "Oui" : "Non"}</td>
                        <td className="py-2 text-ink">{col.featureCount ?? "—"}</td>
                        <td className="py-2 text-ink">{col.owner ?? "—"}</td>
                        <td className="py-2 flex gap-2">
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setRegistering(false);
                              setSharing(null);
                              setEditing(col);
                            }}
                          >
                            Éditer
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => {
                              setRegistering(false);
                              setEditing(null);
                              setSharing(col);
                            }}
                          >
                            Partager
                          </Button>
                          <Button
                            type="button"
                            variant="outline"
                            size="sm"
                            onClick={() => setDeleting(col)}
                          >
                            Supprimer
                          </Button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ),
        }}
        inspect={{
          id: "detail",
          label: "Détail",
          content: (
            <div className="flex flex-col gap-3 p-3">
              {registering && <RegisterCollectionPanel onClose={() => setRegistering(false)} />}
              {editing && (
                <EditCollectionPanel
                  key={editing.id}
                  collection={editing}
                  onClose={() => setEditing(null)}
                />
              )}
              {sharing && (
                <CollectionSharePanel
                  key={sharing.id}
                  collectionId={sharing.id}
                  onClose={() => setSharing(null)}
                />
              )}
            </div>
          ),
        }}
      />
      <ConfirmDialog
        open={!!deleting}
        title="Supprimer la collection"
        message={
          deleting
            ? `Désenregistrer « ${deleting.title} » ? La table PostGIS ne sera pas supprimée.`
            : ""
        }
        confirmLabel="Supprimer"
        pending={deleteCollection.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={() => void confirmDelete()}
      />
    </div>
  );
}
```

- [ ] **Step 7: Réécrire `CollectionsAdminPage.test.tsx`**

Remplacer tout le contenu du fichier par :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { CollectionsAdminPage } from "./CollectionsAdminPage";

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. Stub local, avec vi.unstubAllGlobals()
// en afterEach dès son introduction (même patron que SqlLabPage.test.tsx,
// SP-30i).
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

beforeEach(() => stubMatchMedia(false));
afterEach(() => vi.unstubAllGlobals());

type CollectionAdminFixture = {
  id: string;
  title: string;
  description: string;
  tableName: string;
  isPublic: boolean;
  editable: boolean;
  geometryType: string | null;
  srid: number | null;
  pkColumn: string;
  permissions: { read: boolean; write: boolean; delete: boolean; share: boolean };
  featureCount: number | null;
  owner: string | null;
};

const INCIDENTS: CollectionAdminFixture = {
  id: "incidents",
  title: "Incidents",
  description: "",
  tableName: "incidents",
  isPublic: false,
  editable: true,
  geometryType: "Point",
  srid: 4326,
  pkColumn: "id",
  permissions: { read: true, write: true, delete: false, share: true },
  featureCount: 3,
  owner: "admin",
};

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <CollectionsAdminPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("lists collections and registers a new one via the panel", async () => {
  let posted: unknown;
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [
          {
            tableName: "points_interet",
            registrable: true,
            geometryType: "Point",
            srid: 4326,
            columnCount: 3,
          },
        ],
      }),
    ),
    http.post("https://core.test/collections", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json({ ...INCIDENTS, id: "points_interet", title: "points_interet" });
    }),
  );
  render(<Harness />);
  await screen.findByText("Incidents");
  expect(screen.getByText("admin")).toBeInTheDocument(); // owner column

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer une table" }));
  await userEvent.selectOptions(await screen.findByLabelText("Table"), "points_interet");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  // No title typed here — isPublic is still always sent (a real `false`,
  // never dropped by JSON.stringify), only the untouched title/description
  // fields drop out (empty string → undefined via `.trim() || undefined`).
  await waitFor(() => expect(posted).toEqual({ tableName: "points_interet", isPublic: false }));
});

test("shows an empty-state message when there are no candidate tables", async () => {
  server.use(
    http.get("https://core.test/collections", () => HttpResponse.json({ collections: [] })),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Enregistrer une table" }));
  await waitFor(() => expect(screen.getByText(/Aucune table à enregistrer/)).toBeInTheDocument());
});

test("disables a non-registrable candidate and shows its reason", async () => {
  server.use(
    http.get("https://core.test/collections", () => HttpResponse.json({ collections: [] })),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [
          { tableName: "widgets", registrable: false, reason: "table has no primary key" },
          {
            tableName: "points_interet",
            registrable: true,
            geometryType: "Point",
            srid: 4326,
            columnCount: 3,
          },
        ],
      }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Enregistrer une table" }));
  await screen.findByLabelText("Table");
  const widgetsOption = screen.getByRole("option", { name: /widgets.*table has no primary key/ });
  expect(widgetsOption).toBeDisabled();
  const poiOption = screen.getByRole("option", { name: "points_interet" });
  expect(poiOption).not.toBeDisabled();
});

test("disables the register submit button when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/collections", () => HttpResponse.json({ collections: [] })),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [
          {
            tableName: "points_interet",
            registrable: true,
            geometryType: "Point",
            srid: 4326,
            columnCount: 3,
          },
        ],
      }),
    ),
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Enregistrer une table" }));
  await userEvent.selectOptions(await screen.findByLabelText("Table"), "points_interet");
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled());
});

test("edits a collection via the row action", async () => {
  let patched: unknown;
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.patch("https://core.test/collections/incidents", async ({ request }) => {
      patched = await request.json();
      return HttpResponse.json({ ...INCIDENTS, title: "Incidents (v2)" });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Éditer" }));
  const titleInput = await screen.findByLabelText("Titre");
  await userEvent.clear(titleInput);
  await userEvent.type(titleInput, "Incidents (v2)");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(patched).toMatchObject({ title: "Incidents (v2)" }));
});

test("surfaces an alert when editing a collection fails", async () => {
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.patch("https://core.test/collections/incidents", () =>
      HttpResponse.json({}, { status: 500 }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Éditer" }));
  await screen.findByLabelText("Titre");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Échec de la mise à jour."),
  );
});

test("disables the edit submit button when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Éditer" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled());
});

test("deletes a collection after confirming", async () => {
  let deleteCalled = false;
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.delete("https://core.test/collections/incidents", () => {
      deleteCalled = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Supprimer" }));
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(deleteCalled).toBe(true));
});

test("shares a collection via the row action", async () => {
  let putBody: unknown;
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.get("https://core.test/groups", () =>
      HttpResponse.json([{ id: "g1", name: "Équipe terrain" }]),
    ),
    http.get("https://core.test/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.put("https://core.test/collections/incidents/sharing", async ({ request }) => {
      putBody = await request.json();
      return HttpResponse.json({ public: true, groups: [] });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Partager" }));
  await userEvent.click(await screen.findByLabelText("Public"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(putBody).toEqual({ public: true, groups: [] }));
});

test("disables the share submit button when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.get("https://core.test/groups", () =>
      HttpResponse.json([{ id: "g1", name: "Équipe terrain" }]),
    ),
    http.get("https://core.test/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Partager" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled());
});

test("switching from edit to share on a different row closes the edit panel (exclusivité mutuelle)", async () => {
  const other: CollectionAdminFixture = { ...INCIDENTS, id: "parcs", title: "Parcs" };
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS, other] }),
    ),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.get("https://core.test/groups", () => HttpResponse.json([])),
    http.get("https://core.test/collections/parcs/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
  );
  render(<Harness />);
  const editButtons = await screen.findAllByRole("button", { name: "Éditer" });
  await userEvent.click(editButtons[0]);
  expect(await screen.findByLabelText("Titre")).toBeInTheDocument();
  const shareButtons = screen.getAllByRole("button", { name: "Partager" });
  await userEvent.click(shareButtons[1]);
  await screen.findByText("Partager la collection");
  expect(screen.queryByLabelText("Titre")).not.toBeInTheDocument();
});

test("sous viewport étroit, affiche trois onglets Catalogue/Collections/Détail avec Collections actif par défaut", async () => {
  stubMatchMedia(true);
  server.use(http.get("https://core.test/collections", () => HttpResponse.json({ collections: [] })));
  render(<Harness />);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Collections", "Détail"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Collections");
});
```

Note : le test « shows an access-denied message… » disparaît (couvert par
`RequireRole.test.tsx`, SP-30i). Les tests d'état vide/option désactivée/
lecture-seule viennent des trois fichiers de dialogue supprimés (Step 5),
adaptés pour cliquer d'abord sur le bouton déclencheur. Le test
« surfaces an alert when editing a collection fails » et le test
d'exclusivité mutuelle sont **nouveaux** : le premier comble un trou de
couverture qui existait déjà dans `EditCollectionDialog.test.tsx` avant
suppression (il l'avait, je le migre) ; le second vérifie directement la
décision 5 de ce plan (aucun équivalent avant, la barrière modale rendait le
scénario impossible à observer).

- [ ] **Step 8: Lancer les tests, vérifier le succès**

```bash
cd shell && npx vitest run src/pages/CollectionsAdminPage.test.tsx
```

Expected: PASS — 13 tests.

- [ ] **Step 9: Mettre à jour `admin-collections.spec.ts`**

Dans `e2e/admin-collections.spec.ts`, remplacer (lignes 146-159) :

```ts
  await page.getByRole("button", { name: "Enregistrer une table" }).click();
  // Scoped to the dialog: the RegisterCollectionDialog's own role="dialog"
  // element carries aria-label="Enregistrer une table" (its title), whose
  // accessible name contains the substring "Table" — an unscoped
  // getByLabel("Table") resolves to both that dialog and the <select>,
  // tripping Playwright's strict mode. Same fix pattern as the "Supprimer"
  // scoping below (ConfirmDialog vs. row action button).
  const registerDialog = page.getByRole("dialog", { name: "Enregistrer une table" });
  await registerDialog.getByLabel("Table").selectOption("points_interet");
  await registerDialog.getByLabel("Titre").fill("Points d'intérêt");
  // exact: true — the page's own "Enregistrer une table" button (behind the
  // dialog overlay, still in the DOM) is a substring superstring match of
  // "Enregistrer" and would otherwise trip Playwright's strict mode.
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
```

par :

```ts
  await page.getByRole("button", { name: "Enregistrer une table" }).click();
  // Scoped to the panel: RegisterCollectionPanel's <section> carries
  // aria-label="Enregistrer une table" (role="region" implicite), dont le nom
  // accessible contient la sous-chaîne "Table" — un getByLabel("Table") non
  // scopé résoudrait à la fois ce conteneur et le <select>, faisant échouer
  // le mode strict de Playwright. Même schéma de correction que le scoping
  // "Supprimer" plus bas (ConfirmDialog vs. bouton de ligne). SP-30j : la
  // page bascule sur TriptychLayout, RegisterCollectionDialog (role="dialog")
  // devient RegisterCollectionPanel (role="region" implicite).
  const registerPanel = page.getByRole("region", { name: "Enregistrer une table" });
  await registerPanel.getByLabel("Table").selectOption("points_interet");
  await registerPanel.getByLabel("Titre").fill("Points d'intérêt");
  // exact: true — the page's own "Enregistrer une table" button (still in
  // the DOM, not behind an overlay anymore) is a substring superstring match
  // of "Enregistrer" and would otherwise trip Playwright's strict mode.
  await page.getByRole("button", { name: "Enregistrer", exact: true }).click();
```

Les scopings `page.getByRole("dialog")` restants (lignes 186 et 195, la
suppression) ne changent pas : `ConfirmDialog` reste un vrai `role="dialog"`
Radix (Task 4 le migre seulement vers `ui/kit/ConfirmDialog`, sans changer
son rôle ARIA).

- [ ] **Step 10: Relancer `admin-collections.spec.ts`, vérifier le succès**

```bash
cd shell && npx playwright test e2e/admin-collections.spec.ts
```

Expected: PASS (2 tests).

- [ ] **Step 11: Vérifier l'absence de couleur Tailwind en dur**

```bash
grep -rnE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/pages/CollectionsAdminPage.tsx \
  shell/src/shell/EditCollectionPanel.tsx \
  shell/src/shell/CollectionSharePanel.tsx \
  shell/src/shell/RegisterCollectionPanel.tsx
```

Expected: aucune sortie.

- [ ] **Step 12: Vérifier l'absence d'ancien import et de comparaison de droits résiduelle**

```bash
grep -n 'ui/button"\|ui/dialog"\|ui/input"\|ui/ConfirmDialog"\|isAdmin\|isAnalyst\|useMe' \
  shell/src/pages/CollectionsAdminPage.tsx \
  shell/src/shell/EditCollectionPanel.tsx \
  shell/src/shell/CollectionSharePanel.tsx \
  shell/src/shell/RegisterCollectionPanel.tsx
```

Expected: aucune sortie.

- [ ] **Step 13: Suite E2E complète (piège n°6)**

```bash
cd shell && npm run e2e
```

Expected: PASS — 118 passed / 4 skipped / 0 failed, ou mieux.

- [ ] **Step 14: Commit**

```bash
cd shell && git add src/pages/CollectionsAdminPage.tsx src/pages/CollectionsAdminPage.test.tsx \
  src/shell/EditCollectionPanel.tsx src/shell/CollectionSharePanel.tsx src/shell/RegisterCollectionPanel.tsx \
  src/shell/EditCollectionDialog.tsx src/shell/EditCollectionDialog.test.tsx \
  src/shell/CollectionShareDialog.tsx src/shell/CollectionShareDialog.test.tsx \
  src/shell/RegisterCollectionDialog.tsx src/shell/RegisterCollectionDialog.test.tsx \
  e2e/admin-collections.spec.ts
git commit -m "feat(shell): collectionsAdminPage sur TriptychLayout, dialogues convertis en panneaux"
```

---

## Task 5: Vérification finale

Ce plan ne se termine pas par un commit propre — c'est une tâche de
vérification. Si un des steps échoue, revenir à la tâche responsable
(identifiable par le fichier en cause) pour corriger, jamais par un
correctif générique ici.

- [ ] **Step 1: Suite Vitest complète**

```bash
cd shell && npx vitest run
```

Expected: PASS — 230 fichiers / ~1856 tests (223/1829 avant ce plan côté
compte de fichiers : SP-30i a laissé 223 fichiers/1829 tests ; ce plan
supprime 4 fichiers de test de dialogue et en ajoute 0 nouveau fichier —
seuls les trois fichiers de page existants sont réécrits — net −4 fichiers
+ tests consolidés dedans : 4 tests `AdminExtensionsPage.test.tsx` (+1 vs
avant), 12 tests `HarvestSourcesAdminPage.test.tsx` (+9 vs les 3 avant :
+6 migrés de `CreateHarvestSourceDialog.test.tsx`, +1 nouveau « edits a
source », +1 narrow-viewport, −1 access-denied), 13 tests
`CollectionsAdminPage.test.tsx` (+9 vs les 4 avant : +3 migrés de
`RegisterCollectionDialog.test.tsx`, +2 migrés d'`EditCollectionDialog.test.tsx`,
+1 migré de `CollectionShareDialog.test.tsx`, +1 nouveau « surfaces an alert
when editing », +1 nouveau « exclusivité mutuelle », +1 narrow-viewport,
−1 access-denied) — chiffres à confirmer par l'exécution réelle plutôt que
recalculés à la main, cf. verification-before-completion), aucune régression
sur les fichiers non touchés par ce plan.

- [ ] **Step 2: Couverture**

```bash
rm -rf shell/dist shell/dist-export
cd shell && npm run build
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```

Expected: seuil 88 respecté (piège documenté quatre fois : nettoyer
`dist/`/`dist-export/` avant de mesurer).

- [ ] **Step 3: Suite E2E complète (troisième exécution, après tous les commits de ce plan)**

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

- [ ] **Step 6: Recherche exhaustive de couleurs Tailwind en dur résiduelles dans tous les fichiers touchés par ce plan**

```bash
grep -rnE 'text-(red|slate|blue|gray|black)-[0-9]+|bg-(white|black|slate|gray)(/[0-9]+)?|border-(slate|gray)-[0-9]+' \
  shell/src/shell/routes.tsx \
  shell/src/pages/AdminExtensionsPage.tsx \
  shell/src/pages/HarvestSourcesAdminPage.tsx \
  shell/src/pages/CollectionsAdminPage.tsx \
  shell/src/shell/CreateHarvestSourcePanel.tsx \
  shell/src/shell/EditHarvestSourcePanel.tsx \
  shell/src/shell/EditCollectionPanel.tsx \
  shell/src/shell/CollectionSharePanel.tsx \
  shell/src/shell/RegisterCollectionPanel.tsx
```

Expected: aucune sortie.

- [ ] **Step 7: Confirmer qu'il ne reste plus que trois occurrences hors périmètre documenté**

```bash
grep -rn "isAnalyst\|isAdmin" shell/src --include="*.tsx" --include="*.ts" \
  | grep -v test | grep -v "capabilities.ts\|permissions.ts\|generated\|itemClient.ts\|types.ts\|RequireRole.tsx"
```

Expected : uniquement `AccountMenu.tsx` (2, affichage du badge de rôle —
lit `me.isAdmin`/`me.isAnalyst` déjà résolus, ne compare rien, hors
doctrine), `AppLayout.tsx` (2, construit `Profile` pour `capabilities.ts`,
hors périmètre par doctrine SP-29a/SP-30i) et `KitGalleryPage.tsx` (1, outil
interne `/internal/kit-gallery`, jamais lié depuis la navigation produit,
hors périmètre — voir « Ce que ce plan NE fait PAS »). Les trois pages
d'administration (`AdminExtensionsPage.tsx`, `CollectionsAdminPage.tsx`,
`HarvestSourcesAdminPage.tsx`) n'apparaissent plus dans cette liste — 5
occurrences dans 3 fichiers, contre 11 dans 6 fichiers avant ce plan (le
compte de départ inclut `KitGalleryPage.tsx`, jamais compté par le texte de
la spec SP-30 elle-même — vérifié par grep réel avant d'écrire ce plan,
piège n°3, plutôt que recopié depuis l'attendu de SP-30i qui ne le
mentionnait pas).

- [ ] **Step 8: Confirmer qu'aucun fichier `*Dialog.tsx` ne subsiste pour les cinq composants convertis**

```bash
ls shell/src/shell/EditCollectionDialog.tsx shell/src/shell/CollectionShareDialog.tsx \
  shell/src/shell/RegisterCollectionDialog.tsx shell/src/shell/CreateHarvestSourceDialog.tsx \
  shell/src/shell/EditHarvestSourceDialog.tsx 2>&1
```

Expected : cinq erreurs `No such file or directory` — tous supprimés.

- [ ] **Step 9: Confirmer la présence des cinq nouveaux fichiers `*Panel.tsx`**

```bash
ls shell/src/shell/EditCollectionPanel.tsx shell/src/shell/CollectionSharePanel.tsx \
  shell/src/shell/RegisterCollectionPanel.tsx shell/src/shell/CreateHarvestSourcePanel.tsx \
  shell/src/shell/EditHarvestSourcePanel.tsx
```

Expected : cinq chemins affichés, aucune erreur.
