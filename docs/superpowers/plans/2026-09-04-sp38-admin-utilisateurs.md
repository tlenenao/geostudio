# Page d'administration des utilisateurs (SP-38) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fermer le chantier 4.21 (vague 4) en donnant au shell une page
`/admin/users` qui consomme les routes `GET`/`PATCH /users` déjà livrées et
testées côté cœur par SP-31 — un admin doit pouvoir changer le rôle de
n'importe quel utilisateur du tenant sans toucher une variable
d'environnement.

**Architecture:** Un seul ajout côté cœur (paramètre de recherche `q` sur
`GET /users`, pour que la recherche fonctionne à n'importe quelle échelle de
tenant). Côté shell : trois couches minces empilées sur le patron déjà
établi par `RolesAdminPage` — API layer (`itemClient.ts`/`hooks.ts`), page
`UsersAdminPage.tsx` (`TriptychLayout`, sélecteur de rôle natif inline par
ligne, pas de panneau séparé), câblage de route + lien de découverte depuis
`AdminExtensionsPage`.

**Tech Stack:** Python 3.12 / FastAPI / SQLAlchemy 2.0 / pytest côté cœur ;
React 19 / TypeScript / TanStack Query / Vitest / Testing Library / MSW côté
shell.

## Global Constraints

- Spec de référence : `docs/superpowers/specs/2026-09-04-sp38-admin-utilisateurs-design.md`. Tout ce qui est explicitement hors périmètre en §2 de cette spec (email/nom affiché, création/suppression d'utilisateur, distinction de message par code HTTP, échappement `ILIKE`, `core/app/users/routes.py` dédié) reste hors périmètre de ce plan — ne pas l'ajouter en cours de route.
- **Régénération OpenAPI + types TS obligatoire** (CLAUDE.md, piège n°1) dès que Task 1 ajoute le paramètre `q` à `GET /users` — commande exacte dans Task 1, Step 6 (pas la commande nue, qui échoue).
- **Suite E2E complète à lancer avant clôture** (CLAUDE.md, piège n°6), même si ce plan n'ajoute aucun nouveau spec Playwright — pour attraper une éventuelle régression croisée invisible à Vitest.
- Revue par tâche **et** revue finale de branche (CLAUDE.md, doctrine `subagent-driven-development`) — pas seulement l'une des deux.
- Aucune surface `MapConfig`/`AppConfig` n'est touchée par ce plan — le piège n°5 (`toFrontLayer()`) ne s'applique pas ici.
- Baselines à confirmer par lecture directe des sorties de test avant de les recopier dans `CLAUDE.md` (ne jamais supposer l'arithmétique) :
  - Cœur : **1899 passed / 3 skipped / 0 failed** (entrée SP-35, la plus récente à donner ce chiffre).
  - Shell Vitest : **221 fichiers / 1848 tests**, couverture **90,51 %** (seuil 88, entrée SP-33, inchangée depuis) — ce plan ajoute des tests dans `itemClient.test.ts` et `AdminExtensionsPage.test.tsx` (fichiers existants) et un nouveau fichier `UsersAdminPage.test.tsx`.
  - Shell E2E : **144 tests / 140 passed / 4 skipped / 0 failed** (entrée SP-37) — ce plan n'ajoute aucun spec E2E, ce nombre ne devrait pas bouger ; à confirmer, pas supposer.
- Couverture shell : nettoyer `dist/`/`dist-export/` avant de mesurer (piège documenté 4 fois dans CLAUDE.md).
- Nommer le ledger de session `.superpowers/sdd/sp38-*` si `subagent-driven-development` en crée un (CLAUDE.md, piège n°9 — jamais `task-N-report.md` générique).

---

### Task 1 : Cœur — recherche `q` sur `GET /users`

**Files:**
- Modify: `core/app/users/repository.py`
- Modify: `core/app/auth/routes.py`
- Test: `core/tests/test_users_admin_routes.py`
- Modify (régénération mécanique) : `core/openapi.json`, `shell/src/api/generated/core-schema.d.ts`

**Interfaces:**
- Consumes: rien de nouveau — `list_users()` et `GET /users` existent déjà (SP-31), inchangés hors l'ajout ci-dessous.
- Produces: `list_users(session, *, tenant_id, page, page_size, q=None)` — `q` filtre `User.username` par sous-chaîne insensible à la casse. `GET /users?q=...` — Task 2 consomme cette route par son URL brute, pas par un import Python, aucune interface partagée au-delà de l'URL et de la forme JSON déjà documentée par la spec (`{users: [{id, username, roleSlug}], total}`, inchangée).

- [ ] **Step 1 : écrire le test qui échoue**

Ajouter à la fin de `core/tests/test_users_admin_routes.py` (après `test_patch_user_rejects_an_unknown_role_id`) :

```python
def test_list_users_filters_by_username(env):
    app, client, Session, admin, regular, _roles = env
    with Session() as s:
        get_or_create_user(
            s,
            tenant_id=admin.tenant_id,
            oidc_sub="c",
            username="charlie",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()

    _as(app, admin)
    body = client.get("/users?q=reg").json()
    assert body["total"] == 1
    assert {u["username"] for u in body["users"]} == {"regular"}

    body_ci = client.get("/users?q=REG").json()
    assert body_ci["total"] == 1

    body_all = client.get("/users").json()
    assert body_all["total"] == 3
```

- [ ] **Step 2 : lancer le test, confirmer l'échec**

Run (depuis `core/`) : `uv run pytest tests/test_users_admin_routes.py::test_list_users_filters_by_username -v`
Expected: FAIL — `assert body["total"] == 1` échoue (`q` est aujourd'hui ignoré par la route FastAPI, qui retourne les 3 utilisateurs sans filtrer).

- [ ] **Step 3 : implémenter le filtre dans `list_users()`**

```diff
 def list_users(
-    session: Session, *, tenant_id: str, page: int, page_size: int
+    session: Session, *, tenant_id: str, page: int, page_size: int, q: str | None = None
 ) -> tuple[list[User], int]:
     base = select(User).where(User.tenant_id == tenant_id)
+    if q:
+        base = base.where(User.username.ilike(f"%{q}%"))
     total = session.scalar(select(func.count()).select_from(base.subquery()))
     users = list(
         session.scalars(
             base.order_by(User.username).offset((page - 1) * page_size).limit(page_size)
         ).all()
     )
     return users, total
```

- [ ] **Step 4 : passer `q` depuis la route**

Dans `core/app/auth/routes.py`, fonction `get_users` :

```diff
 @router.get("/users")
 def get_users(
     page: int = 1,
     pageSize: int = 50,
+    q: str | None = None,
     user: User = Depends(get_current_user),
     session: Session = Depends(get_session),
 ) -> dict[str, Any]:
     require_privilege(session, user, Privilege.ADMIN_USERS_MANAGE.value)
-    users, total = list_users(session, tenant_id=user.tenant_id, page=page, page_size=pageSize)
+    users, total = list_users(
+        session, tenant_id=user.tenant_id, page=page, page_size=pageSize, q=q
+    )
     result = []
     for u in users:
         role = get_role(session, tenant_id=user.tenant_id, role_id=u.role_id)
         result.append(_user_json(u, role.slug if role is not None else ""))
     return {"users": result, "total": total}
```

- [ ] **Step 5 : lancer le test, confirmer le succès, puis toute la suite users**

Run (depuis `core/`) :
```bash
uv run pytest tests/test_users_admin_routes.py -v
uv run pytest tests/test_users.py tests/test_users_repository_roles.py -v
```
Expected: tous PASS, y compris les 7 tests pré-existants de `test_users_admin_routes.py` (non-régression).

- [ ] **Step 6 : régénérer OpenAPI + types TS (obligatoire, piège n°1)**

Run (depuis la racine du dépôt) :
```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```
Expected: `core/openapi.json` et `shell/src/api/generated/core-schema.d.ts` changent — `GET /users` gagne un paramètre `q` dans ses `parameters`. Confirmer par :
```bash
git diff --stat core/openapi.json shell/src/api/generated/core-schema.d.ts
```
Expected: les deux fichiers apparaissent modifiés (non vide).

- [ ] **Step 7 : portes de qualité cœur**

Run (depuis `core/`) :
```bash
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot app/admin_tools app/roles
uv run lint-imports
```
Expected: tout passe. `app/users` n'est pas dans le périmètre `mypy --strict` (inchangé par ce plan — ne pas l'y ajouter, hors périmètre).

- [ ] **Step 8 : commit**

```bash
git add core/app/users/repository.py core/app/auth/routes.py \
  core/tests/test_users_admin_routes.py core/openapi.json \
  shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core): ajoute la recherche q à GET /users (SP-38)"
```

---

### Task 2 : Shell — API layer (`types.ts`, `itemClient.ts`, `hooks.ts`, `StaticItemClient.ts`)

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts`
- Modify: `shell/src/api/hooks.ts`
- Modify: `shell/src/staticExport/StaticItemClient.ts`

**Interfaces:**
- Consumes: la route `GET /users`/`PATCH /users/{id}` de Task 1 (URL brute, pas d'import Python).
- Produces: `UserSummary = {id: string, username: string, roleSlug: string}` (export de `types.ts`). `client.listUsers({page, pageSize, q?}): Promise<{users: UserSummary[], total: number}>` et `client.updateUserRole(id, roleId): Promise<UserSummary>` sur `ItemClient`. `useUsers({page, pageSize, q?})` et `useUpdateUserRole()` (mutation, variables `{id, roleId}`) sur `hooks.ts` — Task 3 consomme ces deux hooks et le type `UserSummary` exactement sous ces noms/signatures.

- [ ] **Step 1 : écrire les tests `itemClient` qui échouent**

Ajouter à la fin de `shell/src/api/itemClient.test.ts` (après le test `listRoles/createRole/updateRole/deleteRole round-trip`) :

```ts
test("listUsers/updateUserRole round-trip, avec recherche et pagination dans la query string", async () => {
  let lastUrl = "";
  const users = [
    { id: "u1", username: "alice", roleSlug: "admin" },
    { id: "u2", username: "bob", roleSlug: "reader" },
  ];
  server.use(
    http.get("https://core.test/users", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ users, total: 2 });
    }),
    http.patch("https://core.test/users/u2", async ({ request }) => {
      const body = (await request.json()) as { roleId: string };
      return HttpResponse.json({ id: "u2", username: "bob", roleSlug: body.roleId });
    }),
  );
  const client = makeClient();
  const page = await client.listUsers({ page: 2, pageSize: 25, q: "ali" });
  expect(page).toEqual({ users, total: 2 });
  const url = new URL(lastUrl);
  expect(url.searchParams.get("page")).toBe("2");
  expect(url.searchParams.get("pageSize")).toBe("25");
  expect(url.searchParams.get("q")).toBe("ali");

  const updated = await client.updateUserRole("u2", "admin");
  expect(updated).toEqual({ id: "u2", username: "bob", roleSlug: "admin" });
});

test("listUsers omet q de la query string quand il n'est pas fourni", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/users", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ users: [], total: 0 });
    }),
  );
  await makeClient().listUsers({ page: 1, pageSize: 50 });
  const url = new URL(lastUrl);
  expect(url.searchParams.has("q")).toBe(false);
});
```

- [ ] **Step 2 : lancer les tests, confirmer l'échec**

Run (depuis `shell/`) : `npx vitest run src/api/itemClient.test.ts -t "listUsers"`
Expected: FAIL — `client.listUsers is not a function` (la méthode n'existe pas encore).

- [ ] **Step 3 : ajouter le type `UserSummary` et étendre l'interface `ItemClient`**

Dans `shell/src/api/types.ts`, juste après le type `Role` (après la ligne `};` qui ferme `Role`, avant `PrivilegeCatalogEntry`) :

```diff
 export type Role = {
   id: string;
   name: string;
   slug: string;
   isBuiltIn: boolean;
   privileges: string[];
 };

+export type UserSummary = {
+  id: string;
+  username: string;
+  roleSlug: string;
+};
+
 export type PrivilegeCatalogEntry = {
```

Puis dans l'interface `ItemClient`, juste après `deleteRole(id: string): Promise<void>;` :

```diff
   deleteRole(id: string): Promise<void>;
+  listUsers(params: {
+    page: number;
+    pageSize: number;
+    q?: string;
+  }): Promise<{ users: UserSummary[]; total: number }>;
+  updateUserRole(id: string, roleId: string): Promise<UserSummary>;
   getInstanceInfo(): Promise<InstanceInfo>;
```

- [ ] **Step 4 : implémenter dans `itemClient.ts`**

Ajouter `UserSummary` à l'import de types (bloc alphabétique en tête de fichier, entre `UpdatePatch` et `Variable`) :

```diff
   UpdatePatch,
+  UserSummary,
   Variable,
 } from "./types";
```

Puis implémenter juste après `deleteRole`, avant `getInstanceInfo` (~ligne 580) :

```diff
     async deleteRole(id: string): Promise<void> {
       await request<void>("DELETE", `/roles/${id}`);
     },

+    async listUsers(params: {
+      page: number;
+      pageSize: number;
+      q?: string;
+    }): Promise<{ users: UserSummary[]; total: number }> {
+      const query = new URLSearchParams({
+        page: String(params.page),
+        pageSize: String(params.pageSize),
+      });
+      if (params.q) query.set("q", params.q);
+      return request<{ users: UserSummary[]; total: number }>(
+        "GET",
+        `/users?${query.toString()}`,
+      );
+    },
+
+    async updateUserRole(id: string, roleId: string): Promise<UserSummary> {
+      return request<UserSummary>("PATCH", `/users/${id}`, { roleId });
+    },
+
     async getInstanceInfo(): Promise<InstanceInfo> {
       return request<InstanceInfo>("GET", "/instance");
     },
```

- [ ] **Step 5 : lancer les tests, confirmer le succès**

Run (depuis `shell/`) : `npx vitest run src/api/itemClient.test.ts`
Expected: PASS, y compris les deux nouveaux tests et tous les tests pré-existants du fichier (non-régression).

- [ ] **Step 6 : stub `StaticItemClient` (sinon `tsc --noEmit` échoue — `ItemClient` exige les deux méthodes)**

Dans `shell/src/staticExport/StaticItemClient.ts`, juste après le stub `deleteRole` :

```diff
     async deleteRole(..._args: unknown[]) {
       return unsupported();
     },
+    async listUsers(..._args: unknown[]) {
+      return unsupported();
+    },
+    async updateUserRole(..._args: unknown[]) {
+      return unsupported();
+    },
     // getAuthToken?() et getCoreUrl?() sont optionnels sur ItemClient et
```

- [ ] **Step 7 : ajouter les hooks React Query**

Pas d'ajout à l'import de types de `hooks.ts` — `UserSummary` n'y est référencé par aucun des deux hooks ci-dessous (le type de retour de `useUsers`/`useUpdateUserRole` est inféré depuis `client.listUsers`/`client.updateUserRole`, jamais annoté explicitement). L'ajouter serait un import inutilisé : `noUnusedLocals: true` (`shell/tsconfig.app.json`) ferait échouer `tsc --noEmit` à l'étape suivante — vérifié avant d'écrire ce plan, ne pas l'ajouter.

Ajouter, juste après `useDeleteRole` (avant `useInstanceInfo`) :

```ts
export function useUsers(params: { page: number; pageSize: number; q?: string }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["users", params],
    queryFn: () => client.listUsers(params),
  });
}

export function useUpdateUserRole() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: { id: string; roleId: string }) =>
      client.updateUserRole(vars.id, vars.roleId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["users"] });
    },
  });
}
```

- [ ] **Step 8 : vérification de type et suite complète**

Run (depuis `shell/`) :
```bash
npx tsc --noEmit
npx vitest run src/api/itemClient.test.ts src/api/hooks.ts 2>/dev/null; npx vitest run src/staticExport/StaticItemClient.test.ts
```
Expected: `tsc --noEmit` propre (confirme que `StaticItemClient` satisfait bien l'interface `ItemClient` étendue). `StaticItemClient.test.ts` : PASS, même nombre de tests qu'avant (ce plan n'y ajoute aucun test, cf. Step 6 — pas de test dédié requis, aucun test existant du fichier n'énumère les méthodes de façon réflexive, vérifié par lecture directe avant ce plan).

- [ ] **Step 9 : commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts \
  shell/src/api/hooks.ts shell/src/staticExport/StaticItemClient.ts
git commit -m "feat(shell): ajoute listUsers/updateUserRole à l'ItemClient (SP-38)"
```

---

### Task 3 : `UsersAdminPage`

**Files:**
- Create: `shell/src/pages/UsersAdminPage.tsx`
- Test: `shell/src/pages/UsersAdminPage.test.tsx`

**Interfaces:**
- Consumes: `useUsers`, `useUpdateUserRole` (`../api/hooks`, Task 2), `useRoles` (`../api/hooks`, préexistant), `UserSummary`/`Role` (`../api/types`), `Button`/`Input`/`Panel` (`../ui/kit/*`), `TriptychLayout` (`../shell/chrome/TriptychLayout`).
- Produces: `export function UsersAdminPage()` — Task 4 l'importe et la monte sur la route `/admin/users`.

- [ ] **Step 1 : écrire le fichier de test (échouera — le composant n'existe pas)**

Créer `shell/src/pages/UsersAdminPage.test.tsx` :

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
import { UsersAdminPage } from "./UsersAdminPage";

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
          <UsersAdminPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const ROLES = [
  { id: "role-admin", name: "Administrateur", slug: "admin", isBuiltIn: true, privileges: [] },
  { id: "role-reader", name: "Lecteur", slug: "reader", isBuiltIn: true, privileges: [] },
];
const USERS = [
  { id: "u1", username: "alice", roleSlug: "admin" },
  { id: "u2", username: "bob", roleSlug: "reader" },
];

test("affiche la liste des utilisateurs avec le rôle courant sélectionné", async () => {
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", () => HttpResponse.json({ users: USERS, total: 2 })),
  );
  render(<Harness />);
  await screen.findByText("alice");
  expect(screen.getByLabelText("Rôle de alice")).toHaveValue("role-admin");
  expect(screen.getByLabelText("Rôle de bob")).toHaveValue("role-reader");
});

test("changer le rôle d'un utilisateur appelle PATCH /users/{id} avec le roleId choisi", async () => {
  let patchedBody: unknown = null;
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", () => HttpResponse.json({ users: USERS, total: 2 })),
    http.patch("https://core.test/users/u2", async ({ request }) => {
      patchedBody = await request.json();
      return HttpResponse.json({ id: "u2", username: "bob", roleSlug: "admin" });
    }),
  );
  render(<Harness />);
  await screen.findByText("bob");
  await userEvent.selectOptions(screen.getByLabelText("Rôle de bob"), "role-admin");
  await waitFor(() => expect(patchedBody).toEqual({ roleId: "role-admin" }));
});

test("un changement de rôle refusé affiche une erreur sur la bonne ligne, sans affecter les autres", async () => {
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", () => HttpResponse.json({ users: USERS, total: 2 })),
    http.patch("https://core.test/users/u1", () => new HttpResponse(null, { status: 409 })),
  );
  render(<Harness />);
  await screen.findByText("alice");
  await userEvent.selectOptions(screen.getByLabelText("Rôle de alice"), "role-reader");

  const aliceRow = screen.getByText("alice").closest("tr") as HTMLElement;
  await waitFor(() =>
    expect(within(aliceRow).getByText("Échec de la mise à jour du rôle.")).toBeInTheDocument(),
  );
  const bobRow = screen.getByText("bob").closest("tr") as HTMLElement;
  expect(within(bobRow).queryByText("Échec de la mise à jour du rôle.")).not.toBeInTheDocument();
  // Le select revient à la valeur d'avant la tentative (donnée serveur inchangée).
  expect(screen.getByLabelText("Rôle de alice")).toHaveValue("role-admin");
});

test("la recherche interroge /users avec q et remet la page à 1", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ users: USERS, total: 2 });
    }),
  );
  render(<Harness />);
  await screen.findByText("alice");
  await userEvent.type(screen.getByLabelText("Rechercher"), "ali");
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("q")).toBe("ali"));
  expect(new URL(lastUrl).searchParams.get("page")).toBe("1");
});

test("pagination : Précédent désactivé en page 1, Suivant désactivé quand tout est chargé", async () => {
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", () => HttpResponse.json({ users: USERS, total: 2 })),
  );
  render(<Harness />);
  await screen.findByText("alice");
  expect(screen.getByRole("button", { name: "Précédent" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
});

test("pagination : un clic sur Suivant redemande la page 2", async () => {
  let lastPage = "";
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", ({ request }) => {
      lastPage = new URL(request.url).searchParams.get("page") ?? "";
      return HttpResponse.json({ users: USERS, total: 120 });
    }),
  );
  render(<Harness />);
  await screen.findByText("alice");
  expect(screen.getByRole("button", { name: "Suivant" })).toBeEnabled();
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  await waitFor(() => expect(lastPage).toBe("2"));
});

test("le volet Détail explique l'invariant anti-lockout", async () => {
  server.use(
    http.get("https://core.test/roles", () => HttpResponse.json(ROLES)),
    http.get("https://core.test/users", () => HttpResponse.json({ users: USERS, total: 2 })),
  );
  render(<Harness />);
  await screen.findByText("alice");
  expect(
    screen.getByText(/dernier titulaire de la gestion des rôles et des utilisateurs/i),
  ).toBeInTheDocument();
});
```

- [ ] **Step 2 : lancer les tests, confirmer l'échec**

Run (depuis `shell/`) : `npx vitest run src/pages/UsersAdminPage.test.tsx`
Expected: FAIL — `Failed to resolve import "./UsersAdminPage"` (le fichier n'existe pas encore).

- [ ] **Step 3 : créer `UsersAdminPage.tsx`**

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Link } from "react-router-dom";
import { useRoles, useUpdateUserRole, useUsers } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Input } from "../ui/kit/Input";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

const PAGE_SIZE = 50;

export function UsersAdminPage() {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [rowError, setRowError] = useState<{ userId: string; message: string } | null>(null);

  const usersQuery = useUsers({ page, pageSize: PAGE_SIZE, q: q || undefined });
  const rolesQuery = useRoles();
  const updateUserRole = useUpdateUserRole();

  const totalPages = usersQuery.data
    ? Math.max(1, Math.ceil(usersQuery.data.total / PAGE_SIZE))
    : 1;

  async function handleRoleChange(userId: string, roleId: string) {
    setRowError(null);
    try {
      await updateUserRole.mutateAsync({ id: userId, roleId });
    } catch {
      setRowError({ userId, message: "Échec de la mise à jour du rôle." });
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
          id: "users",
          label: "Utilisateurs",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">Utilisateurs</h1>
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
              {usersQuery.isLoading && <p role="status">Chargement…</p>}
              {usersQuery.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec du chargement des utilisateurs.
                </p>
              )}
              {usersQuery.data && rolesQuery.data && (
                <table className="w-full text-left text-sm">
                  <thead>
                    <tr className="border-b border-rule">
                      <th className="py-2 text-ink">Nom d&apos;utilisateur</th>
                      <th className="py-2 text-ink">Rôle</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usersQuery.data.users.map((u) => {
                      const currentRole = rolesQuery.data.find((r) => r.slug === u.roleSlug);
                      const pending =
                        updateUserRole.isPending && updateUserRole.variables?.id === u.id;
                      return (
                        <tr key={u.id} className="border-b border-rule-2">
                          <td className="py-2 text-ink">{u.username}</td>
                          <td className="py-2">
                            <select
                              aria-label={`Rôle de ${u.username}`}
                              className="h-9 rounded-md border border-rule bg-surface px-2 text-sm text-ink"
                              value={currentRole?.id ?? ""}
                              disabled={pending}
                              onChange={(e) => void handleRoleChange(u.id, e.target.value)}
                            >
                              {rolesQuery.data.map((role) => (
                                <option key={role.id} value={role.id}>
                                  {role.name}
                                </option>
                              ))}
                            </select>
                            {rowError?.userId === u.id && (
                              <p role="alert" className="mt-1 text-xs text-danger">
                                {rowError.message}
                              </p>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
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
          id: "help",
          label: "Détail",
          content: (
            <div className="flex flex-col gap-2 p-3 text-sm text-ink-2">
              <p>
                Le dernier titulaire de la gestion des rôles et des utilisateurs ne peut pas être
                rétrogradé : la tentative échoue pour préserver au moins un compte capable
                d&apos;administrer le tenant.
              </p>
            </div>
          ),
        }}
      />
    </div>
  );
}
```

- [ ] **Step 4 : lancer les tests, confirmer le succès**

Run (depuis `shell/`) : `npx vitest run src/pages/UsersAdminPage.test.tsx`
Expected: PASS — les 7 tests.

- [ ] **Step 5 : vérification de type**

Run (depuis `shell/`) : `npx tsc --noEmit`
Expected: propre.

- [ ] **Step 6 : commit**

```bash
git add shell/src/pages/UsersAdminPage.tsx shell/src/pages/UsersAdminPage.test.tsx
git commit -m "feat(shell): ajoute UsersAdminPage (SP-38)"
```

---

### Task 4 : câblage de route + lien de découverte

**Files:**
- Modify: `shell/src/shell/routes.tsx`
- Modify: `shell/src/pages/AdminExtensionsPage.tsx`
- Modify: `shell/src/pages/AdminExtensionsPage.test.tsx`

**Interfaces:**
- Consumes: `UsersAdminPage` (Task 3).
- Produces: rien de consommé par une tâche suivante — tâche terminale de câblage.

- [ ] **Step 1 : écrire le test du lien qui échoue**

Dans `shell/src/pages/AdminExtensionsPage.test.tsx`, ajouter juste après le test `"le volet Catalogue propose un lien vers /admin/roles (RolesAdminPage sinon inatteignable)"` :

```tsx
test("le volet Catalogue propose un lien vers /admin/users (UsersAdminPage sinon inatteignable)", async () => {
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  await screen.findByRole("table");
  expect(screen.getByRole("link", { name: "Utilisateurs →" })).toHaveAttribute(
    "href",
    "/admin/users",
  );
});
```

- [ ] **Step 2 : lancer le test, confirmer l'échec**

Run (depuis `shell/`) : `npx vitest run src/pages/AdminExtensionsPage.test.tsx -t "admin/users"`
Expected: FAIL — le lien n'existe pas.

- [ ] **Step 3 : ajouter le lien dans `AdminExtensionsPage.tsx`**

```diff
               <Link to="/admin/roles" className="text-accent hover:underline">
                 Rôles et privilèges →
               </Link>
+              <Link to="/admin/users" className="text-accent hover:underline">
+                Utilisateurs →
+              </Link>
```

- [ ] **Step 4 : lancer le test, confirmer le succès, puis toute la suite du fichier**

Run (depuis `shell/`) : `npx vitest run src/pages/AdminExtensionsPage.test.tsx`
Expected: PASS, tous les tests du fichier (non-régression).

- [ ] **Step 5 : câbler la route `/admin/users`**

Dans `shell/src/shell/routes.tsx`, ajouter l'import (bloc d'imports de pages, juste après `RolesAdminPage`) :

```diff
 import { RolesAdminPage } from "../pages/RolesAdminPage";
+import { UsersAdminPage } from "../pages/UsersAdminPage";
 import { KitGalleryPage } from "../pages/KitGalleryPage";
```

Puis ajouter la route, juste après le bloc `/admin/roles` et avant `/admin/infrastructure` :

```diff
         <Route
           path="/admin/roles"
           element={
             <RequirePrivilege
               privilege="admin.roles.manage"
               deniedMessage="Accès réservé à la gestion des rôles."
             >
               <RolesAdminPage />
             </RequirePrivilege>
           }
         />
+        <Route
+          path="/admin/users"
+          element={
+            <RequirePrivilege
+              privilege="admin.users.manage"
+              deniedMessage="Accès réservé à la gestion des utilisateurs."
+            >
+              <UsersAdminPage />
+            </RequirePrivilege>
+          }
+        />
         <Route
           path="/admin/infrastructure"
```

Pas de test dédié dans `routes.test.tsx` pour cette route — même précédent que `/admin/roles`, `/admin/collections`, `/admin/harvest`, `/admin/infrastructure`, aucune n'y a de test (seule `/admin/extensions`, la page hub mockée dans ce fichier, en a un). Confirmer ce précédent avant de considérer cette étape terminée :

Run : `grep -n "admin/roles\|admin/collections\|admin/harvest\|admin/infrastructure" shell/src/shell/routes.test.tsx`
Expected: aucune correspondance (confirme qu'aucune de ces routes n'y est testée individuellement).

- [ ] **Step 6 : vérification de type et suite complète des fichiers touchés**

Run (depuis `shell/`) :
```bash
npx tsc --noEmit
npx vitest run src/shell/routes.test.tsx src/pages/AdminExtensionsPage.test.tsx src/pages/UsersAdminPage.test.tsx
```
Expected: tout PASS.

- [ ] **Step 7 : commit**

```bash
git add shell/src/shell/routes.tsx shell/src/pages/AdminExtensionsPage.tsx \
  shell/src/pages/AdminExtensionsPage.test.tsx
git commit -m "feat(shell): câble /admin/users et le lien de découverte depuis AdminExtensionsPage (SP-38)"
```

---

### Task 5 : vérification finale et `CLAUDE.md`

**Files:**
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: l'état final de toutes les tâches précédentes.
- Produces: rien (tâche terminale).

- [ ] **Step 1 : suite cœur complète**

Run (depuis `core/`) : `uv run pytest`
Expected: pas de nouvel échec par rapport à la baseline (1899 passed / 3 skipped / 0 failed, cf. Global Constraints) — +1 test par rapport à cette baseline (celui de Task 1). Lire le compte réel affiché, ne pas le recalculer de tête.

- [ ] **Step 2 : suite shell Vitest complète, avec couverture**

Run (depuis `shell/`) :
```bash
rm -rf dist dist-export
npx vitest run --coverage
node scripts/check-coverage.mjs coverage/coverage-summary.json .coverage-threshold
```
Expected: aucun échec, couverture ≥ 88 (baseline 90,51 %, ce plan ajoute des tests dans des fichiers déjà couverts et un nouveau fichier entièrement testé — pas de régression attendue, à confirmer).

- [ ] **Step 3 : `npm run build`**

Run (depuis `shell/`) : `npm run build`
Expected: propre (`tsc --noEmit` + `vite build`).

- [ ] **Step 4 : suite E2E complète (piège n°6 — même sans nouveau spec)**

Run (depuis `shell/`) : `npm run e2e`
Expected: même compte que la baseline (144 tests / 140 passed / 4 skipped / 0 failed) — ce plan n'ajoute ni ne retire de spec E2E. Lire `test-results/.last-run.json` pour le compte exact, pas la fin tronquée du reporter `list` (CLAUDE.md, entrée SP-31). Si le compte diffère, investiguer avant de continuer — ne pas l'attribuer par défaut à une session concurrente.

- [ ] **Step 5 : (recommandé, non bloquant) contrôle manuel via un backend réel**

Si une stack `docker compose up -d` est disponible et déjà démarrée dans cet environnement : se connecter en admin, ouvrir `/admin/extensions`, cliquer « Utilisateurs → », vérifier que la liste se charge, changer le rôle d'un utilisateur non-admin, vérifier que la ligne se met à jour. Si la stack n'est pas disponible dans cet environnement, ne pas la démarrer spécialement pour ce plan (chantier UI de faible risque, déjà couvert par les tests d'intégration cœur en TestClient et les tests shell mockés MSW ci-dessus) — noter l'omission dans le rapport de tâche plutôt que prétendre l'avoir fait.

- [ ] **Step 6 : ajouter l'entrée `### Livré` SP-38 dans `CLAUDE.md`**

Lire d'abord l'état actuel de `### Livré` et `### À venir` dans `CLAUDE.md` (une autre session peut l'avoir modifié depuis l'écriture de ce plan — CLAUDE.md, piège n°9). Insérer une nouvelle entrée après la dernière entrée `### Livré` existante (à ce jour, SP-37), dans le même style dense que ses voisines, couvrant exactement :

1. Ce que ce plan ferme : le chantier 4.21 de la vague 4 (`docs/vision/2026-08-20-revue-projet-et-plan-daction.md`) — le cœur avait déjà `GET`/`PATCH /users` (livrés et testés par SP-31, sans que son entrée CLAUDE.md le documente comme tel) ; seule l'UI manquait.
2. L'unique ajout côté cœur : le paramètre de recherche `q` sur `GET /users`/`list_users()`, nécessaire pour que la recherche fonctionne à n'importe quelle échelle de tenant (pas un filtrage côté client sur une seule page).
3. La page `UsersAdminPage` (`/admin/users`, `RequirePrivilege admin.users.manage`) : sélecteur de rôle natif inline par ligne, recherche, pagination Précédent/Suivant, panneau d'aide anti-lockout statique — patron `TriptychLayout` identique à `RolesAdminPage`, découverte depuis `AdminExtensionsPage`.
4. Les comptes réels obtenus aux Steps 1, 2 et 4 ci-dessus (ne pas recopier les nombres prédits par ce plan tels quels — écrire les nombres effectivement observés).
5. Terminer par **Ready to merge.** si rien de bloquant n'a été trouvé, sinon lister ce qui reste.

- [ ] **Step 7 : retirer 4.21 de toute mention de suivi si elle apparaît dans `### À venir`**

Run : `grep -n "4.21\|Gestion des utilisateurs et des rôles" CLAUDE.md`
Expected selon le résultat : si une ligne de suivi non bloquant mentionne encore 4.21 comme ouvert, la retirer ou la corriger ; sinon (le plus probable — cette entrée n'apparaissait dans aucune liste de suivi avant ce plan, seulement dans `docs/vision/2026-08-20-revue-projet-et-plan-daction.md`, qui n'est pas modifié par ce plan), ne rien changer de plus.

- [ ] **Step 8 : commit**

```bash
git add CLAUDE.md
git commit -m "docs: clôture le chantier 4.21 dans CLAUDE.md — page d'administration des utilisateurs (SP-38)"
```

---

## Self-review notes (for the plan author, not a task)

- Spec coverage : §2.1 (recherche `q` cœur) → Task 1. §2.2 (API layer shell) → Task 2. §2.3 (page, sélecteur inline, aide anti-lockout) → Task 3. §2.4 (erreur générique par ligne) → Task 3 Step 3 (`rowError`) + test dédié. §2.5 (route) → Task 4 Step 5. §2.6 (lien de découverte) → Task 4 Steps 1-4. §2.7/§5 (CLAUDE.md) → Task 5. §3 (mécanisme recherche/pagination/select inline) → Task 1 Step 3, Task 3 Step 3. §4 (tests) → chaque tâche a son TDD dédié ; §4.4 (pas de nouveau spec E2E) → confirmé explicitement en Task 4 Step 5 et Task 5 Step 4. §4.6 (régénération OpenAPI) → Task 1 Step 6. §5 (critères de sortie) → couverts par Task 3 (changement de rôle bout en bout), Task 1 (recherche à l'échelle), Task 4 (découverte), Task 5 (suites + CLAUDE.md).
- Type/name consistency : `UserSummary` (Task 2) utilisé tel quel en Task 3 (`usersQuery.data.users: UserSummary[]`). `useUsers`/`useUpdateUserRole` (Task 2) consommés sous ces noms exacts en Task 3. `client.listUsers`/`client.updateUserRole` (Task 2, `itemClient.ts` + interface `types.ts` + stub `StaticItemClient.ts`) — les trois signatures vérifiées identiques. La route `/admin/users` (Task 4) et le privilège `admin.users.manage` (déjà défini côté cœur, `core/app/roles/privileges.py:17`, inchangé par ce plan) correspondent au `RequirePrivilege privilege="admin.users.manage"` de Task 3's test implicite (le composant lui-même ne vérifie pas le privilège — c'est `RequirePrivilege`, au niveau route, qui le fait, comme pour les 5 autres routes `/admin/*`).
- Pas de placeholder : chaque étape de code montre le diff/contenu complet, aucune étape ne dit "ajouter la gestion d'erreur appropriée" sans montrer le code.
