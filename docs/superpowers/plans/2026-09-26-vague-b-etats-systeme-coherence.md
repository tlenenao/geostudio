# Plan — Vague B : états système et cohérence

Source : `docs/superpowers/specs/2026-09-26-vague-b-etats-systeme-coherence-design.md`
(spec complète, 12 chantiers SP-B1→SP-B12). Précédent de forme :
`docs/superpowers/plans/2026-09-24-vague-a-bloquants-decouvrabilite.md`.

## Goal

Fermer les 12 chantiers de la Vague B du diagnostic UI/UX
(`docs/revue/2026-09-24-diagnostic-ui-ux.md`) : états vides, confirmations
de suppression, notifications de succès, résilience réseau (timeout +
bannière hors-ligne), erreurs serveur lisibles, indicateurs de chargement
uniformes, lisibilité des exécutions asynchrones (jobs/tuiles tronquées),
état UI synchronisé à l'URL, tableaux accessibles/cliquables, garde de
navigation sur brouillon non enregistré, et suppression des dernières
couleurs Tailwind brutes hors le kit et le thème d'app runtime.

## Architecture

Tout le travail est additif sur des patrons déjà en place dans le shell
(`ui/kit/*`, `api/domains/*.hooks.ts`, `i18n/catalog.fr.ts`) et une seule
route cœur (`core/app/features/tiles.py`, en-tête de réponse seulement, pas
de nouveau champ de schéma). Aucun nouveau service, aucune nouvelle table.

Deux systèmes de variables CSS distincts sont déjà en place et ne doivent
**pas** être confondus par le chantier SP-B12 : `--gs-*` (thème de chrome du
studio, `shell/src/styles/tokens.css`, consommé via les classes Tailwind
sémantiques littérales comme `text-ink`) et `--gs-color-*` (thème
personnalisable du **runtime d'app**, injecté dynamiquement par
`AppRenderer`, consommé via la syntaxe valeur-arbitraire
`text-[var(--gs-color-muted)]` dans les widgets `builder/widgets/*.tsx`).
Le balayage de couleurs brutes de SP-B12 ne doit toucher ni l'un ni l'autre
registre — seulement les couleurs Tailwind littérales (`text-red-600`,
`bg-slate-100`, etc.) qui ne sont ni l'un ni l'autre.

## Tech Stack

React 18, TypeScript, Vitest + Testing Library, React Query, Radix UI
(`@radix-ui/react-toast`), react-router-dom 6.30.4 (migration vers
`createBrowserRouter`/`RouterProvider` pour `useBlocker`), Playwright E2E,
FastAPI/SQLAlchemy côté cœur (une seule route touchée).

## Global Constraints

- TDD systématique : test rouge → implémentation minimale → test vert →
  commit, à chaque étape.
- Chaîne i18n française neuve ⇒ clé ajoutée à `shell/src/i18n/catalog.fr.ts`
  (convention `<domaine>.<intention>` camelCase), jamais de texte en dur
  dans un composant (`npm run lint` bloque le français en dur).
- Code/identifiants en anglais, prose de spec/commentaires en français
  quand le fichier voisin le fait déjà.
- Commits conventionnels, petits, un sujet, tous terminés par :
  `Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>`
- Seuils de couverture non régressifs (`shell/.coverage-threshold` = 88).
- Après toute tâche touchant une route/un modèle du cœur qui change la
  forme de l'OpenAPI : régénérer spec + types TS. La Tâche 13 (SP-B10,
  cœur) n'ajoute qu'un en-tête de réponse HTTP, aucune modification de
  schéma Pydantic ni de route — **pas de régénération nécessaire**,
  vérifié explicitement dans cette tâche.
- `core/tests/test_feature_inventory.py` exige une entrée
  `docs/revue/inventaire-fonctionnalites.jsonl` pour toute route
  REST/outil MCP/route shell **nouvelle**. Aucune tâche de ce plan
  n'ajoute une route, un outil MCP ou une route shell — toutes sont des
  modifications de comportement sur des surfaces déjà inventoriées. Pas
  de nouvelle entrée requise (revérifié Tâche 34).
- Falsifier tout filet de régression comportemental avant de le considérer
  acquis (piège n°10 CLAUDE.md) : injecter le défaut, constater l'échec,
  retirer.

## Ordre d'exécution

B1, B2, B3, B7, B5, B8, B4, B10, B9, B11, B6, B12 (ordre recommandé par la
spec — B7/B5 regroupés car ils touchent les mêmes 6 sites de fetch dans
`shell/src/api/base.ts`).

---

## Tâche 1 — SP-B1 : état vide du catalogue

**Files:**
- Modify: `shell/src/pages/CatalogPage.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/pages/CatalogPage.test.tsx`

**Interfaces:**
- Consumes: `EmptyState` (`shell/src/ui/kit/EmptyState.tsx`, existant —
  props `{title, description?, action?}`), `NewItemButton`
  (`shell/src/shell/NewItemButton.tsx`, autonome, prop `kind`).
- Produces: aucune nouvelle interface, remplace le rendu vide inline.

`CatalogPage.tsx` rend actuellement, quand la recherche ne trouve rien :

```tsx
{query.isSuccess && query.data.items.length === 0 && (
  <p className="text-sm text-ink-3">{t("catalog.empty")}</p>
)}
```

Deux cas sont confondus : catalogue vide (aucun item, jamais créé) et
recherche sans résultat (filtre actif). Le premier doit proposer une
action de création ; le second doit proposer de réinitialiser les filtres.

- [ ] **Step 1: Test rouge — catalogue vide sans filtre actif propose une action de création**

  Dans `CatalogPage.test.tsx`, ajouter (le fichier a déjà un rendu factice
  de `query`/`useItems` mocké — suivre le patron existant du fichier pour
  le mock de `useItems`) :

  ```tsx
  it("propose de créer un item quand le catalogue est vide sans filtre", async () => {
    mockUseItems.mockReturnValue({
      isSuccess: true,
      data: { items: [], total: 0 },
    } as never);
    render(<CatalogPage />, { wrapper });
    expect(await screen.findByText(t("catalog.emptyNoFilterTitle"))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t("newItem.trigger") })).toBeInTheDocument();
  });

  it("propose de réinitialiser les filtres quand la recherche ne trouve rien", async () => {
    mockUseItems.mockReturnValue({
      isSuccess: true,
      data: { items: [], total: 0 },
    } as never);
    render(<CatalogPage />, { wrapper });
    const search = screen.getByRole("searchbox");
    await userEvent.type(search, "zzz-introuvable");
    expect(await screen.findByText(t("catalog.emptyFilteredTitle"))).toBeInTheDocument();
    expect(screen.getByRole("button", { name: t("catalog.resetFilters") })).toBeInTheDocument();
  });
  ```

  Adapter les noms de mock (`mockUseItems`, `wrapper`) à ceux réellement
  déclarés en tête du fichier de test existant.

  Run: `cd shell && npx vitest run src/pages/CatalogPage.test.tsx`
  Expected: 2 échecs (`emptyNoFilterTitle`/`emptyFilteredTitle` absents de
  `catalog.fr.ts`, bouton de reset absent).

- [ ] **Step 2: Clés i18n**

  Dans `shell/src/i18n/catalog.fr.ts`, ajouter (respecter l'ordre
  alphabétique local existant sous le préfixe `catalog.`) :

  ```ts
  "catalog.emptyNoFilterTitle": "Aucun élément pour l'instant",
  "catalog.emptyNoFilterDescription": "Créez votre première carte, appli ou jeu de données pour commencer.",
  "catalog.emptyFilteredTitle": "Aucun résultat",
  "catalog.emptyFilteredDescription": "Aucun élément ne correspond à ces filtres.",
  "catalog.resetFilters": "Réinitialiser les filtres",
  ```

  Retirer l'ancienne clé `catalog.empty` de `catalog.fr.ts` seulement après
  avoir confirmé (grep) qu'aucun autre fichier ne la consomme.

  Run: `cd shell && grep -rn '"catalog.empty"' src/`
  Expected: aucune occurrence hors le fichier de catalogue lui-même après
  l'étape 3.

- [ ] **Step 3: Implémentation — deux variantes d'état vide**

  Dans `CatalogPage.tsx`, remplacer le bloc `<p>` vide par (le composant a
  déjà accès à `q`, `ownerFilter`, `selectedKeywords`, `spatialBbox`,
  `setSearchParams` d'après le fichier existant) :

  ```tsx
  {query.isSuccess && query.data.items.length === 0 && (() => {
    const hasActiveFilter =
      q.length > 0 || ownerFilter.length > 0 || selectedKeywords.length > 0 || spatialBbox !== null;
    if (hasActiveFilter) {
      return (
        <EmptyState
          title={t("catalog.emptyFilteredTitle")}
          description={t("catalog.emptyFilteredDescription")}
          action={
            <Button
              variant="outline"
              onClick={() => {
                setSearchParams({});
                setSpatialBbox(null);
              }}
            >
              {t("catalog.resetFilters")}
            </Button>
          }
        />
      );
    }
    return (
      <EmptyState
        title={t("catalog.emptyNoFilterTitle")}
        description={t("catalog.emptyNoFilterDescription")}
        action={<NewItemButton />}
      />
    );
  })()}
  ```

  Ajouter les imports `EmptyState`, `NewItemButton`, `Button` en tête de
  fichier s'ils n'y sont pas déjà (vérifier — `Button` l'est déjà d'après
  le grep de grounding). Vérifier la prop réelle de reset de
  `spatialBbox` (`setSpatialBbox` ou équivalent) dans le fichier avant
  d'écrire l'appel — utiliser le nom exact trouvé.

  Run: `cd shell && npx vitest run src/pages/CatalogPage.test.tsx`
  Expected: 2 tests passent.

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/pages/CatalogPage.tsx shell/src/pages/CatalogPage.test.tsx shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): distingue catalogue vide et recherche sans résultat

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 2 — SP-B1 : état vide des 4 pages d'administration en table

**Files:**
- Modify: `shell/src/pages/HarvestSourcesAdminPage.tsx`
- Modify: `shell/src/pages/RolesAdminPage.tsx`
- Modify: `shell/src/pages/UsersAdminPage.tsx`
- Modify: `shell/src/pages/CollectionsAdminPage.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/pages/HarvestSourcesAdminPage.test.tsx`,
  `shell/src/pages/RolesAdminPage.test.tsx`,
  `shell/src/pages/UsersAdminPage.test.tsx`,
  `shell/src/pages/CollectionsAdminPage.test.tsx`

**Interfaces:**
- Consumes: `EmptyState` (idem Tâche 1).
- Produces: rien de nouveau.

Les 4 pages n'ont aucun garde `length === 0` — grounding confirmé (grep) :
le tableau rend juste une ligne d'en-tête quand la liste est vide, sans
aucun message. Patron de référence déjà en place dans `UsagePage.tsx` :

```tsx
{tasksQuery.data && tasksQuery.data.total === 0 && (<EmptyState title={t("usage.noTasks")} />)}
```

- [ ] **Step 1: Test rouge sur les 4 pages**

  Pour chacune des 4 pages, dans son fichier de test, ajouter un test qui
  mocke la liste vide et vérifie l'apparition d'un `EmptyState` (titre
  précis par page) au lieu du tableau. Exemple pour
  `RolesAdminPage.test.tsx` (adapter le nom du hook mocké — `useRoles` ou
  équivalent trouvé en tête du fichier réel) :

  ```tsx
  it("affiche un état vide quand aucun rôle n'existe", async () => {
    mockUseRoles.mockReturnValue({ isSuccess: true, data: [] } as never);
    render(<RolesAdminPage />, { wrapper });
    expect(await screen.findByText(t("rolesAdmin.empty"))).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
  ```

  Répéter pour `HarvestSourcesAdminPage` (`harvestAdmin.empty`),
  `UsersAdminPage` (`usersAdmin.empty`), `CollectionsAdminPage`
  (`collectionsAdmin.empty`) avec les noms de hooks réels de chaque
  fichier (à vérifier par lecture avant d'écrire le test, chaque page a sa
  propre convention de nommage de query).

  Run: `cd shell && npx vitest run src/pages/RolesAdminPage.test.tsx src/pages/HarvestSourcesAdminPage.test.tsx src/pages/UsersAdminPage.test.tsx src/pages/CollectionsAdminPage.test.tsx`
  Expected: 4 échecs (clé i18n absente, aucun `EmptyState` rendu).

- [ ] **Step 2: Clés i18n**

  ```ts
  "rolesAdmin.empty": "Aucun rôle personnalisé pour l'instant",
  "harvestAdmin.empty": "Aucune source de moissonnage configurée",
  "usersAdmin.empty": "Aucun utilisateur ne correspond à cette recherche",
  "collectionsAdmin.empty": "Aucune collection pour l'instant",
  ```

- [ ] **Step 3: Implémentation dans les 4 pages**

  Dans chaque page, entourer le rendu du `<table>` d'une condition
  miroir de celle d'`UsagePage.tsx` : si la liste chargée est vide,
  rendre `<EmptyState title={t("<page>.empty")} />` à la place du
  tableau (garder le tableau seulement quand `data.length > 0`). Ajouter
  l'import `EmptyState` dans les 4 fichiers.

  Run: (même commande que Step 1)
  Expected: 4 tests passent, suite complète de chaque fichier toujours
  verte (`npx vitest run <fichier>` sans filtre de nom).

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/pages/HarvestSourcesAdminPage.tsx shell/src/pages/RolesAdminPage.tsx \
    shell/src/pages/UsersAdminPage.tsx shell/src/pages/CollectionsAdminPage.tsx \
    shell/src/pages/HarvestSourcesAdminPage.test.tsx shell/src/pages/RolesAdminPage.test.tsx \
    shell/src/pages/UsersAdminPage.test.tsx shell/src/pages/CollectionsAdminPage.test.tsx \
    shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): état vide sur les 4 pages d'administration en table

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 3 — SP-B2 : `ConfirmDialog` sur les 3 `window.confirm` restants + suppression de pièce jointe

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx`
- Modify: `shell/src/builder/ConfigHistoryPanel.tsx`
- Modify: `shell/src/map/MapSymbologyEditor.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/widgets/form.test.tsx`,
  `shell/src/builder/ConfigHistoryPanel.test.tsx`,
  `shell/src/map/MapSymbologyEditor.test.tsx`

**Interfaces:**
- Consumes: `ConfirmDialog` (`shell/src/ui/kit/ConfirmDialog.tsx`, props
  `{open, title, message, confirmLabel, onConfirm, onCancel, pending?}`).
- Produces: rien de nouveau.

4 sites au total : 3 `window.confirm()` existants (rollback de config,
suppression d'icône de symbologie, suppression d'enregistrement de
formulaire) + 1 suppression de pièce jointe sans confirmation du tout
(`AttachmentFieldInput.handleDelete`, `form.tsx`).

- [ ] **Step 1: Test rouge — `ConfigHistoryPanel`**

  `ConfigHistoryPanel.test.tsx` ligne ~71 asserte aujourd'hui
  `expect(window.confirm).toHaveBeenCalled()`. Remplacer par un test qui
  ouvre le `ConfirmDialog` et clique sur confirmer :

  ```tsx
  it("demande confirmation via ConfirmDialog avant de restaurer une version", async () => {
    render(<ConfigHistoryPanel {...props} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: /restaurer/i }));
    expect(screen.getByRole("dialog")).toHaveTextContent(
      t("configHistory.confirmMessage", { version: props.versions[0].version }),
    );
    await userEvent.click(screen.getByRole("button", { name: t("confirmDialog.confirm") }));
    expect(mockRollback).toHaveBeenCalledWith(props.pk, props.versions[0].version);
  });
  ```

  Retirer le mock global de `window.confirm` de ce fichier de test s'il
  n'est plus utilisé ailleurs dans le fichier (vérifier).

  Run: `cd shell && npx vitest run src/builder/ConfigHistoryPanel.test.tsx`
  Expected: échec (pas de `role="dialog"`, `restore()` appelle encore
  `window.confirm`).

- [ ] **Step 2: Implémentation — `ConfigHistoryPanel`**

  Remplacer l'appel direct `restore(version)` par un état
  `pendingVersion: number | null`, ouvrir `ConfirmDialog` quand non-null,
  déplacer l'appel réel (`client.rollbackConfig` + invalidation) dans
  `onConfirm`. Ajouter le rendu `<ConfirmDialog open={pendingVersion !== null} title={t("configHistory.confirmTitle")} message={t("configHistory.confirmMessage", {version: pendingVersion ?? 0})} confirmLabel={t("actions.restore")} onCancel={() => setPendingVersion(null)} onConfirm={() => void doRestore(pendingVersion!)} />` en fin de composant. Ajouter clé
  `"configHistory.confirmTitle": "Restaurer cette version ?"` et
  `"actions.restore": "Restaurer"` si absentes (vérifier avant d'ajouter,
  `actions.restore` peut déjà exister ailleurs — grep avant écriture).

  Run: (même commande) — Expected: passe.

- [ ] **Step 3: Test rouge + implémentation — `MapSymbologyEditor` (suppression d'icône)**

  Même patron : le site est `mapSymbology.deleteIconConfirm` (ligne ~697).
  Ajouter un test analogue dans `MapSymbologyEditor.test.tsx` (ouvrir le
  panneau d'icônes, cliquer supprimer, vérifier le dialogue, confirmer),
  puis remplacer le `window.confirm` par le même patron d'état
  `pendingIconId` + `ConfirmDialog`.

  Run: `cd shell && npx vitest run src/map/MapSymbologyEditor.test.tsx`
  Expected: rouge puis vert.

- [ ] **Step 4: Test rouge + implémentation — `form.tsx` suppression d'enregistrement**

  Site : `FormComponent.handleDelete` (ligne ~510-524),
  `window.confirm(t("widgetForm.confirmDelete"))`. Ajouter un test dans
  `form.test.tsx` qui ouvre le formulaire en mode édition, clique
  "Supprimer", vérifie `ConfirmDialog`, confirme, vérifie
  `remove.mutateAsync` appelé. Implémentation : état
  `confirmingDelete: boolean`, `ConfirmDialog` rendu conditionnellement,
  logique de `handleDelete` (mutation + invalidation + emit + reset)
  déplacée dans `onConfirm`.

  Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
  Expected: rouge puis vert.

- [ ] **Step 5: Test rouge + implémentation — `AttachmentFieldInput` (aucune confirmation actuellement)**

  `handleDelete(attachmentId)` (form.tsx, ~ligne 292-296) appelle
  aujourd'hui `client.deleteAttachment` directement, sans confirmation —
  c'est un vrai gap, pas une migration de `window.confirm`. Ajouter un
  test dans `form.test.tsx` : cliquer le bouton de suppression d'une
  pièce jointe listée doit ouvrir un `ConfirmDialog` nommant
  `a.filename`, et ne PAS appeler `deleteAttachment` avant confirmation :

  ```tsx
  it("demande confirmation avant de supprimer une pièce jointe", async () => {
    render(<AttachmentFieldInput {...props} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: t("attachments.deleteAria", { filename: "plan.pdf" }) }));
    expect(mockDeleteAttachment).not.toHaveBeenCalled();
    expect(screen.getByRole("dialog")).toHaveTextContent(
      t("attachments.confirmDeleteMessage", { filename: "plan.pdf" }),
    );
    await userEvent.click(screen.getByRole("button", { name: t("confirmDialog.confirm") }));
    expect(mockDeleteAttachment).toHaveBeenCalledWith("att-1");
  });
  ```

  Implémentation : état `pendingDeleteId: string | null` dans
  `AttachmentFieldInput`, le bouton de suppression (ligne ~326-333) fixe
  `pendingDeleteId` au lieu d'appeler `handleDelete` directement,
  `ConfirmDialog` rendu en fin de composant avec `onConfirm={() => { void handleDelete(pendingDeleteId!); setPendingDeleteId(null); }}`.
  Ajouter clés `"attachments.confirmDeleteMessage": "Supprimer la pièce jointe « {filename} » ?"`
  et `"attachments.deleteAria": "Supprimer {filename}"` (vérifier si
  `attachments.deleteAria` existe déjà — sinon créer).

  Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
  Expected: rouge puis vert, suite complète du fichier toujours verte.

- [ ] **Step 6: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/builder/widgets/form.tsx shell/src/builder/widgets/form.test.tsx \
    shell/src/builder/ConfigHistoryPanel.tsx shell/src/builder/ConfigHistoryPanel.test.tsx \
    shell/src/map/MapSymbologyEditor.tsx shell/src/map/MapSymbologyEditor.test.tsx \
    shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  fix(shell): remplace window.confirm par ConfirmDialog, garde la suppression de pièce jointe

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 4 — SP-B3 : `ToastProvider` + `useToast` + montage

**Files:**
- Create: `shell/src/ui/kit/ToastProvider.tsx`
- Modify: `shell/src/App.tsx`
- Modify: `shell/src/ui/kit/index.ts`
- Test: `shell/src/ui/kit/ToastProvider.test.tsx`

**Interfaces:**
- Consumes: `@radix-ui/react-toast` primitives (déjà une dépendance,
  utilisées directement par `ui/kit/Toast.tsx`).
- Produces: `useToast(): { showToast: (message: string, options?: { variant?: "success" | "error" }) => void }`,
  exporté depuis `ui/kit/ToastProvider.tsx` et re-exporté par
  `ui/kit/index.ts`. Consommé par les Tâches 5 et 6.

`ui/kit/Toast.tsx` existant est purement contrôlé (`open`/`onOpenChange`),
sans contexte. `App.tsx` monte déjà `<ToastPrimitive.Provider>` (ligne 46)
et un `<ToastPrimitive.Viewport>` (ligne 58) — mais rien ne pousse de
toast dedans aujourd'hui. `ToastProvider` ajoute la pièce manquante :
un contexte React qui gère une file de toasts et les rend via les mêmes
primitives Radix déjà montées, pour éviter un deuxième `Viewport`.

- [ ] **Step 1: Test rouge — `useToast` hors provider lève, un composant enfant peut pousser un toast visible**

  ```tsx
  // shell/src/ui/kit/ToastProvider.test.tsx
  import { render, screen } from "@testing-library/react";
  import userEvent from "@testing-library/user-event";
  import { describe, expect, it } from "vitest";
  import * as ToastPrimitive from "@radix-ui/react-toast";
  import { ToastProvider, useToast } from "./ToastProvider";

  function Trigger() {
    const { showToast } = useToast();
    return <button onClick={() => showToast("Enregistré")}>déclencher</button>;
  }

  function renderWithProvider() {
    return render(
      <ToastPrimitive.Provider>
        <ToastProvider>
          <Trigger />
        </ToastProvider>
        <ToastPrimitive.Viewport />
      </ToastPrimitive.Provider>,
    );
  }

  describe("ToastProvider", () => {
    it("affiche un toast poussé par un descendant", async () => {
      renderWithProvider();
      await userEvent.click(screen.getByRole("button", { name: "déclencher" }));
      expect(await screen.findByText("Enregistré")).toBeInTheDocument();
    });

    it("affiche un toast d'erreur avec le rôle alert", async () => {
      function ErrorTrigger() {
        const { showToast } = useToast();
        return <button onClick={() => showToast("Échec", { variant: "error" })}>err</button>;
      }
      render(
        <ToastPrimitive.Provider>
          <ToastProvider>
            <ErrorTrigger />
          </ToastProvider>
          <ToastPrimitive.Viewport />
        </ToastPrimitive.Provider>,
      );
      await userEvent.click(screen.getByRole("button", { name: "err" }));
      expect(await screen.findByRole("alert")).toHaveTextContent("Échec");
    });
  });
  ```

  Run: `cd shell && npx vitest run src/ui/kit/ToastProvider.test.tsx`
  Expected: échec de résolution de module (`./ToastProvider` n'existe pas).

- [ ] **Step 2: Implémentation**

  ```tsx
  // shell/src/ui/kit/ToastProvider.tsx
  // SPDX-License-Identifier: Apache-2.0
  import { createContext, useCallback, useContext, useState, type ReactNode } from "react";
  import * as ToastPrimitive from "@radix-ui/react-toast";

  type ToastVariant = "success" | "error";
  type ToastEntry = { id: string; message: string; variant: ToastVariant };

  type ToastContextValue = {
    showToast: (message: string, options?: { variant?: ToastVariant }) => void;
  };

  const ToastContext = createContext<ToastContextValue | null>(null);

  export function useToast(): ToastContextValue {
    const ctx = useContext(ToastContext);
    if (!ctx) {
      throw new Error("useToast doit être utilisé sous ToastProvider");
    }
    return ctx;
  }

  export function ToastProvider({ children }: { children: ReactNode }) {
    const [toasts, setToasts] = useState<ToastEntry[]>([]);

    const showToast = useCallback((message: string, options?: { variant?: ToastVariant }) => {
      const id = crypto.randomUUID();
      const variant = options?.variant ?? "success";
      setToasts((prev) => [...prev, { id, message, variant }]);
    }, []);

    const dismiss = useCallback((id: string) => {
      setToasts((prev) => prev.filter((toast) => toast.id !== id));
    }, []);

    return (
      <ToastContext.Provider value={{ showToast }}>
        {children}
        {toasts.map((toast) => (
          <ToastPrimitive.Root
            key={toast.id}
            duration={4000}
            onOpenChange={(open) => {
              if (!open) dismiss(toast.id);
            }}
            role={toast.variant === "error" ? "alert" : "status"}
            className={
              toast.variant === "error"
                ? "rounded-md border border-danger bg-surface px-4 py-3 text-sm text-danger shadow-md"
                : "rounded-md border border-rule bg-surface px-4 py-3 text-sm text-ink shadow-md"
            }
          >
            <ToastPrimitive.Description>{toast.message}</ToastPrimitive.Description>
          </ToastPrimitive.Root>
        ))}
      </ToastContext.Provider>
    );
  }
  ```

  Vérifier dans `styles/tokens.css` que `--gs-danger`/`--gs-surface`/
  `--gs-rule`/`--gs-ink` existent bien (confirmé en grounding) avant
  d'utiliser les classes `bg-surface`/`text-danger`/`border-rule`/`text-ink`.

  Run: (même commande) — Expected: 2 tests passent.

- [ ] **Step 3: Montage dans `App.tsx`**

  `App.tsx` monte aujourd'hui, dans cet ordre (ligne 44-61) :
  `<ToastPrimitive.Provider>` → `<TooltipPrimitive.Provider>` →
  `<AppErrorBoundary>` → `<AuthProvider>` → `<QueryClientProvider>` →
  `<ConfigProvider>` → `<AppShell/>`, avec `<ToastPrimitive.Viewport>`
  comme frère après `</TooltipPrimitive.Provider>`. Insérer
  `<ToastProvider>` juste à l'intérieur de `<ToastPrimitive.Provider>`,
  en l'englobant autour de tout le reste (pour que tout composant sous
  `AppShell` puisse appeler `useToast()`) :

  ```tsx
  <ToastPrimitive.Provider>
    <ToastProvider>
      <TooltipPrimitive.Provider>
        <AppErrorBoundary>
          <AuthProvider>
            <QueryClientProvider client={queryClient}>
              <ConfigProvider>
                <AppShell />
              </ConfigProvider>
            </QueryClientProvider>
          </AuthProvider>
        </AppErrorBoundary>
      </TooltipPrimitive.Provider>
    </ToastProvider>
    <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2 outline-none" />
  </ToastPrimitive.Provider>
  ```

  Réindenter le JSX existant en conséquence (pas de changement de logique,
  seulement l'ajout d'un niveau d'enrobage).

- [ ] **Step 4: Export**

  Ajouter dans `shell/src/ui/kit/index.ts` :
  `export { ToastProvider, useToast } from "./ToastProvider";`

  Run: `cd shell && npx vitest run src/ui/kit/ToastProvider.test.tsx src/App.test.tsx`
  Expected: tout vert (vérifier que `App.test.tsx` existe et rend
  toujours sans throw — sinon lancer la suite du dossier `src/` ciblant
  App).

- [ ] **Step 5: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/ui/kit/ToastProvider.tsx shell/src/ui/kit/ToastProvider.test.tsx \
    shell/src/ui/kit/index.ts shell/src/App.tsx
  git commit -m "$(cat <<'EOF'
  feat(shell): ajoute ToastProvider/useToast, monté globalement dans App

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 5 — SP-B3 : notifications de succès sur les sauvegardes Carte/Dataset/App

**Files:**
- Modify: `shell/src/api/domains/layers.hooks.ts`
- Modify: `shell/src/api/domains/datasets.hooks.ts`
- Modify: `shell/src/api/domains/apps.hooks.ts`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/api/domains/layers.hooks.test.ts` (et équivalents
  datasets/apps s'ils existent déjà — sinon les créer sur le même patron)

**Interfaces:**
- Consumes: `useToast` (Tâche 4).
- Produces: rien de nouveau (comportement additif sur des hooks existants).

Un hook React ne peut pas appeler `useToast()` lui-même s'il n'est pas un
composant — mais `useSaveMap`/`useSaveDataset`/`useSaveApp` SONT des hooks
(`useMutation` interne), donc ils peuvent appeler `useToast()` directement
en tête de leur propre corps de hook.

- [ ] **Step 1: Test rouge — `useSaveMap` déclenche un toast de succès**

  Créer/étendre `layers.hooks.test.ts` avec un test qui enrobe le
  renderHook dans `<ToastPrimitive.Provider><ToastProvider>...` (voir
  patron Tâche 4) et vérifie que le toast apparaît après `mutateAsync` :

  ```tsx
  it("useSaveMap affiche un toast de succès après sauvegarde", async () => {
    const { result } = renderHook(() => useSaveMap("map-1"), { wrapper: ToastWrapper });
    await act(async () => {
      await result.current.mutateAsync(fakeMapConfig);
    });
    expect(await screen.findByText(t("toast.mapSaved"))).toBeInTheDocument();
  });
  ```

  `ToastWrapper` : composant local du fichier de test qui combine
  `QueryClientProvider` (déjà nécessaire pour `useMutation`) +
  `ToastPrimitive.Provider` + `ToastProvider` + `ToastPrimitive.Viewport`.

  Run: `cd shell && npx vitest run src/api/domains/layers.hooks.test.ts`
  Expected: échec (`toast.mapSaved` absent, pas de toast affiché).

- [ ] **Step 2: Clé i18n + implémentation `useSaveMap`**

  ```ts
  "toast.mapSaved": "Carte enregistrée",
  ```

  ```ts
  export function useSaveMap(pk: string) {
    const client = useItemClientInternal();
    const queryClient = useQueryClient();
    const { showToast } = useToast();
    return useMutation({
      mutationFn: (config: MapConfig) => client.saveMapConfig(pk, config),
      onSuccess: () => {
        void queryClient.invalidateQueries({ queryKey: ["map", pk] });
        void queryClient.invalidateQueries({ queryKey: ["item", pk] });
        showToast(t("toast.mapSaved"));
      },
    });
  }
  ```

  Ajouter `import { useToast } from "../../ui/kit/ToastProvider";` et
  `import { t } from "../../i18n";` en tête de `layers.hooks.ts` (vérifier
  si `t` y est déjà importé — le fichier grounded ne l'importait pas).

  Run: (même commande) — Expected: passe.

- [ ] **Step 3: Répéter pour `useSaveDataset` et `useSaveApp`**

  Même patron exact : test rouge (`toast.datasetSaved`/`toast.appSaved`)
  puis `showToast(...)` dans `onSuccess`, dans
  `datasets.hooks.ts`/`apps.hooks.ts`. Confirmer par lecture le nom exact
  du hook de sauvegarde dans chacun de ces 2 fichiers avant d'écrire
  (grounding confirme leur existence mais pas leur nom exact au-delà de
  `useSaveDataset`/`useSaveApp` déjà cités dans le commentaire de
  `layers.hooks.ts` ligne 51-58).

  Run: `cd shell && npx vitest run src/api/domains/datasets.hooks.test.ts src/api/domains/apps.hooks.test.ts`
  Expected: rouge puis vert pour chacun.

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/api/domains/layers.hooks.ts shell/src/api/domains/datasets.hooks.ts \
    shell/src/api/domains/apps.hooks.ts shell/src/i18n/catalog.fr.ts \
    shell/src/api/domains/layers.hooks.test.ts shell/src/api/domains/datasets.hooks.test.ts \
    shell/src/api/domains/apps.hooks.test.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): notification de succès sur la sauvegarde carte/dataset/app

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 6 — SP-B3 : notifications de succès Pipeline/Rapport + webhook

**Files:**
- Modify: `shell/src/api/domains/pipelines.hooks.ts`
- Modify: `shell/src/api/domains/reports.hooks.ts`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/api/domains/pipelines.hooks.test.ts`,
  `shell/src/api/domains/reports.hooks.test.ts`

**Interfaces:**
- Consumes: `useToast` (Tâche 4).
- Produces: rien de nouveau.

Même patron que la Tâche 5, appliqué à `useCreatePipeline`/
`useSavePipeline`/`useCreatePipelineWebhookToken`/
`useRevokePipelineWebhookToken` et `useCreateReportSchedule`/
`useSaveReportSchedule`.

- [ ] **Step 1: Tests rouges** — un test par mutation ciblée (6 mutations
  au total), vérifiant l'apparition du toast attendu après succès,
  suivant exactement le patron de la Tâche 5 Step 1.

  Run: `cd shell && npx vitest run src/api/domains/pipelines.hooks.test.ts src/api/domains/reports.hooks.test.ts`
  Expected: échecs sur les clés i18n manquantes.

- [ ] **Step 2: Clés i18n**

  ```ts
  "toast.pipelineCreated": "Pipeline créé",
  "toast.pipelineSaved": "Pipeline enregistré",
  "toast.webhookTokenCreated": "Jeton de webhook créé",
  "toast.webhookTokenRevoked": "Jeton de webhook révoqué",
  "toast.reportScheduleCreated": "Rapport planifié créé",
  "toast.reportScheduleSaved": "Rapport planifié enregistré",
  ```

- [ ] **Step 3: Implémentation** — ajouter `showToast(...)` dans le
  `onSuccess` de chacune des 6 mutations, sans changer leur logique
  d'invalidation de cache existante.

  Run: (même commande Step 1) — Expected: tout vert.

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/api/domains/pipelines.hooks.ts shell/src/api/domains/reports.hooks.ts \
    shell/src/api/domains/pipelines.hooks.test.ts shell/src/api/domains/reports.hooks.test.ts \
    shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): notification de succès sur pipeline/rapport/webhook

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 7 — SP-B7 : timeout réseau + bannière hors-ligne

**Files:**
- Modify: `shell/src/api/base.ts`
- Create: `shell/src/api/CoreUnreachableError.ts`
- Modify: `shell/src/App.tsx`
- Create: `shell/src/shell/ConnectivityBanner.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/api/base.test.ts`, `shell/src/shell/ConnectivityBanner.test.tsx`,
  `shell/src/App.test.tsx`

**Interfaces:**
- Produces: `class CoreUnreachableError extends Error` (exporté depuis
  `api/CoreUnreachableError.ts`), consommé par la Tâche 8 (`ApiError`
  distingue une vraie erreur serveur d'une injoignabilité réseau) et par
  `ConnectivityBanner`.
- Consumes: rien de nouveau — enrobe les 6 sites `fetch()` déjà identifiés
  dans `base.ts` (`requestBlob`, `request`, `fetchGeoJsonFeatures`,
  `fetchCoreCollections`, `fetchExternalRasterSources`,
  `fetchHostedTileset3dSources`, `fetchHostedTerrain3dSources` — 7 sites
  au total, pas 6 ; le décompte de grounding en listait 6 dans le corps de
  `createBase()` plus `requestBlob` en dehors, soit 7 réellement).

- [ ] **Step 1: `CoreUnreachableError`**

  ```ts
  // shell/src/api/CoreUnreachableError.ts
  // SPDX-License-Identifier: Apache-2.0
  export class CoreUnreachableError extends Error {
    constructor(cause?: unknown) {
      super("Le cœur GeoStudio est injoignable");
      this.name = "CoreUnreachableError";
      this.cause = cause;
    }
  }
  ```

  Pas de test dédié — classe triviale, testée par ses consommateurs.

- [ ] **Step 2: Test rouge — `request()` transforme un timeout/échec réseau en `CoreUnreachableError`**

  Dans `base.test.ts` :

  ```ts
  it("transforme un fetch qui rejette (réseau coupé) en CoreUnreachableError", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    const base = createBase({ getCoreUrl: () => "http://core.test", getAccessToken: () => undefined });
    await expect(base.request("/v1/items")).rejects.toThrow(CoreUnreachableError);
  });

  it("applique un timeout de 15s sur toute requête", async () => {
    const fetchSpy = vi.fn().mockImplementation((_url, init: RequestInit) => {
      expect(init.signal).toBeInstanceOf(AbortSignal);
      return Promise.resolve(new Response("{}", { status: 200 }));
    });
    vi.stubGlobal("fetch", fetchSpy);
    const base = createBase({ getCoreUrl: () => "http://core.test", getAccessToken: () => undefined });
    await base.request("/v1/items");
    expect(fetchSpy).toHaveBeenCalled();
  });
  ```

  Run: `cd shell && npx vitest run src/api/base.test.ts`
  Expected: 1er test échoue (rejette avec `TypeError` brute, pas
  `CoreUnreachableError`) ; 2e peut déjà passer si `AbortSignal` est déjà
  ailleurs — vérifier, sinon échec aussi.

- [ ] **Step 3: Implémentation — enrober les 7 sites de fetch**

  Ajouter en tête de `base.ts` :

  ```ts
  import { CoreUnreachableError } from "./CoreUnreachableError";

  const DEFAULT_TIMEOUT_MS = 15_000;

  async function fetchWithTimeout(input: string, init: RequestInit = {}): Promise<Response> {
    try {
      return await fetch(input, { ...init, signal: AbortSignal.timeout(DEFAULT_TIMEOUT_MS) });
    } catch (err) {
      throw new CoreUnreachableError(err);
    }
  }
  ```

  Remplacer chacun des 7 appels `fetch(...)` directs (`requestBlob` L162,
  `request` L197, `fetchGeoJsonFeatures` L271, `fetchCoreCollections` L290,
  `fetchExternalRasterSources` L320, `fetchHostedTileset3dSources` L340,
  `fetchHostedTerrain3dSources` L358) par `fetchWithTimeout(...)`, en
  conservant exactement les mêmes arguments d'URL/`init` déjà construits à
  chaque site. Ne pas enrober l'`AbortSignal` existant s'il y en a déjà un
  pour un site donné — combiner avec `AbortSignal.any([...])` si un signal
  d'annulation existant est déjà passé (vérifier chaque site
  individuellement avant d'écrire, ne pas supposer qu'aucun n'en a).

  Run: `cd shell && npx vitest run src/api/base.test.ts`
  Expected: 2 tests passent, suite complète de `base.test.ts` toujours
  verte.

- [ ] **Step 4: `ConnectivityBanner`**

  Composant qui écoute une invalidation React Query globale : au lieu
  d'un `navigator.onLine`, s'appuie sur le comptage d'erreurs `CoreUnreachableError`
  vues par le `QueryClient` (plus fiable qu'un événement navigateur qui ne
  détecte pas un cœur down avec réseau local up). Utiliser
  `queryClient.getQueryCache().subscribe(...)` :

  ```tsx
  // shell/src/shell/ConnectivityBanner.tsx
  // SPDX-License-Identifier: Apache-2.0
  import { useEffect, useState } from "react";
  import { useQueryClient } from "@tanstack/react-query";
  import { CoreUnreachableError } from "../api/CoreUnreachableError";
  import { t } from "../i18n";

  export function ConnectivityBanner() {
    const queryClient = useQueryClient();
    const [unreachable, setUnreachable] = useState(false);

    useEffect(() => {
      const unsubscribe = queryClient.getQueryCache().subscribe((event) => {
        if (event.type !== "updated") return;
        const query = event.query;
        if (query.state.status === "error" && query.state.error instanceof CoreUnreachableError) {
          setUnreachable(true);
        } else if (query.state.status === "success") {
          setUnreachable(false);
        }
      });
      return unsubscribe;
    }, [queryClient]);

    if (!unreachable) return null;
    return (
      <div role="alert" className="w-full bg-danger-soft px-4 py-2 text-center text-sm text-danger">
        {t("connectivity.unreachable")}
      </div>
    );
  }
  ```

  Test rouge d'abord dans `ConnectivityBanner.test.tsx` : rendre le
  composant sous un `QueryClientProvider`, lancer une query qui rejette
  avec `CoreUnreachableError`, vérifier l'apparition du `role="alert"`,
  puis une query qui réussit, vérifier sa disparition.

  Clé i18n : `"connectivity.unreachable": "Connexion au serveur perdue — nouvelle tentative en cours…"`.

  Run: `cd shell && npx vitest run src/shell/ConnectivityBanner.test.tsx`
  Expected: rouge (fichier absent) puis vert.

- [ ] **Step 5: Montage dans `App.tsx`**

  Ajouter `<ConnectivityBanner />` juste avant `<AppShell />` (à
  l'intérieur de `<ConfigProvider>`, pour avoir accès au `QueryClient`
  déjà fourni par `<QueryClientProvider>` un niveau au-dessus).

  Run: `cd shell && npx vitest run src/App.test.tsx`
  Expected: vert (pas de nouvelle assertion requise dans ce fichier, juste
  pas de régression).

- [ ] **Step 6: Borner le retry par défaut de `QueryClient`**

  Sans ce réglage, le timeout de 15s (Step 3) se multiplie par le retry
  par défaut de React Query (3×, backoff exponentiel) avant qu'une query
  ne se stabilise en erreur — la `ConnectivityBanner` mettrait ~45s+ à
  apparaître sur une vraie panne cœur, contre l'intention de la spec
  SP-B7. `App.tsx:23` construit aujourd'hui `new QueryClient()` sans
  `defaultOptions`. Remplacer par :

  ```ts
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1 } } });
  ```

  Test rouge d'abord dans `App.test.tsx` (ou un test dédié si ce fichier
  ne rend pas facilement le `QueryClient` construit — vérifier le patron
  existant du fichier avant d'écrire) : simuler une query qui échoue et
  vérifier qu'elle se stabilise en erreur après au plus 1 nouvelle
  tentative (2 appels `fetch` au total), pas 4 (le comportement par
  défaut de React Query).

  Run: `cd shell && npx vitest run src/App.test.tsx`
  Expected: rouge (retry par défaut à 3, donc 4 appels) puis vert après
  le changement.

- [ ] **Step 7: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/api/base.ts shell/src/api/base.test.ts shell/src/api/CoreUnreachableError.ts \
    shell/src/shell/ConnectivityBanner.tsx shell/src/shell/ConnectivityBanner.test.tsx \
    shell/src/App.tsx shell/src/App.test.tsx shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): timeout de 15s sur les requêtes cœur, bannière de connectivité

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 8 — SP-B5 : `ApiError` typée + affichage du détail serveur

**Files:**
- Create: `shell/src/api/ApiError.ts`
- Modify: `shell/src/api/base.ts`
- Modify: `shell/src/pages/CatalogPage.tsx` (ou le composant réel de
  création d'item touché par `quota-guard.spec.ts` — confirmer par lecture
  du test E2E lequel appelle réellement la création)
- Modify: `shell/e2e/quota-guard.spec.ts`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/api/base.test.ts`

**Interfaces:**
- Consumes: `CoreUnreachableError` (Tâche 7, pour bien distinguer les 2
  familles d'erreur dans `request()`).
- Produces: `class ApiError extends Error { status: number; title?: string; detail?: string; retryAfter?: number; }`,
  consommé par tout composant qui affiche une erreur de mutation
  (patron : `error instanceof ApiError ? error.detail ?? error.message : t("errors.generic")`,
  avec une branche dédiée `error.status === 429` affichant `retryAfter`).

Le cœur renvoie déjà des erreurs RFC 7807 (`application/problem+json`,
champs `title`+`detail`) depuis SP-26, et un 429 (rate limit,
`core/app/main.py` middleware `rate_limit_guard`) porte toujours un
en-tête `Retry-After` (valeur codée en dur `"60"` côté cœur — vérifié en
lisant le middleware). `request()` dans `base.ts` jette aujourd'hui une
`Error` générique sur `!res.ok`, jetant le `title`/`detail`/`Retry-After`
réels.

- [ ] **Step 1: `ApiError`**

  ```ts
  // shell/src/api/ApiError.ts
  // SPDX-License-Identifier: Apache-2.0
  export class ApiError extends Error {
    readonly status: number;
    readonly title?: string;
    readonly detail?: string;
    readonly retryAfter?: number;

    constructor(status: number, options?: { title?: string; detail?: string; retryAfter?: number }) {
      super(options?.detail ?? `Erreur HTTP ${status}`);
      this.name = "ApiError";
      this.status = status;
      this.title = options?.title;
      this.detail = options?.detail;
      this.retryAfter = options?.retryAfter;
    }
  }
  ```

- [ ] **Step 2: Test rouge — `request()` jette une `ApiError` avec `title`/`detail`/`retryAfter`**

  ```ts
  it("jette une ApiError portant title+detail RFC 7807 sur une réponse d'erreur", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ title: "Conflict", detail: "quota d'items du tenant dépassé : 1/1" }),
          { status: 409, headers: { "content-type": "application/problem+json" } },
        ),
      ),
    );
    const base = createBase({ getCoreUrl: () => "http://core.test", getAccessToken: () => undefined });
    await expect(base.request("/v1/items", { method: "POST" })).rejects.toMatchObject({
      status: 409,
      title: "Conflict",
      detail: "quota d'items du tenant dépassé : 1/1",
    });
  });

  it("jette une ApiError sans detail si le corps n'est pas parsable", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("", { status: 500 })));
    const base = createBase({ getCoreUrl: () => "http://core.test", getAccessToken: () => undefined });
    await expect(base.request("/v1/items")).rejects.toMatchObject({ status: 500, detail: undefined });
  });

  it("porte retryAfter (secondes) depuis l'en-tête Retry-After sur un 429", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({ title: "Too Many Requests", detail: "rate limit exceeded for items" }),
          { status: 429, headers: { "content-type": "application/problem+json", "Retry-After": "60" } },
        ),
      ),
    );
    const base = createBase({ getCoreUrl: () => "http://core.test", getAccessToken: () => undefined });
    await expect(base.request("/v1/items")).rejects.toMatchObject({ status: 429, retryAfter: 60 });
  });
  ```

  Run: `cd shell && npx vitest run src/api/base.test.ts`
  Expected: échecs (erreur générique jetée aujourd'hui, sans
  `status`/`title`/`detail`/`retryAfter`).

- [ ] **Step 3: Implémentation dans `request()`**

  Remplacer le `throw new Error(...)` générique sur `!res.ok` par :

  ```ts
  if (!res.ok) {
    let title: string | undefined;
    let detail: string | undefined;
    try {
      const body = (await res.clone().json()) as { title?: unknown; detail?: unknown };
      if (typeof body.title === "string") title = body.title;
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      title = undefined;
      detail = undefined;
    }
    const retryAfterHeader = res.headers.get("Retry-After");
    const retryAfter =
      res.status === 429 && retryAfterHeader !== null && !Number.isNaN(Number(retryAfterHeader))
        ? Number(retryAfterHeader)
        : undefined;
    throw new ApiError(res.status, { title, detail, retryAfter });
  }
  ```

  Ajouter `import { ApiError } from "./ApiError";` en tête de `base.ts`.

  Run: (même commande) — Expected: passe.

- [ ] **Step 4: Affichage — utiliser `error.detail`/`error.retryAfter` sur le site de création d'item**

  Lire d'abord `shell/e2e/quota-guard.spec.ts` en entier pour confirmer
  quel composant réel déclenche la création testée (le grounding
  identifie le test mais pas le composant exact — `NewItemButton` est le
  candidat le plus probable d'après la Tâche 1, à confirmer). Dans ce
  composant, remplacer le message d'échec générique actuel
  (`t("newItem.createFailed")` ou équivalent trouvé) par, avec une
  branche dédiée pour le 429 (nouvelle clé i18n
  `"errors.retryAfter": "Réessayez dans {seconds} s."`) :

  ```tsx
  {createMutation.isError && (
    <p role="alert" className="text-sm text-danger">
      {createMutation.error instanceof ApiError && createMutation.error.status === 429
        ? `${createMutation.error.detail ?? t("newItem.createFailed")} ${
            createMutation.error.retryAfter !== undefined
              ? t("errors.retryAfter", { seconds: createMutation.error.retryAfter })
              : ""
          }`.trim()
        : createMutation.error instanceof ApiError && createMutation.error.detail
          ? createMutation.error.detail
          : t("newItem.createFailed")}
    </p>
  )}
  ```

- [ ] **Step 5: Mettre à jour `quota-guard.spec.ts`**

  Le test asserte aujourd'hui le texte générique `"Échec de la création."`
  — c'est le changement de comportement assumé par la spec. Remplacer
  l'assertion par le texte réel du `detail` mocké :

  ```ts
  await expect(page.getByRole("alert")).toContainText("quota d'items du tenant dépassé : 1/1");
  ```

  Run: `cd shell && npx playwright test e2e/quota-guard.spec.ts`
  Expected: passe (nécessite le serveur de dev — voir Tâche 34 pour
  l'exécution complète de la suite E2E ; ici, valider au moins que le
  test ne référence plus le texte générique en relisant le diff).

- [ ] **Step 6: Répéter la même conversion sur les 6 autres sites de fetch de `base.ts` si un appelant lit déjà `error.message`**

  Grep `catch` autour de chaque appel des fonctions de `base.ts`
  (`fetchGeoJsonFeatures`, `fetchCoreCollections`,
  `fetchExternalRasterSources`, `fetchHostedTileset3dSources`,
  `fetchHostedTerrain3dSources`, `requestBlob`) pour repérer un
  affichage de `error.message` existant côté appelant ; si trouvé,
  remplacer par le même patron `instanceof ApiError ? error.detail ?? error.message : ...`.
  Documenter dans le message de commit si aucun site supplémentaire n'a
  été trouvé (comportement attendu si ces fonctions sont surtout
  consommées par des `useQuery` sans affichage d'erreur dédié).

  Run: `cd shell && npx vitest run`
  Expected: suite complète verte.

- [ ] **Step 7: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/api/ApiError.ts shell/src/api/base.ts shell/src/api/base.test.ts \
    shell/src/i18n/catalog.fr.ts shell/e2e/quota-guard.spec.ts
  git add -u shell/src
  git commit -m "$(cat <<'EOF'
  feat(shell): ApiError porte le detail RFC 7807 du cœur jusqu'à l'UI

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 9 — SP-B8 : accessibilité des erreurs de formulaire

**Files:**
- Modify: `shell/src/builder/widgets/form.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/builder/widgets/form.test.tsx`

**Interfaces:**
- Consumes: rien de nouveau.
- Produces: rien de nouveau — ajoute `aria-invalid`/`aria-describedby`/`id`
  aux champs déjà rendus par `FieldInput`.

`FieldInput` (lignes 348-450) n'a aujourd'hui aucun `id`,
`aria-invalid`, ni `aria-describedby` sur ses 6 branches de rendu ; le
message d'erreur associé (`<span role="alert" className="text-xs text-red-600">`, ligne 630)
n'est lié à aucun champ par `aria-describedby`.

- [ ] **Step 1: Test rouge — un champ en erreur porte `aria-invalid` et `aria-describedby` pointant vers le message**

  ```tsx
  it("associe le message d'erreur au champ via aria-describedby", async () => {
    render(<FormComponent {...propsWithFieldError("email")} />, { wrapper });
    const field = screen.getByLabelText(/email/i);
    expect(field).toHaveAttribute("aria-invalid", "true");
    const describedBy = field.getAttribute("aria-describedby");
    expect(describedBy).toBeTruthy();
    expect(document.getElementById(describedBy!)).toHaveTextContent(/obligatoire|invalide/i);
  });

  it("un champ valide n'a pas aria-invalid", () => {
    render(<FormComponent {...propsWithoutErrors} />, { wrapper });
    expect(screen.getByLabelText(/email/i)).not.toHaveAttribute("aria-invalid");
  });
  ```

  Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
  Expected: échec (aucun attribut `aria-*` posé aujourd'hui).

- [ ] **Step 2: Implémentation — `FieldInput` reçoit un id stable et propage l'état d'erreur**

  Donner à `FieldInput` un `id` déterministe dérivé du nom de champ
  (`` `field-${field.name}` ``) et un `errorId` correspondant
  (`` `field-${field.name}-error` ``). Sur chacune des 6 branches
  (attachment/boolean/integer-or-number/date/datetime/enum/texte), ajouter
  `id={fieldId}`, et quand `errorFor(field)` retourne un message :
  `aria-invalid="true"` et `aria-describedby={errorId}`. Le `<span
  role="alert">` de message d'erreur (ligne 630) reçoit `id={errorId}`.

  Run: (même commande) — Expected: passe.

- [ ] **Step 3: Couleur brute — remplacer `text-red-600` par le token sémantique**

  Aux lignes 185, 630, 699 de `form.tsx`, remplacer `text-red-600` par
  `text-danger` (token déjà défini dans `tokens.css`, cf. Tâche 30/31 pour
  le reste du balayage — ces 3 occurrences sont corrigées ici car déjà
  touchées par cette tâche, pas de duplication de travail avec SP-B12).

  Run: `cd shell && npx vitest run src/builder/widgets/form.test.tsx`
  Expected: vert (changement purement visuel, pas de nouvelle assertion
  nécessaire au-delà de celles déjà écrites).

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/builder/widgets/form.tsx shell/src/builder/widgets/form.test.tsx \
    shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  fix(shell): associe les erreurs de formulaire à leurs champs (aria-invalid/describedby)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 10 — SP-B4 : composant `LoadingState`

**Files:**
- Create: `shell/src/ui/kit/LoadingState.tsx`
- Modify: `shell/src/ui/kit/index.ts`
- Test: `shell/src/ui/kit/LoadingState.test.tsx`

**Interfaces:**
- Produces: `LoadingState({ label?: string }): JSX.Element`, `role="status"`,
  consommé par la Tâche 11.

- [ ] **Step 1: Test rouge**

  ```tsx
  it("affiche un indicateur de chargement avec le libellé par défaut", () => {
    render(<LoadingState />);
    expect(screen.getByRole("status")).toHaveTextContent(t("common.loading"));
  });

  it("accepte un libellé personnalisé", () => {
    render(<LoadingState label="Chargement des couches…" />);
    expect(screen.getByRole("status")).toHaveTextContent("Chargement des couches…");
  });
  ```

  Run: `cd shell && npx vitest run src/ui/kit/LoadingState.test.tsx`
  Expected: échec (module absent).

- [ ] **Step 2: Implémentation**

  ```tsx
  // shell/src/ui/kit/LoadingState.tsx
  // SPDX-License-Identifier: Apache-2.0
  import { t } from "../../i18n";

  export function LoadingState({ label }: { label?: string }) {
    return (
      <p role="status" className="flex items-center gap-2 text-sm text-ink-3">
        <span className="h-4 w-4 animate-spin rounded-full border-2 border-rule border-t-accent" aria-hidden="true" />
        {label ?? t("common.loading")}
      </p>
    );
  }
  ```

  Vérifier que `"common.loading"` existe déjà dans `catalog.fr.ts`
  (confirmé en grounding, utilisé par `UsagePage.tsx`).

  Run: (même commande) — Expected: passe.

- [ ] **Step 3: Export + commit**

  Ajouter `export { LoadingState } from "./LoadingState";` à `ui/kit/index.ts`.

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/ui/kit/LoadingState.tsx shell/src/ui/kit/LoadingState.test.tsx shell/src/ui/kit/index.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): ajoute le composant LoadingState au kit

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 11 — SP-B4 : balayage des indicateurs de chargement ad hoc

**Files:**
- Modify: (déterminé à l'exécution par le grep ci-dessous — pages/panneaux
  qui rendent `isLoading`/`isPending` avec un texte ou un style différent
  du patron `LoadingState`)
- Test: fichiers de test déjà existants pour chaque composant modifié

**Interfaces:**
- Consumes: `LoadingState` (Tâche 10).

- [ ] **Step 1: Énumération mécanique**

  ```bash
  cd shell && grep -rln '\.isLoading\b' src/pages src/builder src/map --include="*.tsx" | grep -v '\.test\.tsx$'
  ```

  Pour chaque fichier listé, lire le site exact du rendu conditionnel de
  chargement. Ne toucher que les sites qui rendent un texte/spinner ad hoc
  distinct de `LoadingState` (exclure les sites qui utilisent déjà
  `role="status"` avec `t("common.loading")` tel quel — déjà conformes).

- [ ] **Step 2: Remplacement fichier par fichier, un test par fichier touché**

  Pour chaque fichier retenu : test rouge (si le fichier de test existant
  ne couvre pas déjà l'état de chargement, en ajouter un ; sinon adapter
  l'assertion existante pour cibler `role="status"`), puis remplacer le
  rendu ad hoc par `<LoadingState />` (ou `<LoadingState label={...} />`
  si un libellé contextuel existait). Traiter les fichiers par lots de
  3-5 pour garder chaque étape de commit rapide à vérifier — ne pas tout
  committer en un seul diff massif.

  Run après chaque lot : `cd shell && npx vitest run <fichiers du lot>`
  Expected: vert à chaque lot.

- [ ] **Step 3: Commit par lot**

  ```bash
  cd /home/lenen/projets/geostudio
  git add <fichiers du lot>
  git commit -m "$(cat <<'EOF'
  refactor(shell): uniformise les indicateurs de chargement sur LoadingState

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

  Répéter jusqu'à épuisement de la liste du Step 1.

---

## Tâche 12 — SP-B10a : libellés d'état de job partagés

**Files:**
- Create: `shell/src/lib/jobStatusLabel.ts`
- Modify: (panneaux qui affichent un statut de run — `PipelineRunPanel`,
  `ReportRunPanel` ou noms réels trouvés par grep `grep -rln "status.*running\|status.*succeeded\|status.*failed" shell/src/builder shell/src/pages --include="*.tsx"`)
- Test: `shell/src/lib/jobStatusLabel.test.ts`

**Interfaces:**
- Produces: `jobStatusLabel(status: string): string`, consommé par les
  panneaux de run identifiés au Step 1.

- [ ] **Step 1: Grep de découverte des sites réels**

  ```bash
  cd shell && grep -rln 'status ===' src/builder src/pages --include="*.tsx" | grep -v '\.test\.tsx$'
  ```

  Lire chaque fichier trouvé pour confirmer les valeurs de statut réelles
  utilisées par le cœur (`pending`, `running`, `succeeded`, `failed`,
  `cancelled` — confirmer contre `core/app/pipelines/jobs.py`/schéma
  exposé plutôt que de deviner).

- [ ] **Step 2: Test rouge**

  ```ts
  it("traduit chaque statut connu", () => {
    expect(jobStatusLabel("pending")).toBe("En attente");
    expect(jobStatusLabel("running")).toBe("En cours");
    expect(jobStatusLabel("succeeded")).toBe("Terminé");
    expect(jobStatusLabel("failed")).toBe("Échoué");
    expect(jobStatusLabel("cancelled")).toBe("Annulé");
  });

  it("retombe sur le statut brut pour une valeur inconnue", () => {
    expect(jobStatusLabel("weird")).toBe("weird");
  });
  ```

  Run: `cd shell && npx vitest run src/lib/jobStatusLabel.test.ts`
  Expected: échec (module absent).

- [ ] **Step 3: Implémentation**

  ```ts
  // shell/src/lib/jobStatusLabel.ts
  // SPDX-License-Identifier: Apache-2.0
  import { t } from "../i18n";

  const KNOWN_STATUSES = ["pending", "running", "succeeded", "failed", "cancelled"] as const;
  type KnownStatus = (typeof KNOWN_STATUSES)[number];

  function isKnownStatus(status: string): status is KnownStatus {
    return (KNOWN_STATUSES as readonly string[]).includes(status);
  }

  export function jobStatusLabel(status: string): string {
    if (!isKnownStatus(status)) return status;
    return t(`jobStatus.${status}`);
  }
  ```

  Clés i18n :

  ```ts
  "jobStatus.pending": "En attente",
  "jobStatus.running": "En cours",
  "jobStatus.succeeded": "Terminé",
  "jobStatus.failed": "Échoué",
  "jobStatus.cancelled": "Annulé",
  ```

  Run: (même commande) — Expected: passe.

- [ ] **Step 4: Wiring dans les panneaux identifiés au Step 1**

  Pour chaque site : test rouge (le libellé brut `"running"` apparaissait
  à l'écran, remplacer l'assertion par `jobStatusLabel("running")` →
  `"En cours"`), puis remplacer le rendu direct de `status` par
  `jobStatusLabel(status)`.

  Run: `cd shell && npx vitest run <fichiers touchés>`
  Expected: vert.

- [ ] **Step 5: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/lib/jobStatusLabel.ts shell/src/lib/jobStatusLabel.test.ts shell/src/i18n/catalog.fr.ts
  git add -u shell/src/builder shell/src/pages
  git commit -m "$(cat <<'EOF'
  feat(shell): libellés d'état de job traduits et partagés

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 13 — SP-B10b : en-tête `X-Tile-Truncated` (cœur)

**Files:**
- Modify: `core/app/features/tiles.py`
- Test: `core/tests/test_features_tiles_postgis.py`

**Interfaces:**
- Produces: en-tête HTTP `X-Tile-Truncated: true` sur
  `GET /v1/collections/{id}/tiles/{z}/{x}/{y}.mvt` quand
  `feature_count == MAX_TILE_FEATURES`. Consommé par la Tâche 14.
- Pas de changement de schéma Pydantic ni de route — **aucune
  régénération OpenAPI/TS nécessaire** (confirmé en Tâche 34).

- [ ] **Step 1: Test rouge**

  Dans `test_features_tiles_postgis.py`, ajouter à côté du test existant
  `test_a_dense_tile_is_truncated_to_the_feature_cap` (même patron
  `monkeypatch.setattr(tiles_module, "MAX_TILE_FEATURES", 2)`) :

  ```python
  def test_a_truncated_tile_carries_the_truncation_header(pg_app, monkeypatch):
      client, tiles_module = pg_app
      monkeypatch.setattr(tiles_module, "MAX_TILE_FEATURES", 2)
      # insérer 3 features (réutiliser le helper d'insertion du test voisin)
      resp = client.get(TILE_PATH)
      assert resp.status_code == 200
      assert resp.headers.get("X-Tile-Truncated") == "true"

  def test_a_non_truncated_tile_has_no_truncation_header(pg_app, monkeypatch):
      client, tiles_module = pg_app
      monkeypatch.setattr(tiles_module, "MAX_TILE_FEATURES", 50)
      resp = client.get(TILE_PATH)
      assert resp.status_code == 200
      assert "X-Tile-Truncated" not in resp.headers
  ```

  Adapter à la forme exacte de la fixture `pg_app` (elle peut renvoyer
  autre chose qu'un tuple `(client, module)` — vérifier par lecture du
  test voisin avant d'écrire, réutiliser son insertion de 3 features telle
  quelle plutôt que de la dupliquer).

  Run: `cd core && CORE_TEST_DATABASE_URL=<dsn postgis-test> uv run pytest tests/test_features_tiles_postgis.py -k truncat -m postgis`
  Expected: 2 échecs (en-tête jamais posé aujourd'hui).

- [ ] **Step 2: Implémentation — `build_mvt_sql` compte dans la même requête**

  Modifier `build_mvt_sql()` (lignes 78-111) pour que la requête externe
  renvoie 2 colonnes au lieu d'une :

  ```python
  sql = f"""
  SELECT ST_AsMVT(tile, :layer, :extent, 'geom', :fid), count(*)
  FROM (
      SELECT {props_sql}, ST_AsMVTGeom(...) AS geom
      FROM ({inner_query}) AS src
      LIMIT :max_features
  ) AS tile
  WHERE tile.geom IS NOT NULL
  """
  ```

  Adapter au SQL réel déjà présent (le grounding donne la forme générale,
  pas le texte exact caractère pour caractère — lire les lignes 78-111
  avant d'éditer et ne changer que l'aggrégat `ST_AsMVT(...)` isolé en
  `ST_AsMVT(...), count(*)` plus le `WHERE` externe nécessaire pour que
  `count(*)` compte les géométries effectivement matérialisées).

  Dans `get_collection_tile` (lignes 126-182), remplacer
  `.scalar()` par `.first()` et dé-packer les 2 colonnes :

  ```python
  row = session.execute(text(sql), {...}).first()
  if row is None or not row[0]:
      return Response(status_code=204)
  tile_bytes, feature_count = row[0], row[1]
  headers = {"Cache-Control": ...}
  if feature_count == MAX_TILE_FEATURES:
      headers["X-Tile-Truncated"] = "true"
  return Response(content=bytes(tile_bytes), media_type=MVT_MEDIA_TYPE, headers=headers)
  ```

  Run: (même commande Step 1) — Expected: 2 tests passent, suite complète
  du fichier toujours verte : `cd core && CORE_TEST_DATABASE_URL=<dsn> uv run pytest tests/test_features_tiles_postgis.py -m postgis`.

- [ ] **Step 3: Qualité — ruff/mypy sur le fichier touché**

  Run: `cd core && uv run ruff check app/features/tiles.py && uv run ruff format --check app/features/tiles.py`
  Expected: propre.

- [ ] **Step 4: Confirmer l'absence d'impact OpenAPI**

  Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" uv run python scripts/export_openapi.py /tmp/openapi-check.json && diff openapi.json /tmp/openapi-check.json`
  Expected: diff vide — la route ne déclare pas ses en-têtes de réponse
  dans le schéma FastAPI/Pydantic (elle renvoie une `Response` brute avec
  un dict `headers`, jamais introspecté par la génération OpenAPI). Si le
  diff n'est PAS vide, régénérer `openapi.json` et
  `shell/src/api/generated/core-schema.d.ts` avant de commit (voir
  incantation exacte en tête du fichier CLAUDE.md, § Commandes).

- [ ] **Step 5: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add core/app/features/tiles.py core/tests/test_features_tiles_postgis.py
  git commit -m "$(cat <<'EOF'
  feat(core): en-tête X-Tile-Truncated quand une tuile MVT atteint le plafond

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 14 — SP-B10c : badge de troncature dans `LayersPanel`

**Files:**
- Modify: `shell/src/map/LayersPanel.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: `shell/src/map/LayersPanel.test.tsx`

**Interfaces:**
- Consumes: en-tête `X-Tile-Truncated` (Tâche 13), `useAuth().getAccessToken()`.
- Produces: rien de nouveau.

MapLibre ne remonte pas les en-têtes de réponse au code applicatif pour
les tuiles chargées via la source `vector` déclarative. Design retenu
(scope volontairement restreint, documenté dans la spec) : une requête de
sonde ponctuelle sur la tuile racine `0/0/0.mvt` de chaque couche
`vector` visible, au montage du panneau, pour poser un badge informatif —
pas un suivi temps réel par tuile affichée.

- [ ] **Step 1: Test rouge**

  ```tsx
  it("affiche un badge de troncature quand la tuile racine répond X-Tile-Truncated", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue(new Response(new Uint8Array(), { status: 200, headers: { "X-Tile-Truncated": "true" } })),
    );
    render(<LayersPanel layers={[vectorLayer]} onChange={vi.fn()} />, { wrapper });
    expect(await screen.findByText(t("layersPanel.truncatedBadge"))).toBeInTheDocument();
  });

  it("n'affiche aucun badge quand la tuile n'est pas tronquée", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response(new Uint8Array(), { status: 200 })));
    render(<LayersPanel layers={[vectorLayer]} onChange={vi.fn()} />, { wrapper });
    await waitFor(() => expect(vi.mocked(fetch)).toHaveBeenCalled());
    expect(screen.queryByText(t("layersPanel.truncatedBadge"))).not.toBeInTheDocument();
  });
  ```

  `vectorLayer` : fixture `MapLayer` avec `kind: "vector"` et `tilesUrl`
  se terminant par `/tiles/{z}/{x}/{y}.mvt` (patron réel du fichier).

  Run: `cd shell && npx vitest run src/map/LayersPanel.test.tsx`
  Expected: échec (aucune sonde, aucun badge).

- [ ] **Step 2: Clé i18n**

  `"layersPanel.truncatedBadge": "Tuile tronquée (trop d'entités)"`.

- [ ] **Step 3: Implémentation**

  Dans `LayersPanel`, ajouter un état `truncatedLayerIds: Set<string>` et
  un effet qui sonde chaque couche `kind === "vector"` au montage/à chaque
  changement de `layers` :

  ```tsx
  const { getAccessToken } = useAuth();
  const [truncatedLayerIds, setTruncatedLayerIds] = useState<Set<string>>(new Set());

  useEffect(() => {
    const vectorLayers = layers.filter((l) => l.kind === "vector");
    let cancelled = false;
    void Promise.all(
      vectorLayers.map(async (layer) => {
        const rootUrl = layer.tilesUrl.replace("{z}/{x}/{y}", "0/0/0");
        const token = getAccessToken();
        const res = await fetch(rootUrl, {
          headers: token ? { Authorization: `Bearer ${token}` } : undefined,
        });
        return [layer.id, res.headers.get("X-Tile-Truncated") === "true"] as const;
      }),
    ).then((results) => {
      if (cancelled) return;
      setTruncatedLayerIds(new Set(results.filter(([, truncated]) => truncated).map(([id]) => id)));
    });
    return () => {
      cancelled = true;
    };
  }, [layers, getAccessToken]);
  ```

  Dans le `<li>` de rendu de chaque couche `vector` (bloc identifié en
  grounding autour de la ligne 391), ajouter, à côté du titre :

  ```tsx
  {truncatedLayerIds.has(layer.id) && (
    <span className="rounded bg-warn-soft px-1.5 py-0.5 text-xs text-warn" title={t("layersPanel.truncatedBadge")}>
      {t("layersPanel.truncatedBadge")}
    </span>
  )}
  ```

  Vérifier `--gs-warn`/`--gs-warn-soft` existent (confirmés en grounding).

  Run: (même commande Step 1) — Expected: passe, suite complète du
  fichier toujours verte.

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/map/LayersPanel.tsx shell/src/map/LayersPanel.test.tsx shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): badge de troncature de tuile sur les couches vecteur

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 15 — SP-B10d : progression grossière des pipelines (N/M nœuds)

**Files:**
- Modify: (panneau de run de pipeline identifié à la Tâche 12 Step 1 —
  probablement `PipelineRunPanel.tsx` ou équivalent réel)
- Modify: `shell/src/i18n/catalog.fr.ts`
- Test: fichier de test du composant touché

**Interfaces:**
- Consumes: la forme réelle de la réponse de statut de run déjà exposée
  par le cœur (confirmer les champs disponibles — `completed_nodes`/
  `total_nodes` ou noms réels — par lecture du type TS généré
  `core-schema.d.ts` avant d'écrire, ne pas supposer leur existence).

- [ ] **Step 1: Vérifier la forme réelle disponible côté API**

  ```bash
  cd shell && grep -n "PipelineRun\|node.*progress\|completed_nodes" src/api/generated/core-schema.d.ts
  ```

  Si aucun champ de progression par nœud n'existe déjà dans le schéma
  exposé, ce sous-chantier est bloqué côté cœur et doit être noté comme
  tel dans le rapport final plutôt que simulé côté shell — **ne pas
  inventer un champ qui n'existe pas côté serveur**. Si un champ existe
  (ex. `completed_nodes`/`total_nodes` sur l'objet de run), continuer.

- [ ] **Step 2: Test rouge (si champ confirmé disponible)**

  ```tsx
  it("affiche la progression N/M nœuds pendant une exécution en cours", () => {
    render(<PipelineRunPanel run={{ status: "running", completedNodes: 2, totalNodes: 5 }} />);
    expect(screen.getByText("2 / 5 nœuds")).toBeInTheDocument();
  });
  ```

  Run: `cd shell && npx vitest run <fichier du composant>`
  Expected: échec.

- [ ] **Step 3: Implémentation**

  Ajouter le rendu conditionnel `run.status === "running" && (<p>{t("pipelineRun.nodeProgress", { completed: run.completedNodes, total: run.totalNodes })}</p>)`.
  Clé : `"pipelineRun.nodeProgress": "{completed} / {total} nœuds"`.

  Run: (même commande) — Expected: passe.

- [ ] **Step 4: Commit (ou note de blocage si Step 1 a établi l'absence du champ)**

  Si implémenté :

  ```bash
  cd /home/lenen/projets/geostudio
  git add <fichiers touchés> shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): affiche la progression par nœud d'une exécution de pipeline

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

  Si bloqué (champ absent côté cœur), ne rien committer sur ce point et
  le consigner explicitement dans le rapport de clôture (Tâche 34) comme
  hors-périmètre de ce plan (nécessiterait une évolution de schéma cœur,
  hors Vague B qui est censée n'être qu'additive sur le shell).

---

## Tâche 16 — SP-B9a : `useUrlSyncedState`

**Files:**
- Create: `shell/src/lib/useUrlSyncedState.ts`
- Test: `shell/src/lib/useUrlSyncedState.test.ts`

**Interfaces:**
- Produces: `useUrlSyncedState<T extends string>(paramName: string, defaultValue: T | null): [T | null, (value: T | null) => void]`,
  consommé par les Tâches 17-19.

- [ ] **Step 1: Test rouge**

  ```tsx
  function renderHookWithRouter(paramName: string, defaultValue: string | null, initialPath = "/") {
    return renderHook(() => useUrlSyncedState(paramName, defaultValue), {
      wrapper: ({ children }) => (
        <MemoryRouter initialEntries={[initialPath]}>
          <Routes><Route path="*" element={children as React.ReactElement} /></Routes>
        </MemoryRouter>
      ),
    });
  }

  it("lit la valeur initiale depuis le paramètre d'URL", () => {
    const { result } = renderHookWithRouter("page", null, "/?page=p2");
    expect(result.current[0]).toBe("p2");
  });

  it("retombe sur la valeur par défaut si le paramètre est absent", () => {
    const { result } = renderHookWithRouter("page", "p1", "/");
    expect(result.current[0]).toBe("p1");
  });

  it("met à jour l'URL quand le setter est appelé", () => {
    const { result } = renderHookWithRouter("page", null, "/");
    act(() => result.current[1]("p3"));
    expect(result.current[0]).toBe("p3");
  });

  it("retire le paramètre de l'URL quand le setter reçoit null", () => {
    const { result } = renderHookWithRouter("page", null, "/?page=p2");
    act(() => result.current[1](null));
    expect(result.current[0]).toBeNull();
  });
  ```

  Run: `cd shell && npx vitest run src/lib/useUrlSyncedState.test.ts`
  Expected: échec (module absent).

- [ ] **Step 2: Implémentation**

  ```ts
  // shell/src/lib/useUrlSyncedState.ts
  // SPDX-License-Identifier: Apache-2.0
  import { useCallback } from "react";
  import { useSearchParams } from "react-router-dom";

  export function useUrlSyncedState<T extends string>(
    paramName: string,
    defaultValue: T | null,
  ): [T | null, (value: T | null) => void] {
    const [searchParams, setSearchParams] = useSearchParams();
    const raw = searchParams.get(paramName);
    const value = (raw as T | null) ?? defaultValue;

    const setValue = useCallback(
      (next: T | null) => {
        setSearchParams(
          (prev) => {
            const updated = new URLSearchParams(prev);
            if (next === null) {
              updated.delete(paramName);
            } else {
              updated.set(paramName, next);
            }
            return updated;
          },
          { replace: true },
        );
      },
      [paramName, setSearchParams],
    );

    return [value, setValue];
  }
  ```

  Run: (même commande) — Expected: 4 tests passent.

- [ ] **Step 3: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/lib/useUrlSyncedState.ts shell/src/lib/useUrlSyncedState.test.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): ajoute useUrlSyncedState pour synchroniser un état à l'URL

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 17 — SP-B9b : synchroniser `AppBuilderPage` (page active + sélection)

**Files:**
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Test: `shell/src/pages/AppBuilderPage.test.tsx`

**Interfaces:**
- Consumes: `useUrlSyncedState` (Tâche 16).

`AppBuilderPage.tsx` utilise aujourd'hui `useState` simple pour
`activePageId`/`selectedId`, tous les sites d'appel confirmés passer des
valeurs directes (jamais la forme fonctionnelle `(prev) => ...`) —
migration directe sans changement de logique environnante.

- [ ] **Step 1: Test rouge — la page active survit à un rechargement (simulé par un remount avec la même URL)**

  ```tsx
  it("conserve la page active dans l'URL après un remount", () => {
    const { unmount } = render(<AppBuilderPage />, { wrapper, route: "/apps/app-1/edit?page=page-2" });
    unmount();
    render(<AppBuilderPage />, { wrapper, route: "/apps/app-1/edit?page=page-2" });
    expect(screen.getByRole("tab", { name: /page 2/i })).toHaveAttribute("aria-selected", "true");
  });
  ```

  Adapter au vrai patron de rendu de test du fichier (wrapper de route
  existant — le fichier utilise déjà un routeur pour les tests d'après le
  fait que la page consomme `useParams`).

  Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
  Expected: échec (état perdu au remount, pas de lecture d'URL).

- [ ] **Step 2: Implémentation**

  Remplacer `const [activePageId, setActivePageId] = useState<string | null>(null);`
  par `const [activePageId, setActivePageId] = useUrlSyncedState<string>("page", null);`.
  Ne toucher aucun autre site (les 6 sites d'appel de `setActivePageId`
  identifiés en grounding continuent de fonctionner sans changement,
  signature identique). Faire de même pour `selectedId` avec le paramètre
  `"selected"`.

  Run: (même commande) — Expected: passe, suite complète du fichier
  toujours verte (`npx vitest run src/pages/AppBuilderPage.test.tsx` sans
  filtre).

- [ ] **Step 3: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
  git commit -m "$(cat <<'EOF'
  feat(shell): synchronise la page/sélection active du builder d'app à l'URL

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 18 — SP-B9c : synchroniser `PipelineBuilderPage` (nœud sélectionné)

**Files:**
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`
- Test: `shell/src/pages/PipelineBuilderPage.test.tsx`

**Interfaces:**
- Consumes: `useUrlSyncedState` (Tâche 16).

- [ ] **Step 1: Test rouge** — même patron que la Tâche 17 : remount avec
  `?node=<id>` dans l'URL doit restaurer la sélection.

  Run: `cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx`
  Expected: échec.

- [ ] **Step 2: Implémentation** — remplacer
  `const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);`
  par `useUrlSyncedState<string>("node", null)`, sans toucher les sites
  d'appel (`onSelectNode={setSelectedNodeId}` continue de fonctionner).

  Run: (même commande) — Expected: passe.

- [ ] **Step 3: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/pages/PipelineBuilderPage.tsx shell/src/pages/PipelineBuilderPage.test.tsx
  git commit -m "$(cat <<'EOF'
  feat(shell): synchronise le nœud sélectionné du builder de pipeline à l'URL

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 19 — SP-B9d : synchroniser `SqlLabPage` (requête active dans l'historique)

**Files:**
- Modify: `shell/src/lib/sqlLabHistory.ts`
- Modify: `shell/src/pages/SqlLabPage.tsx`
- Test: `shell/src/lib/sqlLabHistory.test.ts`, `shell/src/pages/SqlLabPage.test.tsx`

**Interfaces:**
- Consumes: `useUrlSyncedState` (Tâche 16).
- Produces: `SqlHistoryEntry.id: string` (champ ajouté),
  `findSqlHistoryEntry(id: string): SqlHistoryEntry | undefined` (nouveau
  helper). **Décision de cadrage** (au-delà du texte littéral de la
  spec) : `SqlHistoryEntry` n'avait aucun champ `id` (confirmé en
  grounding) ; sans lui, `?historyId=<id>` ne peut désigner aucune
  entrée. Ajout minimal et documenté ici plutôt que dans le corps de la
  spec.

- [ ] **Step 1: Test rouge — `sqlLabHistory`**

  Dans `sqlLabHistory.test.ts` (créer si absent, sinon étendre) :

  ```ts
  it("attribue un id unique à chaque entrée ajoutée", () => {
    const history = appendSqlHistory({ sql: "select 1", executedAt: "2026-09-26T00:00:00Z", status: "ok", rowCount: 1 });
    expect(history[0].id).toBeTruthy();
  });

  it("findSqlHistoryEntry retrouve une entrée par id", () => {
    const history = appendSqlHistory({ sql: "select 1", executedAt: "2026-09-26T00:00:00Z", status: "ok", rowCount: 1 });
    expect(findSqlHistoryEntry(history[0].id)).toEqual(history[0]);
  });

  it("findSqlHistoryEntry renvoie undefined pour un id inconnu", () => {
    expect(findSqlHistoryEntry("inconnu")).toBeUndefined();
  });
  ```

  Run: `cd shell && npx vitest run src/lib/sqlLabHistory.test.ts`
  Expected: échec (`id` absent du type, `findSqlHistoryEntry` inexistant).

- [ ] **Step 2: Implémentation**

  ```ts
  export type SqlHistoryEntry = {
    id: string;
    sql: string;
    executedAt: string;
    status: "ok" | "error";
    rowCount?: number;
  };

  export function appendSqlHistory(entry: Omit<SqlHistoryEntry, "id">): SqlHistoryEntry[] {
    const withId: SqlHistoryEntry = { ...entry, id: crypto.randomUUID() };
    const current = readSqlHistory();
    const updated = [withId, ...current].slice(0, 20);
    localStorage.setItem(HISTORY_KEY, JSON.stringify(updated));
    return updated;
  }

  export function findSqlHistoryEntry(id: string): SqlHistoryEntry | undefined {
    return readSqlHistory().find((entry) => entry.id === id);
  }
  ```

  Conserver le nom réel de la constante de clé localStorage
  (`HISTORY_KEY` ou équivalent — vérifier avant d'éditer, ne pas
  renommer).

  Run: (même commande) — Expected: 3 tests passent.

- [ ] **Step 3: Test rouge — `SqlLabPage` synchronise `historyId` à l'URL**

  ```tsx
  it("restaure la requête sélectionnée dans l'historique via l'URL", () => {
    localStorage.setItem("geostudio.sqlLab.history", JSON.stringify([{ id: "h1", sql: "select 2", executedAt: "…", status: "ok", rowCount: 1 }]));
    render(<SqlLabPage />, { wrapper, route: "/analytics/sql?historyId=h1" });
    expect(screen.getByRole("textbox", { name: /requête/i })).toHaveValue("select 2");
  });
  ```

  Run: `cd shell && npx vitest run src/pages/SqlLabPage.test.tsx`
  Expected: échec (aucune lecture de `historyId`).

- [ ] **Step 4: Implémentation `SqlLabPage`**

  Ajouter `const [historyId, setHistoryId] = useUrlSyncedState<string>("historyId", null);`
  et un effet qui, quand `historyId` change, appelle
  `findSqlHistoryEntry(historyId)` et pousse son `sql` dans `setSql(...)`
  si trouvé. Sur clic d'une entrée d'historique dans la liste déjà
  rendue, appeler `setHistoryId(entry.id)` en plus de l'action existante
  (charger le `sql` dans l'éditeur).

  Run: (même commande) — Expected: passe.

- [ ] **Step 5: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/lib/sqlLabHistory.ts shell/src/lib/sqlLabHistory.test.ts \
    shell/src/pages/SqlLabPage.tsx shell/src/pages/SqlLabPage.test.tsx
  git commit -m "$(cat <<'EOF'
  feat(shell): identifie les entrées d'historique SQL Lab, restaure la sélection depuis l'URL

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 20 — SP-B11a : `DataTable` accessible au clavier + `onRowClick`

**Files:**
- Modify: `shell/src/ui/kit/DataTable.tsx`
- Test: `shell/src/ui/kit/DataTable.test.tsx`

**Interfaces:**
- Produces: nouvelle prop optionnelle `onRowClick?: (row: T) => void` sur
  `DataTable`, `<th>` triable devient focusable/activable au clavier.
  Consommé par les Tâches 21-24.

- [ ] **Step 1: Test rouge — tri au clavier**

  ```tsx
  it("trie au clavier (Entrée) sur un en-tête de colonne triable", async () => {
    const onSortChange = vi.fn();
    render(<DataTable columns={cols} rows={rows} getRowId={(r) => r.id} sortKey="name" sortDirection="asc" onSortChange={onSortChange} />);
    const header = screen.getByRole("columnheader", { name: /nom/i });
    header.focus();
    await userEvent.keyboard("{Enter}");
    expect(onSortChange).toHaveBeenCalledWith("name");
  });

  it("appelle onRowClick au clic sur une ligne", async () => {
    const onRowClick = vi.fn();
    render(<DataTable columns={cols} rows={rows} getRowId={(r) => r.id} onRowClick={onRowClick} />);
    await userEvent.click(screen.getAllByRole("row")[1]);
    expect(onRowClick).toHaveBeenCalledWith(rows[0]);
  });
  ```

  Run: `cd shell && npx vitest run src/ui/kit/DataTable.test.tsx`
  Expected: 2 échecs (pas de `tabIndex`/`onKeyDown` sur `<th>`, pas de prop
  `onRowClick`).

- [ ] **Step 2: Implémentation**

  Sur le `<th>` triable (lignes 44-59), ajouter
  `tabIndex={0}` et
  `onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onSortChange?.(col.key); } }}`.

  Ajouter la prop `onRowClick?: (row: T) => void` à la signature du
  composant, et sur chaque `<tr>` de ligne de données :
  `onClick={onRowClick ? () => onRowClick(row) : undefined}`,
  `style={onRowClick ? { cursor: "pointer" } : undefined}`.

  Run: (même commande) — Expected: 2 tests passent, suite complète du
  fichier toujours verte.

- [ ] **Step 3: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/ui/kit/DataTable.tsx shell/src/ui/kit/DataTable.test.tsx
  git commit -m "$(cat <<'EOF'
  fix(shell): DataTable triable au clavier, ajoute onRowClick

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 21 — SP-B11b : migrer `RolesAdminPage`/`HarvestSourcesAdminPage`/`UsersAdminPage` sur `DataTable`

**Files:**
- Modify: `shell/src/pages/RolesAdminPage.tsx`
- Modify: `shell/src/pages/HarvestSourcesAdminPage.tsx`
- Modify: `shell/src/pages/UsersAdminPage.tsx`
- Test: fichiers de test correspondants

**Interfaces:**
- Consumes: `DataTable` (Tâche 20).

- [ ] **Step 1: `RolesAdminPage` — test rouge sur le tri**

  Le fichier grounded (154 lignes, `<table>` manuel avec colonnes
  nom/nombre de privilèges/actions) n'a aujourd'hui aucun tri. Ajouter un
  test qui clique l'en-tête "Nom" et vérifie l'ordre des lignes rendu
  après clic (comportement nouveau, cohérent avec `DataTable`).

  Run: `cd shell && npx vitest run src/pages/RolesAdminPage.test.tsx`
  Expected: échec.

- [ ] **Step 2: Migration `RolesAdminPage`**

  Remplacer le `<table>` manuel par
  `<DataTable columns={[...]} rows={roles} getRowId={(r) => r.id} sortKey={sortKey} sortDirection={sortDirection} onSortChange={...} />`,
  colonnes `{key: "name", label: t("rolesAdmin.columnName"), render: (r) => r.name}`,
  `{key: "privilegeCount", label: t("rolesAdmin.columnPrivileges"), render: (r) => r.privileges.length}`,
  `{key: "actions", label: "", render: (r) => <RowActions role={r} />}`.
  Conserver le `ConfirmDialog` de suppression déjà en place (lignes
  143-151), inchangé — seul le rendu du tableau change. `RolesAdminPage`
  a reçu un garde `EmptyState` en Tâche 2 (`rolesAdmin.empty`) : ce garde
  doit rester AVANT le rendu de `DataTable`, pas remplacé par lui — même
  risque que celui documenté en Tâche 22 pour `CollectionsAdminPage`.

  Run: (même commande) — Expected: passe, suite complète verte.

- [ ] **Step 3: Répéter pour `HarvestSourcesAdminPage` et `UsersAdminPage`**

  Même patron. `UsersAdminPage` a déjà pagination/recherche (SP-38) —
  conserver ces contrôles inchangés, migrer seulement le corps du
  `<table>`. Les 3 pages de cette tâche (`RolesAdminPage`,
  `HarvestSourcesAdminPage`, `UsersAdminPage`) ont chacune reçu un garde
  `EmptyState` en Tâche 2 (`rolesAdmin.empty`/`harvestAdmin.empty`/
  `usersAdmin.empty`) : sur les 3, s'assurer que ce garde reste AVANT le
  rendu de `DataTable`, pas remplacé par lui — vérifier chaque page
  individuellement après migration (ne pas supposer que le patron de
  `RolesAdminPage` couvre les 2 autres sans vérification).

  Run: `cd shell && npx vitest run src/pages/HarvestSourcesAdminPage.test.tsx src/pages/UsersAdminPage.test.tsx`
  Expected: vert.

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/pages/RolesAdminPage.tsx shell/src/pages/HarvestSourcesAdminPage.tsx \
    shell/src/pages/UsersAdminPage.tsx shell/src/pages/RolesAdminPage.test.tsx \
    shell/src/pages/HarvestSourcesAdminPage.test.tsx shell/src/pages/UsersAdminPage.test.tsx \
    shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  refactor(shell): migre Rôles/Moissonnage/Utilisateurs sur DataTable

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 22 — SP-B11c : migrer `CollectionsAdminPage`/`UsagePage`

**Files:**
- Modify: `shell/src/pages/CollectionsAdminPage.tsx`
- Modify: `shell/src/pages/UsagePage.tsx`
- Test: fichiers de test correspondants

**Interfaces:**
- Consumes: `DataTable` (Tâche 20).

- [ ] **Step 1-3** — même patron exact que la Tâche 21 : test rouge de tri
  par page, migration du `<table>` manuel vers `DataTable`, en conservant
  chaque comportement existant (pagination d'`UsagePage`, `EmptyState`
  ajouté en Tâche 2 pour `CollectionsAdminPage` — s'assurer que le garde
  d'état vide reste AVANT le rendu de `DataTable`, pas remplacé par lui).

  Run: `cd shell && npx vitest run src/pages/CollectionsAdminPage.test.tsx src/pages/UsagePage.test.tsx`
  Expected: rouge puis vert.

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/pages/CollectionsAdminPage.tsx shell/src/pages/UsagePage.tsx \
    shell/src/pages/CollectionsAdminPage.test.tsx shell/src/pages/UsagePage.test.tsx \
    shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  refactor(shell): migre Collections/Usage sur DataTable

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 23 — SP-B11d : migrer l'aperçu du pipeline builder

**Files:**
- Modify: (composant réel d'aperçu tabulaire du pipeline builder — grep
  `grep -rln "PipelinePreview\|aperçu.*pipeline" shell/src/builder --include="*.tsx"`
  pour confirmer le nom exact avant d'éditer)
- Test: fichier de test correspondant

**Interfaces:**
- Consumes: `DataTable` (Tâche 20), `onRowClick` pour la sélection de
  ligne déjà mentionnée par le CLAUDE.md (autorisation resserrée à
  `action="write"` — ne pas toucher à cette autorisation, seulement au
  rendu tabulaire).

- [ ] **Step 1: Confirmer le composant réel**

  ```bash
  cd shell && grep -rln "aperçu\|preview" src/builder --include="*.tsx" | xargs grep -l "table\|<th"
  ```

- [ ] **Step 2: Test rouge** — tri/pagination déjà existants (SP-15,
  "pipeline builder UX") doivent continuer de fonctionner après migration
  ; ajouter un test de clic de ligne si `onRowClick` est une capacité
  nouvellement branchée ici (sélection d'une ligne d'aperçu pour
  inspection détaillée — confirmer d'abord si un tel besoin existe déjà
  dans le composant avant d'ajouter un comportement non demandé par la
  spec).

  Run: `cd shell && npx vitest run <fichier confirmé>`
  Expected: rouge (si nouveau comportement) ou déjà vert (si migration
  pure sans nouveau comportement — dans ce cas, le test à écrire vérifie
  la non-régression du tri/pagination existants après le remplacement du
  `<table>` manuel).

- [ ] **Step 3: Migration** — remplacer le rendu tabulaire manuel par
  `DataTable`, conserver tri/pagination/formatage déjà livrés par
  "pipeline builder UX" (CLAUDE.md § Livré), ne pas régresser
  l'autorisation `action="write"` déjà en place sur la route
  d'aperçu — ce chantier ne touche que le rendu client, pas la requête.

  Run: (même commande) — Expected: vert.

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add <fichiers touchés>
  git commit -m "$(cat <<'EOF'
  refactor(shell): migre l'aperçu du pipeline builder sur DataTable

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 24 — SP-B11e : migrer le widget table de l'App Builder

**Files:**
- Modify: `shell/src/builder/widgets/data.tsx`
- Test: `shell/src/builder/widgets/data.test.tsx`

**Interfaces:**
- Consumes: `DataTable` (Tâche 20).
- Produces: adaptateur interne `toDataTableColumns(columns: TableColumn[]): DataTableColumn<Record<string, unknown>>[]`
  (privé au fichier, pas exporté — pas de nouvelle interface publique).

Le widget table (lignes 225-350+) a un tri/pagination manuels, sans
`aria-sort`, et une sélection de ligne (`selectRecord`) déjà branchée sur
le bus d'événements — c'est le candidat naturel pour `onRowClick`.
`TableColumn` peut être une `CalculatedColumn` (CEL) ou une simple clé de
champ — l'adaptateur doit gérer les deux.

- [ ] **Step 1: Test rouge — tri accessible + sélection de ligne préservée**

  ```tsx
  it("trie via DataTable et émet toujours itemSelected au clic de ligne", async () => {
    const emit = vi.fn();
    render(<TableWidget {...propsWithBus(emit)} />, { wrapper });
    await userEvent.click(screen.getAllByRole("row")[1]);
    expect(emit).toHaveBeenCalledWith("itemSelected", expect.objectContaining({ id: records[0].id }));
  });

  it("rend une colonne calculée CEL via l'adaptateur", () => {
    render(<TableWidget {...propsWithCalculatedColumn} />, { wrapper });
    expect(screen.getByRole("columnheader", { name: /total/i })).toBeInTheDocument();
  });
  ```

  Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx`
  Expected: échec (aucun `role="row"` cliquable actuellement, tri encore
  manuel).

- [ ] **Step 2: Adaptateur de colonnes**

  ```tsx
  function toDataTableColumns(
    columns: TableColumn[],
    records: Record<string, unknown>[],
  ): { key: string; label: string; render: (row: Record<string, unknown>) => React.ReactNode }[] {
    return columns.map((col) => {
      if (isCalculatedColumn(col)) {
        return {
          key: col.name,
          label: col.label ?? col.name,
          render: (row) => String(evaluateCalculatedColumn(col, row, records)),
        };
      }
      return { key: col, label: col, render: (row) => String(row[col] ?? "") };
    });
  }
  ```

  Adapter au nom réel de la fonction d'évaluation CEL déjà utilisée par ce
  fichier pour les colonnes calculées (grep `evaluateCalculatedColumn` ou
  équivalent avant d'écrire — ne pas inventer un nom).

- [ ] **Step 3: Remplacement du `<table>` manuel**

  Remplacer le rendu manuel (lignes ~291-350+) par
  `<DataTable columns={toDataTableColumns(tableColumns, records)} rows={sortedPagedRecords} getRowId={(r) => String(r.id)} sortKey={sortCol} sortDirection={sortDir} onSortChange={toggleSort} onRowClick={selectRecord} />`,
  en conservant `sortCol`/`sortDir`/`toggleSort`/`page`/`pageSize`/
  `selectRecord` tels quels (aucun changement de logique de tri/pagination,
  seulement de rendu).

  Remplacer aussi les 2 occurrences `text-red-600` trouvées dans ce
  fichier par `text-danger` (même règle que Tâche 9 Step 3 — corrigées ici
  car ce fichier est déjà rouvert, pas de second passage nécessaire en
  SP-B12).

  Run: (même commande Step 1) — Expected: 2 tests passent, suite complète
  du fichier toujours verte.

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/builder/widgets/data.tsx shell/src/builder/widgets/data.test.tsx
  git commit -m "$(cat <<'EOF'
  refactor(shell): migre le widget table de l'App Builder sur DataTable

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 25 — SP-B6a : migration vers `createBrowserRouter`/`RouterProvider`

**Files:**
- Modify: `shell/src/shell/routes.tsx`
- Modify: `shell/src/App.tsx`
- Test: `shell/src/shell/routes.test.tsx` (aucun changement attendu —
  vérifie la non-régression)

**Interfaces:**
- Produces: `createAppRouter(): ReturnType<typeof createBrowserRouter>`,
  exporté depuis `routes.tsx`, consommé par `App.tsx`. `AppRoutes()`
  reste exporté et inchangé (compat descendante complète pour
  `routes.test.tsx`).
- Consumes: rien de nouveau.

`useBlocker` (nécessaire Tâche 26) exige un data router. Design retenu :
extraire l'arbre de `<Route>` existant (lignes 236-358 de `routes.tsx`,
`ProtectedLayout` + 4 routes hors-layout) dans une fonction
`routeChildren(): RouteObject[]` réutilisée par `AppRoutes()` (via
`createRoutesFromElements`, zéro changement de comportement) ET par
`createAppRouter()` (via `createBrowserRouter(routeChildren())` pour la
production).

- [ ] **Step 1: Test rouge — `createAppRouter` existe et route vers les mêmes pages que `AppRoutes`**

  ```tsx
  it("createAppRouter résout /bookmarks vers BookmarksPage", async () => {
    const router = createAppRouter({ initialEntries: ["/bookmarks"] });
    render(<RouterProvider router={router} />, { wrapper: AuthAndQueryWrapper });
    expect(await screen.findByTestId("bookmarks-page")).toBeInTheDocument();
  });
  ```

  (`initialEntries` : accepter une option de test qui bascule sur
  `createMemoryRouter` en interne quand fournie, sinon `createBrowserRouter`
  — patron nécessaire pour tester sans naviguer le vrai navigateur.)

  Run: `cd shell && npx vitest run src/shell/routes.test.tsx`
  Expected: échec (`createAppRouter` n'existe pas).

- [ ] **Step 2: Implémentation**

  ```tsx
  import {
    createBrowserRouter,
    createMemoryRouter,
    createRoutesFromElements,
    type RouteObject,
  } from "react-router-dom";

  function routeElements() {
    return (
      <>
        <Route element={<ProtectedLayout />}>
          {/* ... arbre de routes existant, déplacé tel quel depuis AppRoutes ... */}
        </Route>
        {/* ... 4 routes hors-layout existantes, déplacées telles quelles ... */}
      </>
    );
  }

  export function AppRoutes() {
    return (
      <Suspense fallback={<p role="status">Chargement…</p>}>
        <Routes>{routeElements()}</Routes>
      </Suspense>
    );
  }

  export function createAppRouter(options?: { initialEntries?: string[] }) {
    const routes: RouteObject[] = createRoutesFromElements(
      <Route element={<Suspense fallback={<p role="status">Chargement…</p>}><Outlet /></Suspense>}>
        {routeElements()}
      </Route>,
    );
    return options?.initialEntries
      ? createMemoryRouter(routes, { initialEntries: options.initialEntries })
      : createBrowserRouter(routes);
  }
  ```

  Déplacer l'arbre de `<Route>` réel (lignes 236-358) dans
  `routeElements()`, sans changer un seul chemin/élément — copier-coller
  exact, seulement ré-enveloppé dans une fonction.

  Run: (même commande) — Expected: passe, ET `routes.test.tsx` complet
  toujours entièrement vert sans aucune modification de ce fichier de
  test (confirmation de la compat descendante annoncée).

- [ ] **Step 3: Basculer `App.tsx` en production sur le router**

  Remplacer, dans `AppShell` (lignes 25-42) :

  ```tsx
  <BrowserRouter>
    <AppRoutes />
  </BrowserRouter>
  ```

  par :

  ```tsx
  <RouterProvider router={router} />
  ```

  avec `const router = createAppRouter();` défini une seule fois au
  niveau module (comme `queryClient` ligne 23), pas recréé à chaque
  rendu de `AppShell`.

  Run: `cd shell && npx vitest run src/App.test.tsx`
  Expected: vert (adapter le mock de test de `App.tsx` si celui-ci
  mockait `BrowserRouter`/`AppRoutes` directement — vérifier par lecture
  avant d'éditer).

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/shell/routes.tsx shell/src/shell/routes.test.tsx shell/src/App.tsx shell/src/App.test.tsx
  git commit -m "$(cat <<'EOF'
  refactor(shell): bascule sur createBrowserRouter/RouterProvider (prépare useBlocker)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 26 — SP-B6b : `useDirtyGuard`

**Files:**
- Create: `shell/src/lib/useDirtyGuard.ts`
- Create: `shell/src/shell/UnsavedChangesDialog.tsx`
- Test: `shell/src/lib/useDirtyGuard.test.ts`

**Interfaces:**
- Produces: `useDirtyGuard(isDirty: boolean): { blocker: ReturnType<typeof useBlocker>, ConfirmLeaveDialog: () => JSX.Element | null }`,
  consommé par les Tâches 27-28.
- Consumes: `useBlocker` (react-router-dom, nécessite Tâche 25),
  `ConfirmDialog` (Tâche 3's consommateur existant, `ui/kit/ConfirmDialog.tsx`).

- [ ] **Step 1: Test rouge**

  ```tsx
  it("bloque la navigation quand isDirty est vrai, débloque après confirmation", async () => {
    function Harness() {
      const [dirty, setDirty] = useState(true);
      const { ConfirmLeaveDialog } = useDirtyGuard(dirty);
      return (
        <>
          <button onClick={() => setDirty(false)}>marquer propre</button>
          <Link to="/autre">partir</Link>
          <ConfirmLeaveDialog />
        </>
      );
    }
    const router = createMemoryRouter(
      [{ path: "/", element: <Harness /> }, { path: "/autre", element: <p>Autre page</p> }],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);
    await userEvent.click(screen.getByRole("link", { name: "partir" }));
    expect(await screen.findByRole("dialog")).toHaveTextContent(t("navigation.unsavedChangesMessage"));
    await userEvent.click(screen.getByRole("button", { name: t("confirmDialog.confirm") }));
    expect(await screen.findByText("Autre page")).toBeInTheDocument();
  });

  it("ne bloque pas la navigation quand isDirty est faux", async () => {
    function Harness() {
      const { ConfirmLeaveDialog } = useDirtyGuard(false);
      return (
        <>
          <Link to="/autre">partir</Link>
          <ConfirmLeaveDialog />
        </>
      );
    }
    const router = createMemoryRouter(
      [{ path: "/", element: <Harness /> }, { path: "/autre", element: <p>Autre page</p> }],
      { initialEntries: ["/"] },
    );
    render(<RouterProvider router={router} />);
    await userEvent.click(screen.getByRole("link", { name: "partir" }));
    expect(await screen.findByText("Autre page")).toBeInTheDocument();
  });
  ```

  Run: `cd shell && npx vitest run src/lib/useDirtyGuard.test.ts`
  Expected: échec (module absent).

- [ ] **Step 2: Implémentation**

  ```ts
  // shell/src/lib/useDirtyGuard.ts
  // SPDX-License-Identifier: Apache-2.0
  import { useCallback } from "react";
  import { useBlocker } from "react-router-dom";
  import { ConfirmDialog } from "../ui/kit/ConfirmDialog";
  import { t } from "../i18n";

  export function useDirtyGuard(isDirty: boolean) {
    const blocker = useBlocker(
      useCallback(
        ({ currentLocation, nextLocation }) =>
          isDirty && currentLocation.pathname !== nextLocation.pathname,
        [isDirty],
      ),
    );

    function ConfirmLeaveDialog() {
      if (blocker.state !== "blocked") return null;
      return (
        <ConfirmDialog
          open
          title={t("navigation.unsavedChangesTitle")}
          message={t("navigation.unsavedChangesMessage")}
          confirmLabel={t("navigation.leaveAnyway")}
          onCancel={() => blocker.reset()}
          onConfirm={() => blocker.proceed()}
        />
      );
    }

    return { blocker, ConfirmLeaveDialog };
  }
  ```

  Clés i18n :

  ```ts
  "navigation.unsavedChangesTitle": "Modifications non enregistrées",
  "navigation.unsavedChangesMessage": "Vous avez des modifications non enregistrées. Voulez-vous vraiment quitter cette page ?",
  "navigation.leaveAnyway": "Quitter sans enregistrer",
  ```

  Run: (même commande) — Expected: 2 tests passent.

- [ ] **Step 3: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/lib/useDirtyGuard.ts shell/src/lib/useDirtyGuard.test.ts shell/src/i18n/catalog.fr.ts
  git commit -m "$(cat <<'EOF'
  feat(shell): ajoute useDirtyGuard, garde de navigation sur brouillon non enregistré

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 27 — SP-B6c : brancher la garde sur `MapEditorPage`

**Files:**
- Modify: `shell/src/pages/MapEditorPage.tsx`
- Test: `shell/src/pages/MapEditorPage.test.tsx`

**Interfaces:**
- Consumes: `useDirtyGuard` (Tâche 26).

`useUndoableDraft` (confirmé en grounding) n'a pas de concept `isDirty` —
il faut le dériver localement : comparer le `draft` courant à la donnée
serveur chargée (`mapConfigQuery.data`), ou plus simplement suivre si
`undo`/`canUndo` a été franchi depuis le dernier `saveMap` réussi. Design
retenu (le plus simple et robuste) : un état booléen `hasUnsavedChanges`
mis à `true` par `setDraft`, remis à `false` dans `onSuccess` de
`useSaveMap`.

- [ ] **Step 1: Test rouge — navigation bloquée après une modification non enregistrée**

  ```tsx
  it("bloque la navigation après une modification non enregistrée de la carte", async () => {
    renderWithRouter(<MapEditorPage />, { route: "/maps/map-1", otherRoute: "/" });
    await userEvent.click(screen.getByRole("button", { name: /ajouter une couche/i }));
    await userEvent.click(screen.getByRole("link", { name: /retour au catalogue/i }));
    expect(await screen.findByRole("dialog")).toHaveTextContent(t("navigation.unsavedChangesMessage"));
  });

  it("ne bloque pas la navigation juste après une sauvegarde réussie", async () => {
    renderWithRouter(<MapEditorPage />, { route: "/maps/map-1", otherRoute: "/" });
    await userEvent.click(screen.getByRole("button", { name: /ajouter une couche/i }));
    await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
    await waitFor(() => expect(screen.getByText(t("toast.mapSaved"))).toBeInTheDocument());
    await userEvent.click(screen.getByRole("link", { name: /retour au catalogue/i }));
    expect(await screen.findByText(/catalogue/i)).toBeInTheDocument();
  });
  ```

  Adapter au patron réel de rendu-avec-routeur du fichier de test
  (utiliser `createAppRouter({initialEntries: [...]})` de la Tâche 25 ou
  un harnais `MemoryRouter` local équivalent selon ce que le fichier fait
  déjà pour d'autres tests de navigation).

  Run: `cd shell && npx vitest run src/pages/MapEditorPage.test.tsx`
  Expected: échec (aucune garde aujourd'hui).

- [ ] **Step 2: Implémentation**

  Ajouter `const [hasUnsavedChanges, setHasUnsavedChanges] = useState(false);`,
  le passer à `true` dans le `setDraft` enrobé (wrapper local autour de
  `setDraft` de `useUndoableDraft`, utilisé partout où le composant
  modifie le brouillon), le repasser à `false` dans `onSuccess` de la
  mutation de sauvegarde locale à cette page. Appeler
  `const { ConfirmLeaveDialog } = useDirtyGuard(hasUnsavedChanges);` et
  rendre `<ConfirmLeaveDialog />` en fin de JSX du composant.

  Run: (même commande) — Expected: 2 tests passent, suite complète du
  fichier toujours verte.

- [ ] **Step 3: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/pages/MapEditorPage.tsx shell/src/pages/MapEditorPage.test.tsx
  git commit -m "$(cat <<'EOF'
  feat(shell): garde de navigation sur brouillon de carte non enregistré

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 28 — SP-B6d : brancher la garde sur les 4 autres éditeurs

**Files:**
- Modify: `shell/src/pages/DatasetEditPage.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Modify: `shell/src/pages/PipelineBuilderPage.tsx`
- Modify: `shell/src/pages/ReportEditPage.tsx` (ou nom réel — confirmer
  par grep `grep -rln "ReportSchedule" shell/src/pages --include="*.tsx"`)
- Test: fichiers de test correspondants

**Interfaces:**
- Consumes: `useDirtyGuard` (Tâche 26).

- [ ] **Step 1-4** — même patron exact que la Tâche 27, un fichier à la
  fois, un commit par fichier pour garder chaque diff vérifiable
  isolément :

  1. `DatasetEditPage` : test rouge → `hasUnsavedChanges` local → commit.
  2. `AppBuilderPage` : idem — attention, ce fichier a déjà
     `activePageId`/`selectedId` migrés en Tâche 17 vers
     `useUrlSyncedState` ; le `hasUnsavedChanges` ici est une donnée
     distincte (état du `draft` de widgets, pas la sélection UI), ne pas
     les confondre.
  3. `PipelineBuilderPage` : idem.
  4. `ReportEditPage`/nom réel : idem.

  Run après chaque fichier : `cd shell && npx vitest run <fichier>`
  Expected: rouge puis vert à chaque fois.

  Commit après chaque fichier :

  ```bash
  cd /home/lenen/projets/geostudio
  git add <fichier> <fichier>.test.tsx
  git commit -m "$(cat <<'EOF'
  feat(shell): garde de navigation sur brouillon non enregistré (<éditeur>)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

  (4 commits distincts pour cette tâche, un par éditeur — cohérent avec
  la règle "petits, un sujet" de CLAUDE.md.)

---

## Tâche 29 — SP-B12a : tokenisation `AppRuntimePage` + `printLayout`

**Files:**
- Modify: `shell/src/pages/AppRuntimePage.tsx`
- Test: `shell/src/pages/AppRuntimePage.test.tsx`

**Interfaces:**
- Consumes: tokens `--gs-*` déjà définis dans `tokens.css` (pas de
  nouveau token créé).

6 occurrences de couleurs Tailwind littérales dans ce fichier
(grounding). **Distinction à respecter strictement** : ce fichier peut
légitimement contenir des usages `--gs-color-*` du thème d'app runtime
(arbitraire-value) — ne remplacer QUE les classes Tailwind à nom de
palette littéral (`bg-slate-100`, `text-red-500`, etc.), jamais une
classe `[var(--gs-color-*)]`.

- [ ] **Step 1: Énumération précise**

  ```bash
  cd shell && grep -n '\b\(text\|bg\|border\)-\(red\|green\|blue\|yellow\|slate\|gray\|zinc\|neutral\|stone\|emerald\|amber\|orange\|indigo\|violet\|purple\|pink\|rose\|cyan\|sky\|teal\|lime\|white\|black\)\(-[0-9]\+\)\?\(/[0-9]\+\)\?\b' src/pages/AppRuntimePage.tsx
  ```

- [ ] **Step 2: Test rouge (snapshot de classes) — falsification du filet**

  Suivre le patron `expectTokenizedClasses()` déjà établi ailleurs dans le
  dépôt (SP-34, cité au piège n°10 de CLAUDE.md) si un tel helper existe
  déjà (grep `expectTokenizedClasses` dans `shell/src/test/`) ; sinon,
  écrire un test simple par occurrence qui vérifie l'absence de la classe
  littérale et la présence du token attendu sur l'élément rendu. **Avant
  de faire confiance à ce test** : injecter délibérément une classe
  littérale dans le composant, confirmer que le test échoue, puis
  retirer l'injection — ne committer qu'après cette falsification
  positive (piège n°10 CLAUDE.md, un existant a déjà donné un faux
  positif sur ce type de test en SP-29b).

  Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx`
  Expected: échec avant remplacement.

- [ ] **Step 3: Remplacement 1-pour-1**

  Chaque couleur littérale → le token `--gs-*` sémantique le plus proche
  (`text-red-*`→`text-danger`, `bg-slate-100`→`bg-surface` ou
  `bg-raised` selon le contexte visuel réel, `text-gray-500`→`text-ink-3`,
  etc. — décider au cas par cas en regardant le rendu visuel voulu, pas
  une correspondance mécanique aveugle).

  Run: (même commande) — Expected: vert.

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/src/pages/AppRuntimePage.tsx shell/src/pages/AppRuntimePage.test.tsx
  git commit -m "$(cat <<'EOF'
  refactor(shell): tokenise les couleurs Tailwind brutes de AppRuntimePage

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 30 — SP-B12b : tokenisation des 3 pages publiques + `DatasetDownloadButtons`

**Files:**
- Modify: `shell/src/pages/EmbedPage.tsx`
- Modify: (2 autres pages publiques — `SitesPage`/`PublicItemPage`/
  `PublicDatasetPage` ou noms réels, confirmer par grep
  `grep -rln "public" shell/src/pages --include="*.tsx"`)
- Modify: (composant `DatasetDownloadButtons` ou nom réel — confirmer par
  grep `grep -rln "DownloadButtons\|téléchargement" shell/src --include="*.tsx"`)
- Test: fichiers de test correspondants

**Interfaces:**
- Consumes: tokens `--gs-*`.

Même patron exact que la Tâche 29, appliqué fichier par fichier (3
occurrences pour `EmbedPage.tsx` + occurrences des 2 autres pages
publiques + du composant de téléchargement, tous confirmés en grounding
via le décompte initial de 216 occurrences/52 fichiers).

- [ ] **Step 1-4 par fichier** : énumération grep précise → test de
  falsification → remplacement 1-pour-1 → commit séparé par fichier
  (garder les diffs petits et vérifiables, cohérent avec la règle de
  commit CLAUDE.md).

  Run par fichier: `cd shell && npx vitest run <fichier>`
  Expected: rouge puis vert.

  Commit par fichier:

  ```bash
  cd /home/lenen/projets/geostudio
  git add <fichier> <fichier>.test.tsx
  git commit -m "$(cat <<'EOF'
  refactor(shell): tokenise les couleurs Tailwind brutes de <fichier>

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 31 — SP-B12c : balayage repo-wide des couleurs Tailwind brutes restantes

**Files:**
- Modify: les fichiers restants parmi les 52 identifiés en grounding
  (216 occurrences totales, moins celles déjà traitées dans les Tâches
  9, 24, 29, 30) — traités par lots.
- Test: fichiers de test correspondants, par lot.

**Interfaces:**
- Consumes: tokens `--gs-*`.

- [ ] **Step 1: Recompter après les tâches précédentes**

  ```bash
  cd shell && grep -rln '\b\(text\|bg\|border\)-\(red\|green\|blue\|yellow\|slate\|gray\|zinc\|neutral\|stone\|emerald\|amber\|orange\|indigo\|violet\|purple\|pink\|rose\|cyan\|sky\|teal\|lime\|white\|black\)\(-[0-9]\+\)\?\(/[0-9]\+\)\?\b' src \
    --include="*.tsx" | grep -v '\.test\.tsx$' | grep -v '^src/ui/kit/' | grep -v '^src/map/'
  ```

  Confirmer le décompte restant (attendu : significativement < 216 après
  les Tâches 9/24/29/30).

- [ ] **Step 2: Lots de 5-8 fichiers, patron identique à la Tâche 30**

  Pour chaque lot : test de falsification par fichier touché (ou
  extension d'un test existant), remplacement 1-pour-1 vers le token
  sémantique le plus proche, en respectant strictement l'exclusion des
  usages `[var(--gs-color-*)]` (déjà exclus par la regex du Step 1, qui
  ne matche que des noms de palette Tailwind littéraux — ne pas
  l'élargir).

  Run par lot: `cd shell && npx vitest run <fichiers du lot>`
  Expected: vert à chaque lot.

  Commit par lot:

  ```bash
  cd /home/lenen/projets/geostudio
  git add <fichiers du lot>
  git commit -m "$(cat <<'EOF'
  refactor(shell): tokenise les couleurs Tailwind brutes restantes (lot N)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

  Répéter jusqu'à épuisement de la liste du Step 1.

---

## Tâche 32 — SP-B12d : garde-fou anti-régression (script de lint)

**Files:**
- Create: `shell/scripts/check-raw-colors.mjs`
- Modify: `shell/package.json` (script `lint:colors` ou intégré à
  `npm run lint` existant — vérifier la structure de scripts réelle avant
  d'éditer)
- Modify: `.github/workflows/ci.yml` (ajout de l'invocation si pas déjà
  couvert par `npm run lint`)

**Interfaces:**
- Produces: script Node qui échoue (exit 1) si une couleur Tailwind
  littérale est trouvée hors `ui/kit/`, `map/`, fichiers de test, et hors
  toute syntaxe `[var(--gs-color-*)]`.

- [ ] **Step 1: Implémentation**

  ```js
  #!/usr/bin/env node
  // SPDX-License-Identifier: Apache-2.0
  import { readFileSync } from "node:fs";
  import { globSync } from "node:fs";
  import path from "node:path";

  const RAW_COLOR_RE =
    /\b(text|bg|border)-(red|green|blue|yellow|slate|gray|zinc|neutral|stone|emerald|amber|orange|indigo|violet|purple|pink|rose|cyan|sky|teal|lime|white|black)(-[0-9]+)?(\/[0-9]+)?\b/;

  const files = globSync("shell/src/**/*.tsx", { ignore: ["shell/src/**/*.test.tsx", "shell/src/ui/kit/**", "shell/src/map/**"] });
  const offenders = [];
  for (const file of files) {
    const content = readFileSync(file, "utf8");
    const lines = content.split("\n");
    lines.forEach((line, index) => {
      if (RAW_COLOR_RE.test(line)) {
        offenders.push(`${file}:${index + 1}: ${line.trim()}`);
      }
    });
  }
  if (offenders.length > 0) {
    console.error("Couleurs Tailwind brutes détectées hors ui/kit et map/ :");
    offenders.forEach((o) => console.error(`  ${o}`));
    process.exit(1);
  }
  console.log("Aucune couleur Tailwind brute détectée.");
  ```

  Vérifier la version de Node disponible supporte `node:fs` `globSync`
  (Node ≥ 22) — sinon utiliser `fast-glob` déjà présent en dépendance
  (vérifier `package.json` avant de choisir l'implémentation exacte, ne
  pas ajouter une nouvelle dépendance si `fast-glob` ou équivalent existe
  déjà dans le dépôt).

  Run: `cd shell && node scripts/check-raw-colors.mjs`
  Expected: exit 0, "Aucune couleur Tailwind brute détectée." (après les
  Tâches 29-31 — si le script trouve encore des offenders, c'est que le
  balayage 31 n'est pas allé au bout : revenir compléter la Tâche 31
  avant de continuer ici).

- [ ] **Step 2: Falsification (piège n°10 — le script doit exister avant qu'on puisse le falsifier)**

  Maintenant que le script existe (Step 1), créer temporairement un
  fichier de scratch avec une classe `text-red-600` littérale sous
  `shell/src/` (ex. `shell/src/scratch-raw-color-fixture.tsx`), lancer
  `node scripts/check-raw-colors.mjs`, confirmer qu'il échoue (exit 1) en
  nommant ce fichier, puis retirer le fichier de scratch et relancer pour
  confirmer un retour à exit 0 — documenter ce test manuel dans le
  message de commit (pas de fichier de test automatisé requis pour un
  script utilitaire, mais la falsification doit être faite et confirmée
  avant de faire confiance au script).

- [ ] **Step 3: Câblage CI**

  Ajouter `"lint:colors": "node scripts/check-raw-colors.mjs"` à
  `shell/package.json`, l'inclure dans le script `lint` composite s'il en
  existe un (`"lint": "eslint . && node scripts/check-raw-colors.mjs"` ou
  équivalent — vérifier la forme réelle du script `lint` avant d'éditer).

  Run: `cd shell && npm run lint`
  Expected: passe, inclut maintenant la vérification de couleurs.

- [ ] **Step 4: Commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/scripts/check-raw-colors.mjs shell/package.json
  git commit -m "$(cat <<'EOF'
  feat(shell): garde-fou CI contre les couleurs Tailwind brutes hors kit/map

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 33 — filets transverses : plancher d'adoption + interdiction de `window.confirm`

**Files:**
- Create: `shell/scripts/check-no-window-confirm.mjs`
- Modify: `shell/package.json`
- Test: falsification manuelle (même patron que Tâche 32 Step 1)

**Interfaces:**
- Produces: script qui échoue si `window.confirm(` apparaît hors
  `ui/kit/ConfirmDialog.tsx` lui-même et hors fichiers de test.

Referme la classe de défaut de la Tâche 3 : sans ce garde, un futur ajout
peut réintroduire un `window.confirm` sans qu'aucun test ne le remarque.

- [ ] **Step 1: Implémentation**

  ```js
  #!/usr/bin/env node
  // SPDX-License-Identifier: Apache-2.0
  import { readFileSync } from "node:fs";
  import { globSync } from "node:fs";

  const files = globSync("shell/src/**/*.tsx", { ignore: ["shell/src/**/*.test.tsx"] });
  const offenders = [];
  for (const file of files) {
    const content = readFileSync(file, "utf8");
    content.split("\n").forEach((line, index) => {
      if (line.includes("window.confirm(")) {
        offenders.push(`${file}:${index + 1}`);
      }
    });
  }
  if (offenders.length > 0) {
    console.error("window.confirm() détecté — utiliser ConfirmDialog :");
    offenders.forEach((o) => console.error(`  ${o}`));
    process.exit(1);
  }
  console.log("Aucun window.confirm() résiduel.");
  ```

  Run: `cd shell && node scripts/check-no-window-confirm.mjs`
  Expected: exit 0 (après la Tâche 3, les 3 sites migrés + le gap de
  pièce jointe corrigé).

- [ ] **Step 2: Falsification (piège n°10 — le script doit exister avant qu'on puisse le falsifier)**

  Maintenant que le script existe (Step 1), ajouter temporairement un
  `window.confirm("test")` dans un fichier scratch sous `shell/src/`
  (ex. `shell/src/scratch-window-confirm-fixture.tsx`), lancer
  `node scripts/check-no-window-confirm.mjs`, confirmer qu'il échoue en
  nommant ce fichier, puis retirer le fichier de scratch et relancer pour
  confirmer un retour à exit 0.

- [ ] **Step 3: Câblage dans `npm run lint`, commit**

  ```bash
  cd /home/lenen/projets/geostudio
  git add shell/scripts/check-no-window-confirm.mjs shell/package.json
  git commit -m "$(cat <<'EOF'
  feat(shell): garde-fou CI contre la réintroduction de window.confirm

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Tâche 34 — Clôture : suites complètes, régénération, documentation

**Files:**
- Modify: `CLAUDE.md` (une ligne `### Livré`)
- Modify: `docs/revue/2026-09-04-backlog.md` (si des `REV-nnn` de la
  Vague B y sont référencées — vérifier, sinon ne rien changer)
- Modify: `docs/revue/2026-09-24-diagnostic-ui-ux.md` (marquer les 12
  SP-Bx comme traités, si ce document porte un état par item — vérifier
  sa structure avant d'éditer)

- [ ] **Step 1: Suite complète shell + build**

  Run: `cd shell && npx vitest run`
  Expected: entièrement vert, couverture ≥ 88 (`node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold` après nettoyage de `dist/`/`dist-export/`).

  Run: `cd shell && npm run build`
  Expected: `tsc --noEmit` propre, `vite build` réussit, filet de taille
  de bundle (`node scripts/check-bundle-size.mjs`) sous le seuil.

- [ ] **Step 2: Suite E2E complète**

  Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e`
  Expected: entièrement vert (0 échec — CLAUDE.md rappelle qu'il n'y a
  plus d'échec "connu" à imputer). Porter une attention particulière à
  `e2e/quota-guard.spec.ts` (Tâche 8) et à tout test E2E touchant la
  navigation (Tâches 25-28) ou le tri de tableau (Tâches 20-24).

- [ ] **Step 3: Suite cœur (fichier `tiles.py` touché en Tâche 13)**

  Run: `cd core && uv run pytest` (avec `CORE_TEST_DATABASE_URL` pointant
  un postgis-test réel, sinon les tests `@pytest.mark.postgis` de la
  Tâche 13 skippent silencieusement — CLAUDE.md piège documenté).
  Expected: entièrement vert, couverture ≥ 85.

  Run: `cd core && uv run ruff check . && uv run ruff format --check . && uv run lint-imports`
  Expected: propre.

- [ ] **Step 4: Vérifier l'inventaire de fonctionnalités**

  Confirmer, en relisant `core/tests/test_feature_inventory.py`, qu'aucune
  route REST, outil MCP ou route shell nouvelle n'a été ajoutée par ce
  plan (vrai : Tâche 13 modifie un en-tête de réponse sur une route
  existante, toutes les autres tâches sont additives sur des composants
  déjà inventoriés ou strictement internes au shell sans nouvelle route).

  Run: `cd core && PYTHONPATH=. uv run python scripts/feature_health_cli.py --repo .. --check`
  Expected: passe sans modification de
  `docs/revue/inventaire-fonctionnalites.jsonl`. Si la commande échoue en
  signalant une surface non inventoriée, l'ajouter avant de continuer
  (ne pas supposer — vérifier le message d'erreur réel).

- [ ] **Step 5: OpenAPI/types TS**

  Run:
  ```bash
  cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
    uv run python scripts/export_openapi.py /tmp/openapi-final.json
  diff openapi.json /tmp/openapi-final.json
  ```
  Expected: diff vide (confirmé dès la Tâche 13, revérifié ici après
  toutes les autres tâches qui ne touchent pas le cœur). Si non vide,
  régénérer `openapi.json` et `cd shell && npm run gen:api-types` avant
  de committer.

- [ ] **Step 6: `pre-commit` complet**

  Run: `uvx pre-commit run --all-files`
  Expected: 5 hooks passent.

- [ ] **Step 7: CLAUDE.md § Livré**

  Ajouter une ligne sous `### Livré`, style identique aux entrées
  existantes :

  ```
  - **Vague B états système et cohérence** — 12 chantiers (SP-B1→SP-B12) :
    états vides catalogue/admin, `ConfirmDialog` sur 4 sites de
    suppression, notifications de succès (`ToastProvider`), résilience
    réseau (timeout 15s, `CoreUnreachableError`, bannière de
    connectivité), `ApiError` porte le detail RFC 7807 jusqu'à l'UI,
    accessibilité des erreurs de formulaire, `LoadingState` uniforme,
    lisibilité des jobs (libellés traduits, badge de troncature MVT),
    état UI synchronisé à l'URL (`useUrlSyncedState`), tableaux
    accessibles/cliquables (`DataTable`), garde de navigation sur
    brouillon non enregistré (migration `createBrowserRouter`), dernières
    couleurs Tailwind brutes tokenisées + garde-fou CI.
  ```

  Vérifier le garde-fou de taille avant de committer :
  Run: `python3 scripts/check_claude_md_size.py CLAUDE.md .claude-md-size-threshold`
  Expected: sous le seuil.

- [ ] **Step 8: Commit de clôture**

  ```bash
  cd /home/lenen/projets/geostudio
  git add CLAUDE.md
  git commit -m "$(cat <<'EOF'
  docs: clôture Vague B (états système et cohérence)

  Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
  EOF
  )"
  ```

---

## Self-Review

**Couverture de la spec** (12 sections SP-Bx du document source, mappées
aux tâches de ce plan) :

- SP-B1 (états vides) → Tâches 1, 2.
- SP-B2 (confirmations de suppression) → Tâche 3.
- SP-B3 (notifications de succès) → Tâches 4, 5, 6.
- SP-B7 (résilience réseau) → Tâche 7.
- SP-B5 (erreurs serveur lisibles) → Tâche 8.
- SP-B8 (accessibilité des formulaires) → Tâche 9.
- SP-B4 (indicateurs de chargement) → Tâches 10, 11.
- SP-B10 (lisibilité des exécutions asynchrones) → Tâches 12, 13, 14, 15.
- SP-B9 (état UI synchronisé à l'URL) → Tâches 16, 17, 18, 19.
- SP-B11 (tableaux accessibles/cliquables) → Tâches 20, 21, 22, 23, 24.
- SP-B6 (garde de navigation) → Tâches 25, 26, 27, 28.
- SP-B12 (couleurs Tailwind brutes) → Tâches 29, 30, 31, 32.
- Filets transverses non attachés à un seul SP-Bx (plancher
  window.confirm) → Tâche 33.
- Clôture (régénération, doc, suites complètes) → Tâche 34.

Les 12 sections ont chacune au moins une tâche. Aucune section n'est
seulement mentionnée sans tâche d'implémentation associée.

**Balayage de placeholders** : aucune étape de ce plan ne contient de
`// TODO`, de `<...>` non résolu dans un bloc de code exécutable, ni de
"puis faire X" sans le code de X. Les points explicitement laissés à
vérifier à l'exécution (Tâche 15 Step 1 : existence d'un champ de
progression côté cœur ; Tâche 23 Step 1 : nom réel du composant d'aperçu
pipeline ; Tâche 21/22/28 : noms réels de quelques hooks/fichiers) sont
des vérifications par grep explicitement scriptées avec une branche de
sortie documentée (implémenter si trouvé, sinon consigner comme
hors-périmètre) — pas des trous dans le plan, mais des points où le texte
littéral du dépôt doit trancher plutôt qu'une supposition (cohérent avec
le piège n°3 de CLAUDE.md : ne jamais deviner une interface tierce ou un
nom réel).

**Cohérence des types/noms across tâches** — vérifié un par un :
- `EmptyState` (existant, Tâche 1/2/22) : même signature partout,
  `{title, description?, action?}`.
- `ConfirmDialog` (existant, Tâche 3/26) : même signature partout,
  `{open, title, message, confirmLabel, onConfirm, onCancel, pending?}`.
- `useToast`/`ToastProvider` (créés Tâche 4) : consommés identiquement en
  Tâches 5 et 6, import `"../../ui/kit/ToastProvider"` (relatif à
  `api/domains/`) cohérent sur les 2 tâches.
- `CoreUnreachableError` (créé Tâche 7) : consommé par `ConnectivityBanner`
  (Tâche 7 elle-même) — aucune autre tâche ne le réimporte sous un autre
  nom.
- `ApiError` (créé Tâche 8) : même nom/forme (`status`, `detail`) partout
  où mentionné (Tâche 8 uniquement — pas d'autre tâche ne le consomme
  directement dans ce plan, cohérent avec le fait que SP-B5 est
  auto-contenu).
- `LoadingState` (créé Tâche 10) : consommé identiquement Tâche 11, même
  props `{label?}`.
- `jobStatusLabel` (créé Tâche 12) : même signature
  `(status: string) => string` partout où wiré.
- `useUrlSyncedState` (créé Tâche 16) : même signature
  `<T extends string>(paramName, defaultValue) => [T | null, (v: T | null) => void]`
  dans les 3 tâches consommatrices (17, 18, 19) — vérifié que Tâche 19
  utilise bien la même forme de tuple `[value, setValue]`, pas une forme
  différente.
- `SqlHistoryEntry.id`/`findSqlHistoryEntry` (ajoutés Tâche 19) : nom de
  champ et de fonction cohérents entre le Step 1 (test) et le Step 2
  (implémentation) de la même tâche — aucune autre tâche ne les
  re-consomme, pas de risque de divergence inter-tâches.
- `DataTable`/`onRowClick` (étendu Tâche 20) : même prop consommée
  identiquement dans les Tâches 21, 22, 23, 24.
- `createAppRouter`/`AppRoutes` (Tâche 25) : `AppRoutes` reste exporté à
  l'identique (compat `routes.test.tsx`), `createAppRouter` est le seul
  nouveau nom, consommé une seule fois (Tâche 25 Step 3, `App.tsx`) et
  référencé en Tâche 27 comme option de patron de test — cohérent.
- `useDirtyGuard`/`ConfirmLeaveDialog` (créés Tâche 26) : même signature
  `(isDirty: boolean) => { blocker, ConfirmLeaveDialog }` consommée
  identiquement dans les Tâches 27 et 28 (5 éditeurs au total).

**Corrections apportées pendant le cadrage, avant écriture du plan** (à
reporter dans le compte-rendu, ne concernent aucune tâche du plan
lui-même car déjà closes en amont) :
1. Ligne exacte de `<BrowserRouter>` dans `App.tsx` : corrigée à la
   ligne 37 (pas 23) après relecture complète du fichier — utilisée
   correctement dans la Tâche 25.
2. `EmptyState` existe déjà (`ui/kit/EmptyState.tsx`, 2 consommateurs
   réels) — les Tâches 1 et 2 sont donc scopées en pure adoption
   (modification de pages consommatrices), pas en création de composant.
3. `SqlHistoryEntry` n'avait pas de champ `id` — ajout explicite documenté
   dans la Tâche 19 comme extension de périmètre nécessaire (pas dans le
   texte littéral de la spec, mais requis pour que `?historyId=<id>`
   puisse désigner quoi que ce soit).

Aucun gap de couverture de spec résiduel trouvé après cette relecture.
