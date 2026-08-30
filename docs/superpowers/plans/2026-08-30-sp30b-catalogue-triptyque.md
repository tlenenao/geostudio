# SP-30b — Catalogue sur le socle triptyque (CatalogPage, ItemDetailPage, ItemActions) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Basculer la famille **Catalogue** (`docs/superpowers/specs/2026-08-30-sp30-bascule-triptyque-design.md` §6.1, famille 2) sur `TriptychLayout` : `CatalogPage`, `ItemDetailPage`, `ItemActions`, `ShareDialog`. Supprime les derniers usages de `ui/{button,card,input,dialog}.tsx` et de `../ui/ConfirmDialog` dans ces fichiers ; aucun dialogue ne subsiste hors `ui/kit/ConfirmDialog` (confirmation de suppression uniquement). Corrige au passage les deux défauts Minor de la revue finale SP-30a qui portent directement sur `CatalogPage` (`.superpowers/sdd/sp30a-progress.md`).

**Périmètre explicitement hors de ce plan** (familles 3 à 8 du §6.1, à traiter dans des plans SP-30c+ séparés — le chantier est trop gros pour un seul plan revuable, cf. spec parent §11 « SP-30 est un gros bloc ») : `MapEditorPage` (Cartes), `DatasetEditPage` + `CollectionPermissions` shell-side (Données), `AppBuilderPage` (Apps & sites), `PipelineBuilderPage`/`ReportEditPage`/`VisualQueryWizardPage` (Automatisation), `SqlLabPage` (Analytique), `AdminExtensionsPage`/`CollectionsAdminPage`/`HarvestSourcesAdminPage` (Administration), `CollectionShareDialog`/`CreateHarvestSourceDialog`/`EditCollectionDialog`/`EditHarvestSourceDialog`/`RegisterCollectionDialog` (tous scoped aux familles Données/Automatisation/Administration). Les 13 Minor non détaillés de la 1ʳᵉ passe de revue SP-30a et les 4 Minor listés sans être Catalogue-scoped (`share: true` inerte dans `admin-collections.spec.ts`, garde d'exhaustivité sur `requiresRole`) restent également hors de ce plan.

**Architecture:** `ItemActions` perd toute UI de panneau inline (édition/miniature/partage) : cliquer ces trois entrées **navigue** vers `/items/{pk}?panel=edit|thumbnail|share` — que ce clic vienne d'une carte de la grille ou de la fiche elle-même (elle y est déjà, seul le paramètre change). Seule « Supprimer » garde une confirmation inline (`ui/kit/ConfirmDialog`), la seule exception autorisée par la spec. `ItemDetailPage` devient le seul endroit qui rend ces trois panneaux, comme contenu de son volet `inspect`, piloté par `?panel=` (source de vérité dans l'URL, pas un état local — même piège que `?type=` en SP-30a). `ShareDialog` perd son enveloppe `<Dialog>` et devient `ShareForm`, un composant de contenu pur. `CatalogPage` et `ItemDetailPage` s'enveloppent chacun dans `<div className="-m-6 ...">` pour neutraliser le `p-6` que `AppLayout` applique à son contenu (nécessaire pour toute page encore non basculée — cf. Constraints) sans toucher `AppLayout.tsx` lui-même ni les ~13 pages non migrées qui en dépendent encore.

**Tech Stack:** React 19, react-router-dom, @tanstack/react-query, kit de primitives SP-29b (`shell/src/ui/kit/`), Vitest + Testing Library, Playwright.

## Global Constraints

- Docs et identifiants de test en français ; code/identifiants en anglais (CLAUDE.md).
- Aucun dialogue ne survit hors `ui/kit/ConfirmDialog` (spec §2.1) : `ui/dialog.tsx` (ancien) ne doit plus être importé nulle part dans les fichiers touchés par ce plan à l'issue de la Task 4.
- Aucune couleur Tailwind en dur (`slate-*`, `red-600`, `black/40`, `white`) dans les fichiers touchés : tokens uniquement (`bg-surface`, `text-ink`, `text-ink-2`, `text-ink-3`, `border-rule`, `bg-raised`, `bg-sunken`, `text-danger`, `text-accent`) — `shell/src/styles/tokens.css` (SP-29a).
- `-m-6` est une technique de transition **locale à chaque page basculée sur `TriptychLayout`**, jamais un changement à `AppLayout.tsx` : les ~13 pages encore sur l'ancien layout (basculées dans SP-30c+) dépendent du `p-6` d'`AppLayout` et ne doivent pas être touchées par ce plan. Documenté comme dette assumée (§8 du présent plan), à nettoyer quand la dernière famille bascule et qu'`AppLayout` peut perdre son `p-6` global.
- `ItemActions` garde exactement son API publique actuelle (`{ item: Item, onDeleted?: () => void }`) — `CatalogPage.test.tsx` a un `vi.mock("../shell/ItemActions", ...)` qui ne doit pas nécessiter de changement.
- Régressions jsdom (piège n°10) : `window.matchMedia` n'existe pas sous jsdom — stub local à chaque fichier de test qui rend `TriptychLayout` (directement ou via `CatalogPage`/`ItemDetailPage`), jamais dans `shell/src/test/setup.ts`. Copier le stub exact d'`AppLayout.test.tsx:38-47` (`vi.stubGlobal("matchMedia", ...)` avec `matches: false`).
- E2E : `shell/e2e/catalog.spec.ts` (7 tests) et `shell/e2e/item-permissions.spec.ts` (1 test) sont le filet de non-régression comportementale de cette famille — vérifiés à chaque tâche qui touche `CatalogPage`/`ItemDetailPage`/`ItemActions`, pas seulement en fin de plan (Task 6 + relance ciblée dans les tasks précédentes si le composant change).
- Pas de changement au cœur (`core/`) dans ce plan : aucune régénération OpenAPI/TS attendue, diff vide légitime (piège n°1 — vide ici parce qu'aucun schéma ne change, pas parce qu'une surface est derrière un flag).

---

## Task 1: Shell — kit-ifier `ItemCard`, `MetadataForm`, `ThumbnailUpload`

**Files:**
- Modify: `shell/src/ui/ItemCard.tsx`
- Modify: `shell/src/ui/MetadataForm.tsx`
- Modify: `shell/src/ui/ThumbnailUpload.tsx`
- Test: `shell/src/ui/ItemCard.test.tsx` (nouveau — n'existe pas aujourd'hui)
- Test: `shell/src/ui/MetadataForm.test.tsx`, `shell/src/ui/ThumbnailUpload.test.tsx` (adapter s'ils existent déjà, sinon nouveaux)

**Interfaces:**
- Consumes: `Button`/`Input`/`Panel` de `shell/src/ui/kit/{Button,Input,Panel}.tsx` (SP-29b, signatures lues — `Button({variant,size,...props})`, `Input(...props)`, `Panel({className,children})`).
- Produces: `ItemCard`, `MetadataForm`, `ThumbnailUpload` avec la même API publique qu'aujourd'hui (aucun changement de props) — consommés tels quels par Task 4/5.

Ces trois fichiers sont des feuilles sans dépendance sur le reste du plan : les traiter en premier limite le risque des tâches suivantes.

- [ ] **Step 1: Vérifier l'état actuel des tests existants**

```bash
cd shell && npx vitest run src/ui/MetadataForm.test.tsx src/ui/ThumbnailUpload.test.tsx 2>&1 | tail -20
```

S'ils n'existent pas, le prochain step les crée en même temps que le composant est modifié. S'ils existent, ils passent avant modification (baseline).

- [ ] **Step 2: `ItemCard.tsx` — remplacer `ui/button`/`ui/card` par le kit, tokens**

```tsx
// SPDX-License-Identifier: Apache-2.0
import type { Item, ResourceType } from "../api/types";
import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
import { Button } from "./kit/Button";
import { Panel } from "./kit/Panel";

export function ItemCard({
  item,
  onOpen,
  actions,
}: {
  item: Item;
  onOpen: (pk: string, type: ResourceType) => void;
  actions?: React.ReactNode;
}) {
  return (
    <Panel className="flex flex-col gap-2 p-4">
      <div className="flex items-start justify-between">
        <span className="w-fit rounded bg-sunken px-2 py-0.5 text-xs uppercase text-ink-2">
          {RESOURCE_TYPE_LABELS[item.resourceType]}
        </span>
        {actions}
      </div>
      {item.thumbnailUrl && (
        <img
          src={item.thumbnailUrl}
          alt={item.title}
          className="h-24 w-full rounded object-cover"
        />
      )}
      <h3 className="text-base font-semibold text-ink">{item.title}</h3>
      <p className="line-clamp-2 text-sm text-ink-2">{item.abstract}</p>
      <Button size="sm" className="mt-2 w-fit" onClick={() => onOpen(item.pk, item.resourceType)}>
        Ouvrir
      </Button>
    </Panel>
  );
}
```

- [ ] **Step 3: Test `ItemCard.test.tsx` (nouveau)**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { Item } from "../api/types";
import { ItemCard } from "./ItemCard";

const item: Item = {
  pk: "1",
  resourceType: "app",
  title: "Alpha",
  abstract: "Une app",
  owner: "alice",
  thumbnailUrl: null,
  date: "",
  configId: null,
  isPublished: false,
  permissions: { read: true, write: true, delete: true, share: true },
};

test("affiche le titre, le type et déclenche onOpen", async () => {
  const onOpen = vi.fn();
  render(<ItemCard item={item} onOpen={onOpen} />);
  expect(screen.getByText("Alpha")).toBeInTheDocument();
  expect(screen.getByText("App")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Ouvrir" }));
  expect(onOpen).toHaveBeenCalledWith("1", "app");
});

test("rend le contenu de la prop actions", () => {
  render(<ItemCard item={item} onOpen={() => {}} actions={<span>menu</span>} />);
  expect(screen.getByText("menu")).toBeInTheDocument();
});
```

Ajuster `"App"` si `RESOURCE_TYPE_LABELS.app` diffère (vérifier `shell/src/api/resourceTypes.ts` avant d'écrire l'assertion).

- [ ] **Step 4: `MetadataForm.tsx` — remplacer `Button`/`Input`, tokens sur le textarea**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Button } from "./kit/Button";
import { Input } from "./kit/Input";

export function MetadataForm({
  initial,
  onSubmit,
  onCancel,
  pending,
}: {
  initial: { title: string; abstract: string; keywords: string[] };
  onSubmit: (v: { title: string; abstract: string; keywords: string[] }) => void;
  onCancel: () => void;
  pending?: boolean;
}) {
  const [title, setTitle] = useState(initial.title);
  const [abstract, setAbstract] = useState(initial.abstract);
  const [keywords, setKeywords] = useState(initial.keywords.join(", "));

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const clean = title.trim();
    if (!clean) return;
    onSubmit({
      title: clean,
      abstract,
      keywords: keywords
        .split(",")
        .map((k) => k.trim())
        .filter((k) => k.length > 0),
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm text-ink">
        Titre
        <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm text-ink">
        Résumé
        <textarea
          aria-label="Résumé"
          className="min-h-20 rounded-md border border-rule bg-surface px-3 py-2 text-sm text-ink"
          value={abstract}
          onChange={(e) => setAbstract(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm text-ink">
        Mots-clés
        <Input
          aria-label="Mots-clés"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
        />
      </label>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Annuler
        </Button>
        <Button type="submit" size="sm" disabled={pending}>
          Enregistrer
        </Button>
      </div>
    </form>
  );
}
```

(La logique est inchangée — seuls les imports et les couleurs changent. Si `MetadataForm.test.tsx` existe déjà, le relancer suffit à vérifier la non-régression ; sinon écrire un test minimal couvrant la soumission et l'annulation, même patron que le Step 3 ci-dessus.)

- [ ] **Step 5: `ThumbnailUpload.tsx` — tokens seulement (pas d'ancien primitif importé)**

Remplacer `text-red-600` par `text-danger` ligne 43, et ajouter `text-ink` au label racine (ligne 31) :

```tsx
<div className="flex flex-col gap-1 text-sm text-ink">
```

et

```tsx
{error && (
  <p role="alert" className="text-sm text-danger">
    {error}
  </p>
)}
```

- [ ] **Step 6: Lancer la suite complète de cette tâche**

```bash
cd shell && npx vitest run src/ui/ItemCard.test.tsx src/ui/MetadataForm.test.tsx src/ui/ThumbnailUpload.test.tsx
```

Expected: tous verts.

- [ ] **Step 7: Commit**

```bash
git add shell/src/ui/ItemCard.tsx shell/src/ui/ItemCard.test.tsx shell/src/ui/MetadataForm.tsx shell/src/ui/ThumbnailUpload.tsx
git commit -m "feat(shell): itemCard/metadataForm/thumbnailUpload — kit + tokens"
```

---

## Task 2: Shell — `ShareDialog` devient `ShareForm` (contenu pur, sans `<Dialog>`)

**Files:**
- Create: `shell/src/shell/ShareForm.tsx`
- Delete: `shell/src/shell/ShareDialog.tsx`
- Create: `shell/src/shell/ShareForm.test.tsx`
- Delete: `shell/src/shell/ShareDialog.test.tsx`

**Interfaces:**
- Consumes: `useGroups`/`useSharing`/`useSetSharing` (`shell/src/api/hooks.ts`, signatures inchangées) ; `Button` du kit.
- Produces: `ShareForm({ item, onDone }: { item: Item; onDone: () => void })` — pas de prop `open`/`onClose`, le montage/démontage est décidé par l'appelant (Task 4). Consommé par Task 4.

- [ ] **Step 1: Écrire `ShareForm.test.tsx` (adapté de `ShareDialog.test.tsx`, sans assertions sur `role="dialog"`)**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { ReactNode } from "react";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { Item, ItemClient } from "../api/types";
import { ShareForm } from "./ShareForm";

const item: Item = {
  pk: "7",
  resourceType: "map",
  title: "Réseau",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "",
  configId: null,
  isPublished: false,
  permissions: { read: true, write: true, delete: true, share: true },
};

function wrapper(client: ItemClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    return (
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>{children}</ItemClientProvider>
      </QueryClientProvider>
    );
  };
}

function fakeClient(overrides: Partial<ItemClient> = {}): ItemClient {
  return {
    getGroups: vi.fn().mockResolvedValue([{ id: "g1", title: "SIG" }]),
    getSharing: vi.fn().mockResolvedValue({ public: false, groups: [] }),
    setSharing: vi.fn().mockResolvedValue(undefined),
    ...overrides,
  } as unknown as ItemClient;
}

test("charge les groupes et la portée actuelle, puis enregistre", async () => {
  const client = fakeClient();
  const onDone = vi.fn();
  render(<ShareForm item={item} onDone={onDone} />, { wrapper: wrapper(client) });

  expect(await screen.findByText("SIG")).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Public"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() => expect(client.setSharing).toHaveBeenCalledWith("7", { public: true, groups: [] }));
  expect(onDone).toHaveBeenCalled();
});

test("annuler appelle onDone sans enregistrer", async () => {
  const client = fakeClient();
  const onDone = vi.fn();
  render(<ShareForm item={item} onDone={onDone} />, { wrapper: wrapper(client) });
  await screen.findByText("SIG");
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  expect(client.setSharing).not.toHaveBeenCalled();
  expect(onDone).toHaveBeenCalled();
});
```

Vérifier contre `shell/src/api/itemClient.ts` les noms réels des méthodes (`getGroups`/`getSharing`/`setSharing` ou équivalents) avant de committer ce test — les adapter à la signature réelle si elle diffère (piège n°3, vérifier contre la source, pas la mémoire).

- [ ] **Step 2: Run — vérifier l'échec (le fichier n'existe pas encore)**

```bash
cd shell && npx vitest run src/shell/ShareForm.test.tsx
```

Expected: FAIL — `Cannot find module './ShareForm'`.

- [ ] **Step 3: Créer `ShareForm.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useGroups, useSetSharing, useSharing } from "../api/hooks";
import type { Item, ShareRole } from "../api/types";
import { Button } from "../ui/kit/Button";

export function ShareForm({ item, onDone }: { item: Item; onDone: () => void }) {
  const groupsQuery = useGroups();
  const sharingQuery = useSharing(item.pk);
  const setSharing = useSetSharing(item.pk);

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
    setSharing.reset();
    const groups = Object.entries(roles)
      .filter(([, role]) => role)
      .map(([groupId, role]) => ({ groupId, role: role as ShareRole }));
    try {
      await setSharing.mutateAsync({ public: isPublic, groups });
      onDone();
    } catch {
      /* surfaced via setSharing.isError */
    }
  }

  const loading = groupsQuery.isLoading || sharingQuery.isLoading;
  const failed = groupsQuery.isError || sharingQuery.isError;
  const ready = groupsQuery.isSuccess && sharingQuery.isSuccess;

  return (
    <div className="flex flex-col gap-3">
      <h3 className="text-sm font-semibold text-ink">Partager l'élément</h3>
      {loading && <p role="status">Chargement…</p>}
      {failed && (
        <p role="alert" className="text-sm text-danger">
          Erreur de chargement.
        </p>
      )}
      {ready && (
        <>
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
              <div key={g.id} className="flex items-center justify-between gap-2 text-sm">
                <label className="flex items-center gap-2 text-ink">
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
            <Button type="button" variant="outline" size="sm" onClick={onDone}>
              Annuler
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={setSharing.isPending}
              onClick={() => void submit()}
            >
              Enregistrer
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
```

Note : `useGroups()`/`useSharing(item.pk)` sans `{ enabled: open }` — `ShareForm` n'est monté que quand le panneau « share » est actif (Task 4), donc le montage lui-même fait office de porte ; pas de flag `enabled` à porter.

- [ ] **Step 4: Run — vérifier le succès**

```bash
cd shell && npx vitest run src/shell/ShareForm.test.tsx
```

Expected: PASS (2 tests).

- [ ] **Step 5: Supprimer `ShareDialog.tsx` et `ShareDialog.test.tsx`**

```bash
git rm shell/src/shell/ShareDialog.tsx shell/src/shell/ShareDialog.test.tsx
```

Ne pas encore mettre à jour `ItemActions.tsx` (qui importe encore `ShareDialog` à ce stade) — Task 3 le fait. `tsc --noEmit` échouera entre les deux tâches si elles sont committées séparément sans rebase ; committer Task 2 et Task 3 comme une paire logique si l'exécution est stricte tâche-par-tâche avec review entre les deux (le reviewer de Task 2 doit s'attendre à un `tsc` rouge tant que Task 3 n'est pas faite — le signaler explicitement dans le rapport de tâche).

- [ ] **Step 6: Commit**

```bash
git add shell/src/shell/ShareForm.tsx shell/src/shell/ShareForm.test.tsx
git commit -m "feat(shell): shareDialog devient shareForm (contenu pur, sans Dialog)"
```

---

## Task 3: Shell — `ItemActions` sans panneaux inline (navigation `?panel=`)

**Files:**
- Modify: `shell/src/shell/ItemActions.tsx`
- Modify: `shell/src/shell/ItemActions.test.tsx`

**Interfaces:**
- Consumes: `Button`/`ConfirmDialog` de `ui/kit` ; `Gate`/`Locked`/`hasPermission` (`auth/`, inchangés depuis SP-29a) ; `useNavigate` (react-router-dom).
- Produces: `ItemActions({ item, onDeleted? })` — API publique inchangée. Navigue vers `/items/{pk}?panel=edit|thumbnail|share` (consommé par Task 4). Consommé par Task 4 (fiche) et Task 5 (grille).

Le menu déroulant reste un `<div>` maison (pas le `Menu` générique du kit — son API `items: {label,onSelect,disabled,danger}[]` ne sait pas rendre le regroupement `Locked` à raison unique sur plusieurs entrées, une UI composée spécifique à `ItemActions` depuis SP-30a Task 5, pas un pattern de menu générique). Seuls les primitifs `Button`/`Dialog`/`ConfirmDialog` importés changent.

- [ ] **Step 1: Réécrire `ItemActions.test.tsx` — retirer les 2 tests qui attendaient un dialogue inline, ajouter 2 tests de navigation**

Retirer `"renames an item via the edit dialog"` et `"opens the share dialog from the menu"` (lignes 48-72 du fichier actuel). Les remplacer par :

```tsx
import { MemoryRouter, Route, Routes } from "react-router-dom";
// ... (garder les imports existants, ajouter Route/Routes si absents)

function HarnessWithRouter({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter initialEntries={["/"]}>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <Routes>
            <Route path="/" element={children} />
            <Route path="/items/:pk" element={<p>Fiche ouverte : {window.location.search}</p>} />
          </Routes>
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("« Modifier » navigue vers la fiche avec ?panel=edit", async () => {
  render(<ItemActions item={item} />, { wrapper: HarnessWithRouter });
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("button", { name: /modifier/i }));
  expect(await screen.findByText(/panel=edit/)).toBeInTheDocument();
});

test("« Partager » navigue vers la fiche avec ?panel=share", async () => {
  render(<ItemActions item={item} />, { wrapper: HarnessWithRouter });
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("button", { name: /partager/i }));
  expect(await screen.findByText(/panel=share/)).toBeInTheDocument();
});
```

`window.location.search` sous jsdom/MemoryRouter reflète l'URL virtuelle du router (MemoryRouter ne touche pas le vrai `window.location`) — utiliser plutôt `useSearchParams` dans la route factice :

```tsx
function ShowSearch() {
  const [params] = useSearchParams();
  return <p>Fiche ouverte : {params.toString()}</p>;
}
// ... <Route path="/items/:pk" element={<ShowSearch />} />
```

et les assertions `screen.findByText(/panel=edit/)` restent valables sur le texte rendu par `ShowSearch`.

Garder tel quel le reste du fichier (tests de suppression, publication, verrouillage par droits, bookmark/exportEnabled) — ils ne changent pas de comportement.

- [ ] **Step 2: Run — vérifier l'échec (comportement encore inchangé)**

```bash
cd shell && npx vitest run src/shell/ItemActions.test.tsx
```

Expected: les 2 nouveaux tests FAIL (aucune navigation aujourd'hui), le reste PASS.

- [ ] **Step 3: Réécrire `ItemActions.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useDeleteItem, useInstanceInfo, useUpdateItem } from "../api/hooks";
import type { Item } from "../api/types";
import { Button } from "../ui/kit/Button";
import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
import { Gate } from "../auth/Gate";
import { Locked } from "../auth/Locked";
import { hasPermission } from "../auth/permissions";
import { t } from "../i18n";

type MenuState = "closed" | "open" | "delete";

export function ItemActions({ item, onDeleted }: { item: Item; onDeleted?: () => void }) {
  const navigate = useNavigate();
  const [menu, setMenu] = useState<MenuState>("closed");
  const publish = useUpdateItem(item.pk);
  const remove = useDeleteItem();
  const exportEnabled = useInstanceInfo().data?.exportEnabled === true;

  async function togglePublish() {
    try {
      await publish.mutateAsync({ isPublished: !item.isPublished });
      setMenu("closed");
    } catch {
      /* surfaced via publish.isError */
    }
  }

  async function confirmDelete() {
    try {
      await remove.mutateAsync(item.pk);
      setMenu("closed");
      onDeleted?.();
    } catch {
      /* surfaced via remove.isError */
    }
  }

  function goToPanel(panel: "edit" | "thumbnail" | "share") {
    setMenu("closed");
    navigate(`/items/${item.pk}?panel=${panel}`);
  }

  return (
    <div className="relative">
      <Button
        size="sm"
        variant="ghost"
        aria-label={t("actions.menu")}
        onClick={() => setMenu(menu === "open" ? "closed" : "open")}
      >
        ⋯
      </Button>

      {menu === "open" && (
        <div className="absolute right-0 z-20 mt-1 flex w-44 flex-col rounded-md border border-rule bg-raised py-1 text-sm shadow-md">
          {hasPermission(item, "write") ? (
            <>
              <button
                className="px-3 py-1.5 text-left text-ink hover:bg-sunken"
                onClick={() => goToPanel("edit")}
              >
                {t("actions.edit")}
              </button>
              <button
                className="px-3 py-1.5 text-left text-ink hover:bg-sunken"
                onClick={() => void togglePublish()}
              >
                {item.isPublished ? t("actions.unpublish") : t("actions.publish")}
              </button>
              <button
                className="px-3 py-1.5 text-left text-ink hover:bg-sunken"
                onClick={() => goToPanel("thumbnail")}
              >
                {t("actions.thumbnail")}
              </button>
            </>
          ) : (
            <Locked reason={t("locked.needWrite")}>
              <button className="px-3 py-1.5 text-left">{t("actions.edit")}</button>
              <button className="px-3 py-1.5 text-left">
                {item.isPublished ? t("actions.unpublish") : t("actions.publish")}
              </button>
              <button className="px-3 py-1.5 text-left">{t("actions.thumbnail")}</button>
            </Locked>
          )}

          {item.resourceType === "bookmark" && exportEnabled && (
            <button
              className="px-3 py-1.5 text-left text-ink hover:bg-sunken"
              onClick={() => {
                setMenu("closed");
                navigate("/reports/new", { state: { bookmarkItemId: item.pk } });
              }}
            >
              {t("actions.scheduleReport")}
            </button>
          )}

          <Gate on={item} can="share">
            <button
              className="px-3 py-1.5 text-left text-ink hover:bg-sunken"
              onClick={() => goToPanel("share")}
            >
              {t("actions.share")}
            </button>
          </Gate>

          <Gate on={item} can="delete">
            <button
              className="px-3 py-1.5 text-left text-danger hover:bg-sunken"
              onClick={() => setMenu("delete")}
            >
              {t("actions.delete")}
            </button>
          </Gate>
        </div>
      )}

      <ConfirmDialog
        open={menu === "delete"}
        title={t("actions.deleteTitle")}
        message={t("actions.deleteMessage", { title: item.title })}
        confirmLabel={t("actions.delete")}
        pending={remove.isPending}
        onConfirm={() => void confirmDelete()}
        onCancel={() => setMenu("closed")}
      />
      {remove.isError && menu === "delete" && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {t("actions.deleteFailed")}
        </p>
      )}
      {publish.isError && menu === "open" && (
        <p role="alert" className="mt-2 text-sm text-danger">
          {t("actions.publishFailed")}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run — vérifier le succès**

```bash
cd shell && npx vitest run src/shell/ItemActions.test.tsx
```

Expected: PASS (tous les tests, y compris les 2 nouveaux et les tests de droits/verrouillage inchangés).

- [ ] **Step 5: `tsc --noEmit` sur tout le shell — plus aucune référence à `ShareDialog`/`ui/dialog`/`ui/ConfirmDialog` depuis `ItemActions`**

```bash
cd shell && npm run build 2>&1 | grep -i "ShareDialog\|ItemActions" || echo "OK — aucune référence résiduelle"
```

- [ ] **Step 6: Commit**

```bash
git add shell/src/shell/ItemActions.tsx shell/src/shell/ItemActions.test.tsx
git commit -m "feat(shell): itemActions navigue vers ?panel= au lieu d'ouvrir un dialogue"
```

---

## Task 4: Shell — `ItemDetailPage` sur `TriptychLayout`, panneaux pilotés par `?panel=`

**Files:**
- Modify: `shell/src/pages/ItemDetailPage.tsx`
- Modify: `shell/src/pages/ItemDetailPage.test.tsx`

**Interfaces:**
- Consumes: `TriptychLayout` (`shell/src/shell/chrome/TriptychLayout.tsx`, `{browse,work,inspect,defaultTabId}` — SP-30a) ; `ItemActions` (Task 3) ; `MetadataForm`/`ThumbnailUpload` (Task 1) ; `ShareForm` (Task 2) ; `useItem`/`useUpdateItem`/`useUploadThumbnail` (`api/hooks.ts`, inchangés) ; `RESOURCE_TYPE_LABELS` (`api/resourceTypes.ts`).
- Produces: `ItemDetailPage({ pk, onDeleted?, onOpenEditor? })` — API publique inchangée, `ItemDetailRoute` dans `shell/src/shell/routes.tsx` ne change pas.

- [ ] **Step 1: Écrire les nouveaux tests dans `ItemDetailPage.test.tsx`**

Ajouter en tête du fichier le stub `matchMedia` (Global Constraints) et un test qui vérifie que le paramètre `?panel=edit` affiche le formulaire dans le volet inspecter :

```tsx
beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
});

test("affiche le formulaire d'édition quand l'URL porte ?panel=edit", async () => {
  mockItem(); // helper existant ou à créer sur le même patron que CatalogPage.test.tsx (msw + server.use)
  render(<ItemDetailPage pk="1" />, {
    wrapper: ({ children }) => wrapperWithInitialSearch("/items/1?panel=edit", children),
  });
  expect(await screen.findByLabelText("Titre")).toBeInTheDocument();
});

test("aucun panneau affiché sans ?panel=", async () => {
  mockItem();
  render(<ItemDetailPage pk="1" />, { wrapper });
  await screen.findByRole("heading", { name: "Alpha" });
  expect(screen.queryByLabelText("Titre")).not.toBeInTheDocument();
});
```

Écrire `mockItem()`/`wrapperWithInitialSearch` sur le patron déjà utilisé dans `ItemDetailPage.test.tsx` existant (lire le fichier avant d'écrire — il a déjà un `wrapper` MSW pour `useItem`, le réutiliser et lui ajouter un variant avec `initialEntries` pour l'URL du panneau, même patron que `CatalogPage.test.tsx` Step "prend le type initial depuis le paramètre d'URL").

- [ ] **Step 2: Run — vérifier l'échec**

```bash
cd shell && npx vitest run src/pages/ItemDetailPage.test.tsx
```

Expected: les 2 nouveaux tests FAIL (`?panel=` pas encore lu), les anciens PASS ou FAIL selon ce que la Step 3 change (documenter dans le rapport de tâche lesquels changent de comportement, ex. le bouton « Ouvrir dans l'éditeur » reste identique donc son test ne bouge pas).

- [ ] **Step 3: Réécrire `ItemDetailPage.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { Link, useSearchParams } from "react-router-dom";
import { useItem, useUpdateItem, useUploadThumbnail } from "../api/hooks";
import { RESOURCE_TYPE_LABELS } from "../api/resourceTypes";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { MetadataForm } from "../ui/MetadataForm";
import { ThumbnailUpload } from "../ui/ThumbnailUpload";
import { ShareForm } from "../shell/ShareForm";
import { ItemActions } from "../shell/ItemActions";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

type PanelKind = "edit" | "thumbnail" | "share" | null;

export function ItemDetailPage({
  pk,
  onDeleted,
  onOpenEditor,
}: {
  pk: string;
  onDeleted?: () => void;
  onOpenEditor?: (type: string) => void;
}) {
  const query = useItem(pk);
  const [searchParams, setSearchParams] = useSearchParams();
  const panelParam = searchParams.get("panel");
  const panel: PanelKind =
    panelParam === "edit" || panelParam === "thumbnail" || panelParam === "share"
      ? panelParam
      : null;
  const closePanel = () => {
    const params = new URLSearchParams(searchParams);
    params.delete("panel");
    setSearchParams(params, { replace: true });
  };

  const update = useUpdateItem(pk);
  const thumbnail = useUploadThumbnail(pk);

  if (query.isLoading) return <p role="status">Chargement…</p>;
  if (query.isError || !query.data)
    return (
      <p role="alert" className="text-sm text-danger">
        Élément introuvable.
      </p>
    );

  const item = query.data;

  async function save(v: { title: string; abstract: string; keywords: string[] }) {
    try {
      await update.mutateAsync(v);
      closePanel();
    } catch {
      /* surfaced via update.isError */
    }
  }

  async function upload(file: File) {
    try {
      await thumbnail.mutateAsync(file);
      closePanel();
    } catch {
      /* surfaced via thumbnail.isError */
    }
  }

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="item"
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
              <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs text-ink-2">
                <dt>Type</dt>
                <dd>{RESOURCE_TYPE_LABELS[item.resourceType]}</dd>
                <dt>Modifié</dt>
                <dd>{item.date || "—"}</dd>
              </dl>
            </Panel>
          ),
        }}
        work={{
          id: "item",
          label: "Élément",
          content: (
            <article className="flex flex-col gap-3 p-6">
              <span className="w-fit rounded bg-sunken px-2 py-0.5 text-xs uppercase text-ink-2">
                {item.resourceType}
              </span>
              <h2 className="text-xl font-semibold text-ink">{item.title}</h2>
              <p className="text-sm text-ink-2">Propriétaire : {item.owner}</p>
              <p className="text-sm text-ink">{item.abstract}</p>
              {["map", "app", "dashboard", "dataset", "pipeline"].includes(item.resourceType) ? (
                <Button className="w-fit" onClick={() => onOpenEditor?.(item.resourceType)}>
                  Ouvrir dans l'éditeur
                </Button>
              ) : (
                <Button className="w-fit" disabled title="Éditeur indisponible pour ce type">
                  Ouvrir dans l'éditeur
                </Button>
              )}
            </article>
          ),
        }}
        inspect={{
          id: "actions",
          label: "Actions",
          content: (
            <div className="flex flex-col gap-3 p-3">
              <div className="flex items-center justify-between">
                <span className="text-sm font-medium text-ink">Actions</span>
                <ItemActions item={item} onDeleted={onDeleted} />
              </div>
              {panel === "edit" && (
                <Panel className="flex flex-col gap-2">
                  <MetadataForm
                    initial={{ title: item.title, abstract: item.abstract, keywords: [] }}
                    onSubmit={(v) => void save(v)}
                    onCancel={closePanel}
                    pending={update.isPending}
                  />
                  {update.isError && (
                    <p role="alert" className="text-sm text-danger">
                      {t("actions.saveFailed")}
                    </p>
                  )}
                </Panel>
              )}
              {panel === "thumbnail" && (
                <Panel className="flex flex-col gap-2">
                  <ThumbnailUpload
                    onUpload={(file) => void upload(file)}
                    pending={thumbnail.isPending}
                  />
                  {thumbnail.isError && (
                    <p role="alert" className="text-sm text-danger">
                      {t("actions.uploadFailed")}
                    </p>
                  )}
                </Panel>
              )}
              {panel === "share" && (
                <Panel>
                  <ShareForm item={item} onDone={closePanel} />
                </Panel>
              )}
            </div>
          ),
        }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Run — vérifier le succès**

```bash
cd shell && npx vitest run src/pages/ItemDetailPage.test.tsx
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/ItemDetailPage.tsx shell/src/pages/ItemDetailPage.test.tsx
git commit -m "feat(shell): itemDetailPage sur TriptychLayout, panneaux pilotés par ?panel="
```

---

## Task 5: Shell — `CatalogPage` sur `TriptychLayout`, `openError` en prop, 2 correctifs SP-30a

**Files:**
- Modify: `shell/src/pages/CatalogPage.tsx`
- Modify: `shell/src/pages/CatalogPage.test.tsx`
- Modify: `shell/src/shell/routes.tsx` (`CatalogRoute`, `BookmarksRoute`, `ReportsRoute`)

**Interfaces:**
- Consumes: `TriptychLayout` ; `Input`/`Button`/`Panel` du kit ; `ItemCard` (Task 1) ; `ItemActions` (Task 3) ; `t("catalog.count", {n})` (`i18n/catalog.fr.ts:55`, déjà défini).
- Produces: `CatalogPage({ onOpenItem, fixedType?, openError? })` — **`openError` change de forme** : `string | undefined` (message à afficher) au lieu du fragment JSX externe qu'affichait `CatalogRoute` — cassant pour les 3 appelants dans `routes.tsx`, corrigés dans la même tâche.

Corrige deux défauts Minor de la revue finale SP-30a (`.superpowers/sdd/sp30a-progress.md:61-63`) : `setType` poussait une entrée d'historique par changement de filtre (`setSearchParams` sans `{replace:true}`), et `page` n'était pas réinitialisée en changeant de domaine via `DomainBar` (`?type=` change sans démontage de `CatalogPage`, « Page 3 / 1 » restait affiché sur une grille vide).

- [ ] **Step 1: Écrire les tests des 2 correctifs + du nouveau volet `Résumé`**

Ajouter à `CatalogPage.test.tsx` :

```tsx
test("setType remplace l'entrée d'historique, ne l'empile pas", async () => {
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  await screen.findByLabelText("Type");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "dataset");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "map");
  // Deux changements de filtre ne doivent pousser aucune entrée d'historique
  // au-delà de l'entrée initiale — vérifié en confirmant qu'un seul "back"
  // ramène hors de la page plutôt que de rejouer un filtre intermédiaire.
  // (Test au niveau du composant : vérifier l'appel réel à setSearchParams
  // nécessite un spy sur useSearchParams, plus simple à couvrir par
  // inspection du 2e argument si react-router-dom l'expose — sinon,
  // documenter cette assertion comme non testable au niveau unitaire et la
  // reporter en E2E, Task 6, avec `page.goBack()`.)
});

test("réinitialise la page à 1 quand le type change (navigation DomainBar)", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 });
    }),
  );
  function Harness() {
    return (
      <>
        <Link to="/?type=dataset">Données</Link>
        <CatalogPage onOpenItem={() => {}} />
      </>
    );
  }
  render(
    <MemoryRouter initialEntries={["/?type=map"]}>
      <QueryClientProvider client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}>
        <ItemClientProvider client={createItemClient({ coreUrl: "https://core.test", getToken: () => "t" })}>
          <Harness />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("page")).toBe("2"));
  await userEvent.click(screen.getByText("Données"));
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("page")).toBe("1"));
});

test("le volet Résumé affiche le compte total et les filtres actifs", async () => {
  mockCatalogItems();
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  await screen.findByText("Alpha");
  expect(await screen.findByText("2 éléments")).toBeInTheDocument();
});

test("openError affiche le message d'échec d'ouverture dans le volet Catalogue", () => {
  render(<CatalogPage onOpenItem={() => {}} openError="Échec de l'ouverture de l'élément." />, {
    wrapper,
  });
  expect(screen.getByRole("alert")).toHaveTextContent("Échec de l'ouverture de l'élément.");
});
```

La 1ʳᵉ assertion de « setType remplace l'entrée d'historique » est délibérément faible au niveau unitaire (jsdom/MemoryRouter n'expose pas facilement la pile d'historique) — le test réel de cette propriété est en E2E (Task 6, `page.goBack()`). Le retirer du fichier ou le remplacer par un simple test de fumée (« le select change bien la query ») si l'assertion ci-dessus ne trouve pas de prise fiable — ne pas laisser un test qui ne vérifie rien.

- [ ] **Step 2: Run — vérifier l'échec**

```bash
cd shell && npx vitest run src/pages/CatalogPage.test.tsx
```

Expected: les nouveaux tests FAIL (`openError` n'est pas encore une prop, pas de volet Résumé, pas de réinitialisation de page).

- [ ] **Step 3: Réécrire `CatalogPage.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useItems, useMe } from "../api/hooks";
import type { ItemScope, ResourceType } from "../api/types";
import { RESOURCE_TYPE_LABELS, RESOURCE_TYPE_ORDER } from "../api/resourceTypes";
import { ItemCard } from "../ui/ItemCard";
import { ItemActions } from "../shell/ItemActions";
import { Input } from "../ui/kit/Input";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

const PAGE_SIZE = 12;
const SCOPE_LABELS: Record<ItemScope, string> = {
  all: "Tous",
  mine: "Mes éléments",
  shared: "Partagés avec moi",
  public: "Publics",
};

export function CatalogPage({
  onOpenItem,
  fixedType,
  openError,
}: {
  onOpenItem: (pk: string, type: ResourceType) => void;
  fixedType?: ResourceType;
  openError?: string;
}) {
  const [q, setQ] = useState("");
  const [searchParams, setSearchParams] = useSearchParams();
  const urlType = searchParams.get("type");
  const validUrlType =
    urlType !== null && (RESOURCE_TYPE_ORDER as readonly string[]).includes(urlType)
      ? (urlType as ResourceType)
      : "";
  const type = fixedType ?? validUrlType;
  const setType = (next: ResourceType | "") => {
    const params = new URLSearchParams(searchParams);
    if (next) {
      params.set("type", next);
    } else {
      params.delete("type");
    }
    // replace: true — SP-30a review finale : une entrée d'historique par
    // changement de filtre rendait le retour arrière du navigateur inutile.
    setSearchParams(params, { replace: true });
  };
  const [scope, setScope] = useState<ItemScope>("all");
  const [page, setPage] = useState(1);
  // SP-30a review finale : la page n'était pas réinitialisée en changeant de
  // domaine via DomainBar (?type= change sans démontage de CatalogPage) —
  // "Page 3 / 1" restait affiché sur une grille vide.
  useEffect(() => {
    setPage(1);
  }, [type, fixedType]);
  const me = useMe();

  const requiresMe = scope === "mine" || scope === "shared";
  const query = useItems(
    {
      q: q || undefined,
      type: type || undefined,
      page,
      pageSize: PAGE_SIZE,
      scope,
      me: requiresMe ? me.data?.username : undefined,
    },
    { enabled: !requiresMe || !!me.data },
  );

  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1;

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        defaultTabId="catalog"
        browse={{
          id: "filter",
          label: "Filtrer",
          content: (
            <div className="flex flex-col gap-4 p-3">
              <label className="flex flex-col gap-1 text-sm text-ink">
                Rechercher
                <Input
                  aria-label="Rechercher"
                  value={q}
                  onChange={(e) => {
                    setQ(e.target.value);
                    setPage(1);
                  }}
                />
              </label>
              {!fixedType && (
                <label className="flex flex-col gap-1 text-sm text-ink">
                  Type
                  <select
                    aria-label="Type"
                    className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                    value={type}
                    onChange={(e) => setType(e.target.value as ResourceType | "")}
                  >
                    <option value="">Tous</option>
                    {RESOURCE_TYPE_ORDER.map((rt) => (
                      <option key={rt} value={rt}>
                        {RESOURCE_TYPE_LABELS[rt]}
                      </option>
                    ))}
                  </select>
                </label>
              )}
              <label className="flex flex-col gap-1 text-sm text-ink">
                Portée
                <select
                  aria-label="Portée"
                  className="h-9 rounded-md border border-rule bg-surface px-3 text-sm text-ink"
                  value={scope}
                  onChange={(e) => {
                    setScope(e.target.value as ItemScope);
                    setPage(1);
                  }}
                >
                  {(Object.keys(SCOPE_LABELS) as ItemScope[]).map((s) => (
                    <option key={s} value={s}>
                      {SCOPE_LABELS[s]}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          ),
        }}
        work={{
          id: "catalog",
          label: "Catalogue",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-6">
              {openError && (
                <p role="alert" className="text-sm text-danger">
                  {openError}
                </p>
              )}
              {query.isLoading && <p role="status">Chargement…</p>}
              {query.isError && (
                <div role="alert" className="text-sm text-danger">
                  Erreur de chargement.{" "}
                  <Button size="sm" variant="outline" onClick={() => void query.refetch()}>
                    Réessayer
                  </Button>
                </div>
              )}
              {query.isSuccess && query.data.items.length === 0 && (
                <p className="text-sm text-ink-3">Aucun élément.</p>
              )}
              {query.isSuccess && query.data.items.length > 0 && (
                <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {query.data.items.map((item) => (
                    <ItemCard
                      key={item.pk}
                      item={item}
                      onOpen={onOpenItem}
                      actions={<ItemActions item={item} />}
                    />
                  ))}
                </div>
              )}
              <div className="mt-auto flex items-center gap-3">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page <= 1}
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                >
                  Précédent
                </Button>
                <span className="text-sm text-ink-2">
                  Page {page} / {totalPages}
                </span>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={page >= totalPages}
                  onClick={() => setPage((p) => p + 1)}
                >
                  Suivant
                </Button>
              </div>
            </div>
          ),
        }}
        inspect={{
          id: "summary",
          label: "Résumé",
          content: (
            <Panel className="m-3 flex flex-col gap-2 text-sm">
              <p className="font-medium text-ink">{t("catalog.count", { n: query.data?.total ?? 0 })}</p>
              <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-xs text-ink-2">
                <dt>Recherche</dt>
                <dd>{q || "—"}</dd>
                <dt>Type</dt>
                <dd>{type ? RESOURCE_TYPE_LABELS[type] : "Tous"}</dd>
                <dt>Portée</dt>
                <dd>{SCOPE_LABELS[scope]}</dd>
              </dl>
            </Panel>
          ),
        }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Mettre à jour `routes.tsx` — `openError` devient un message, plus un fragment JSX externe**

```tsx
function CatalogRoute() {
  const { onOpenItem, openError } = useOpenItem();
  return (
    <CatalogPage
      onOpenItem={onOpenItem}
      openError={openError ? "Échec de l'ouverture de l'élément." : undefined}
    />
  );
}

function BookmarksRoute() {
  const { onOpenItem, openError } = useOpenItem();
  return (
    <CatalogPage
      onOpenItem={onOpenItem}
      fixedType="bookmark"
      openError={openError ? "Échec de l'ouverture du signet." : undefined}
    />
  );
}
```

et dans `ReportsRoute` :

```tsx
function ReportsRoute() {
  const { onOpenItem, openError } = useOpenItem();
  return (
    <CatalogPage
      onOpenItem={onOpenItem}
      fixedType="report"
      openError={openError ? "Échec de l'ouverture du rapport." : undefined}
    />
  );
}
```

(Motif : `CatalogPage` doit rester le seul et unique enfant de `AppLayout`'s content wrapper pour que la technique `-m-6` du Step 3 reste sûre — un fragment `<>{err}<CatalogPage/></>` externe casserait la marge négative sur le mauvais élément. Cf. Global Constraints.)

- [ ] **Step 5: Vérifier `routes.test.tsx` n'a pas d'assertion sur l'ancien fragment externe**

```bash
cd shell && npx vitest run src/shell/routes.test.tsx
```

Adapter si un test cherche le message d'erreur en dehors de `CatalogPage` (peu probable — vérifier avant de committer).

- [ ] **Step 6: Run — vérifier le succès**

```bash
cd shell && npx vitest run src/pages/CatalogPage.test.tsx src/shell/routes.test.tsx
```

Expected: PASS.

- [ ] **Step 7: E2E ciblée — confirmer qu'aucune régression sur `catalog.spec.ts`/`item-permissions.spec.ts` à ce stade**

```bash
cd shell && npx playwright test e2e/catalog.spec.ts e2e/item-permissions.spec.ts
```

Expected: 8/8 verts, sans modification de ces fichiers (comportement préservé par construction — mêmes `aria-label`, mêmes rôles, `<select>` natif inchangé).

- [ ] **Step 8: Commit**

```bash
git add shell/src/pages/CatalogPage.tsx shell/src/pages/CatalogPage.test.tsx shell/src/shell/routes.tsx
git commit -m "feat(shell): catalogPage sur TriptychLayout, corrige history/page-reset (suivi SP-30a)"
```

---

## Task 6: E2E — nouvelle couverture pour les panneaux inline + dégradation 390 px

**Files:**
- Modify: `shell/e2e/catalog.spec.ts` (ajouts seulement)
- Create: `shell/e2e/item-detail-panels.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`shell/e2e/mocks.ts`, patron déjà utilisé par tous les fichiers `e2e/*.spec.ts`).

- [ ] **Step 1: Ajouter à `catalog.spec.ts` — le retour arrière du navigateur après un changement de filtre**

```ts
test("changer de filtre ne remplit pas l'historique (retour arrière direct)", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  await page.getByLabel("Type").selectOption("dataset");
  await page.getByLabel("Type").selectOption("map");
  await page.goBack();
  // Un seul retour doit sortir de la page (revenir à about:blank / page
  // précédente réelle), pas rejouer "dataset" — la preuve la plus fiable
  // ici est que l'URL ne contient plus aucun ?type= issu de nos deux
  // changements de filtre consécutifs.
  await expect(page).not.toHaveURL(/type=(dataset|map)/);
});
```

- [ ] **Step 2: Nouveau fichier `item-detail-panels.spec.ts` — édition et partage via le volet inspecter**

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("modifier le titre depuis le menu Actions ouvre le panneau d'édition sur la fiche", async ({
  page,
}) => {
  await mockCore(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Actions" }).first().click();
  await page.getByRole("button", { name: "Modifier" }).click();
  await expect(page).toHaveURL(/\/items\/1\?panel=edit$/);
  const title = page.getByLabelText("Titre");
  await title.fill("Alpha renommé");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect(page.getByRole("heading", { name: "Alpha renommé" })).toBeVisible();
  await expect(page).toHaveURL(/\/items\/1$/);
});

test("partager depuis la fiche ouvre le formulaire de partage inline, sans dialogue", async ({
  page,
}) => {
  await mockCore(page);
  await page.goto("/items/1");
  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Partager" }).click();
  await expect(page).toHaveURL(/\/items\/1\?panel=share$/);
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByText("Partager l'élément")).toBeVisible();
});
```

Vérifier contre `shell/e2e/mocks.ts` que l'item `pk=1`/titre `Alpha` et l'endpoint de mise à jour (`PATCH /items/1` ou équivalent) sont bien mockés par `mockCore` avant d'écrire ces assertions — s'appuyer sur le mock existant utilisé par `catalog.spec.ts` (même fonction).

- [ ] **Step 3: Dégradation 390 px — Catalogue et Détail (2 des 8 écrans de référence ; les 6 autres restent aux familles SP-30c+)**

```ts
test("390 px : le catalogue passe en onglets, un volet à la fois", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await mockCore(page);
  await page.goto("/");
  await expect(page.getByRole("tablist")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Catalogue" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
  await page.getByRole("tab", { name: "Filtrer" }).click();
  await expect(page.getByLabel("Rechercher")).toBeVisible();
});

test("390 px : la fiche d'un item passe en onglets", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 800 });
  await mockCore(page);
  await page.goto("/items/1");
  await expect(page.getByRole("tablist")).toBeVisible();
  await expect(page.getByRole("tab", { name: "Élément" })).toHaveAttribute(
    "aria-selected",
    "true",
  );
});
```

Ajouter ces deux tests dans `item-detail-panels.spec.ts` (le premier pourrait aussi vivre dans `catalog.spec.ts` — choix laissé à l'exécutant, cohérence de fichier prioritaire sur la lettre du plan).

- [ ] **Step 4: Run — suite E2E complète de cette tâche**

```bash
cd shell && npx playwright test e2e/catalog.spec.ts e2e/item-detail-panels.spec.ts e2e/item-permissions.spec.ts
```

Expected: tous verts.

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/catalog.spec.ts shell/e2e/item-detail-panels.spec.ts
git commit -m "test(shell): e2e — panneaux inline de la fiche, historique de filtre, 390px catalogue"
```

---

## Task 7: Portes de qualité + suite complète

**Files:** aucun (vérification seule).

- [ ] **Step 1: Suite Vitest complète + couverture**

```bash
cd shell
rm -rf dist dist-export  # piège documenté 4 fois : ne pas mesurer la couverture avec ces artefacts présents
npm run test
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```

Expected: aucune régression sur le compte de tests mesuré au dernier `### Livré` (222 fichiers / 1796+ tests à la clôture de SP-29b, en hausse ici) ; couverture ≥ 88.

- [ ] **Step 2: Suite E2E complète**

```bash
cd shell && npm run e2e
```

Expected: au moins 113 passed / 4 skipped / 0 failed (référence SP-30a) + les nouveaux tests de Task 6.

- [ ] **Step 3: Lint, format, build**

```bash
cd shell
npm run lint && npm run format:check
npm run build   # tsc --noEmit + vite build
```

Expected: 0 erreur. Le build confirme qu'aucun import résiduel vers `ui/dialog.tsx`/`ui/ConfirmDialog.tsx`/`ShareDialog.tsx` ne subsiste dans les fichiers touchés.

- [ ] **Step 4: Grep de garde — aucun ancien primitif dans les fichiers touchés par ce plan**

```bash
cd shell/src
grep -rn 'from "\.\./ui/button"\|from "\.\./ui/card"\|from "\.\./ui/dialog"\|from "\.\./ui/ConfirmDialog"\|ShareDialog' \
  pages/CatalogPage.tsx pages/ItemDetailPage.tsx shell/ItemActions.tsx ui/ItemCard.tsx ui/MetadataForm.tsx ui/ThumbnailUpload.tsx \
  || echo "OK — aucun ancien primitif"
```

Expected: `OK — aucun ancien primitif`.

- [ ] **Step 5: `uvx pre-commit run --all-files`**

```bash
cd /home/lenen/projets/geostudio && uvx pre-commit run --all-files
```

Expected: 5 hooks verts (commitlint ne sort qu'au commit — déjà vérifié à chaque Step de commit précédente).

- [ ] **Step 6: Pas de régénération OpenAPI attendue — vérifier que c'est bien le cas**

```bash
cd /home/lenen/projets/geostudio
git status --short core/openapi.json shell/src/api/generated/core-schema.d.ts
```

Expected: rien (aucun changement de schéma cœur dans ce plan). Si une différence apparaît, c'est un signal d'un changement non prévu à investiguer avant de continuer (pas un skip automatique — piège n°1).

- [ ] **Step 7: Revue finale de branche**

Suivre `superpowers:requesting-code-review` sur l'ensemble des commits de ce plan (Task 1 → 6). Porter une attention particulière (piège n°4, croisement entre tâches) à :
- La cohérence des trois messages `openError` (Task 5 Step 4) avec ce qu'affichait l'ancien code par route.
- Le fait que `ItemActions` (Task 3) est appelé à l'identique depuis `ItemCard` (grille, Task 5) et `ItemDetailPage` (fiche, Task 4) — vérifier qu'aucun des deux appelants ne suppose encore un comportement de dialogue inline.
- `-m-6` appliqué exactement une fois par page basculée (Task 4 et Task 5), jamais en double si un futur composant partagé les enveloppe à nouveau.

---

## 8. Dette assumée pour SP-30c+

- **`-m-6` sur `CatalogPage`/`ItemDetailPage`** : technique de transition documentée dans les Global Constraints, à retirer (avec le `p-6` global d'`AppLayout`) quand la dernière famille de pages aura basculé sur `TriptychLayout`.
- **Volet `browse` de `ItemDetailPage`** limité à un lien de retour + 2 faits — pas de mini-catalogue embarqué (la vraie cible du §3.8 du doc parent, « le catalogue est présent dans le volet gauche de chaque écran ») : cette capacité (recherche/liste compacte réutilisable dans le volet `browse` de *tous* les domaines) est un chantier transverse plus grand, hors périmètre d'une seule famille — à statuer explicitement avant SP-31/32/33 plutôt que redécouvert par surprise dans une future famille.
- **Volet `inspect` de `CatalogPage` sans sélection de ligne** : affiche un résumé global (compte + filtres actifs), pas la fiche d'un item survolé/sélectionné — délibérément, pour éviter d'introduire une sélection multi-lignes/master-detail non demandée par la spec SP-30 (réservée aux facettes/vues « nouveau » du doc parent, footnote ¹, SP-33). Si Tanguy veut cette interaction plus tôt, c'est un changement de spec, pas un oubli de ce plan.
- **13 Minor de la 1ʳᵉ passe de revue SP-30a** non énumérés dans le ledger consulté (`.superpowers/sdd/sp30a-progress.md`) restent à trier — consulter l'historique de revue complet (PR #102 ou équivalent) avant la famille SP-30c pour savoir combien sont Catalogue-scoped (aucun ne semble l'être d'après ce qui est documenté, mais le ledger ne liste que 4 des 17 Minor par leur texte).
