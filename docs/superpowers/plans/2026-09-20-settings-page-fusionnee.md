# Page Paramètres détaillée, fusionnée avec Administration — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remplacer la page `/settings` vide (« bientôt disponible ») par une vraie page Paramètres (profil, préférence de notifications, lien de compte Keycloak), et fusionner la navigation « Administration »/« Paramètres » en un seul point d'entrée toujours visible, dont le contenu (7 destinations admin) reste filtré par privilège.

**Architecture:** Travail shell-only (React/TypeScript), aucune route ni modèle du cœur ne change — pas de régénération OpenAPI/TS nécessaire. Cinq unités indépendantes : (1) un contexte React pour exposer la config runtime (`oidcAuthority`/`authMode`) aux pages, (2) le renommage de `AdminNav` en `SettingsNav` avec une entrée « Général » toujours visible, (3) la page `SettingsPage` elle-même, (4) la fusion du domaine `admin` dans `settings` (`capabilities.ts`/`domainRoutes.ts`), (5) les tests E2E de bout en bout.

**Tech Stack:** React 18, TypeScript, React Router, TanStack Query, Radix UI (`ui/kit/Radio`), Vitest + Testing Library + MSW, Playwright.

## Global Constraints

- Tout texte utilisateur passe par `t("clé", params?)` et une entrée dans `shell/src/i18n/catalog.fr.ts` — jamais de chaîne française codée en dur (`npm run lint` fait échouer la CI sinon, cf. `shell/scripts/check-i18n-coverage.mjs`).
- Couleurs/espacements via les classes Tailwind déjà tokenisées du dépôt (`text-ink`, `text-ink-2`, `border-rule`, `text-accent`, `text-danger`, …) — jamais une couleur Tailwind brute.
- Aucun changement de route/modèle côté `core/` : ne pas régénérer l'OpenAPI, ce plan n'y touche pas.
- Aucune URL `/admin/*` ne change. Aucun privilège n'est ajouté, retiré ou renommé côté cœur (`core/app/roles/privileges.py` reste intact).
- Commandes de vérification (depuis `shell/`) : `npx vitest run <fichier>` par tâche, `npm test` en fin de plan, `npm run lint`, `npx playwright test e2e/<fichier>.spec.ts` pour la tâche E2E.
- Les 7 pages `/admin/*` existantes ne changent pas de contenu, seulement leur import de `AdminNav` → `SettingsNav` (Task 2).

---

## Task 1: `ConfigContext` — exposer `AppConfig` aux pages via un hook

Aujourd'hui, la config runtime (`AppConfig`, `shell/src/config.ts`) n'existe que comme variable de module dans `shell/src/App.tsx` (`const config = loadConfig(...)`), jamais exportée ni passée par contexte — seul `AuthProvider` la reçoit en prop. La page Paramètres a besoin de `config.authMode` (masquer le lien de compte en mode mock) et `config.oidcAuthority` (construire l'URL de la console de compte) depuis une page de route, profondément dans l'arbre. Ce contexte suit exactement le patron déjà utilisé par `shell/src/api/ItemClientProvider.tsx` (contexte + hook qui lève si absent de l'arbre).

**Files:**
- Create: `shell/src/ConfigContext.tsx`
- Create: `shell/src/ConfigContext.test.tsx`
- Modify: `shell/src/App.tsx`

**Interfaces:**
- Produces: `ConfigProvider({ config: AppConfig, children: React.ReactNode })`, `useConfig(): AppConfig` (lève `Error("useConfig must be used within a ConfigProvider")` si appelé hors provider).
- Consumes: `AppConfig` (type existant, `shell/src/config.ts`).

- [ ] **Step 1: Write the failing test**

Create `shell/src/ConfigContext.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import { ConfigProvider, useConfig } from "./ConfigContext";
import type { AppConfig } from "./config";

const CONFIG: AppConfig = {
  coreUrl: "https://core.test",
  oidcAuthority: "https://kc.test/realms/geostudio",
  oidcClientId: "shell",
  oidcRedirectUri: "https://app.test/callback",
  authMode: "oidc",
};

function Consumer() {
  const config = useConfig();
  return <span>{config.oidcAuthority}</span>;
}

test("useConfig retourne la config fournie par ConfigProvider", () => {
  render(
    <ConfigProvider config={CONFIG}>
      <Consumer />
    </ConfigProvider>,
  );
  expect(screen.getByText("https://kc.test/realms/geostudio")).toBeInTheDocument();
});

test("useConfig lève une erreur sans ConfigProvider", () => {
  const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});
  expect(() => render(<Consumer />)).toThrow("useConfig must be used within a ConfigProvider");
  consoleError.mockRestore();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run (from `shell/`): `npx vitest run src/ConfigContext.test.tsx`
Expected: FAIL — `Cannot find module './ConfigContext'`.

- [ ] **Step 3: Write minimal implementation**

Create `shell/src/ConfigContext.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext } from "react";
import type { AppConfig } from "./config";

const ConfigContext = createContext<AppConfig | null>(null);

export function ConfigProvider({
  config,
  children,
}: {
  config: AppConfig;
  children: React.ReactNode;
}) {
  return <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>;
}

export function useConfig(): AppConfig {
  const config = useContext(ConfigContext);
  if (!config) {
    throw new Error("useConfig must be used within a ConfigProvider");
  }
  return config;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npx vitest run src/ConfigContext.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Wire the provider into `App.tsx`**

Read `shell/src/App.tsx` first. Apply these two edits:

Edit 1 — add the import, right after the existing `loadConfig` import:

```ts
import { loadConfig } from "./config";
import { ConfigProvider } from "./ConfigContext";
import { AuthProvider } from "./auth/AuthProvider";
```

Edit 2 — wrap `<AppShell />` so every route can call `useConfig()`:

Old:
```tsx
          <AuthProvider config={config}>
            <QueryClientProvider client={queryClient}>
              <AppShell />
            </QueryClientProvider>
          </AuthProvider>
```

New:
```tsx
          <AuthProvider config={config}>
            <QueryClientProvider client={queryClient}>
              <ConfigProvider config={config}>
                <AppShell />
              </ConfigProvider>
            </QueryClientProvider>
          </AuthProvider>
```

- [ ] **Step 6: Confirm nothing else broke**

Run: `npx vitest run src/App.test.tsx`
Expected: PASS — `App.test.tsx` renders `AppLayout` directly (its own harness), never the real `App`/`config` singleton, so this change cannot affect it; this just confirms that assumption still holds.

- [ ] **Step 7: Commit**

```bash
git add src/ConfigContext.tsx src/ConfigContext.test.tsx src/App.tsx
git commit -m "feat(shell): expose la config runtime aux pages via useConfig

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 2: Renommer `AdminNav` en `SettingsNav`, ajouter l'entrée « Général »

`AdminNav.tsx` (`shell/src/shell/chrome/AdminNav.tsx`) est le panneau de navigation latéral partagé par les 7 pages `/admin/*`, filtré par privilège. Il devient `SettingsNav.tsx` : même filtrage pour les 7 entrées admin, plus une 8ᵉ entrée « Général → /settings » **toujours visible** (aucun privilège requis), en tête de liste.

**Files:**
- Create: `shell/src/shell/chrome/SettingsNav.tsx` (contenu ci-dessous)
- Create: `shell/src/shell/chrome/SettingsNav.test.tsx` (contenu ci-dessous)
- Delete: `shell/src/shell/chrome/AdminNav.tsx`, `shell/src/shell/chrome/AdminNav.test.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`
- Modify (import + JSX usage only): `shell/src/pages/AdminExtensionsPage.tsx`, `shell/src/pages/AdminInfrastructurePage.tsx`, `shell/src/pages/CollectionsAdminPage.tsx`, `shell/src/pages/HarvestSourcesAdminPage.tsx`, `shell/src/pages/RolesAdminPage.tsx`, `shell/src/pages/ComplianceAdminPage.tsx`, `shell/src/pages/UsersAdminPage.tsx`

**Interfaces:**
- Produces: `SettingsNav()` component (no props), rendered as the `browse` column content on the 7 `/admin/*` pages and (Task 3) on `/settings`.
- Consumes: `useMe()` (`shell/src/api/hooks`), `t`/`MessageKey` (`shell/src/i18n`), `Panel` (`shell/src/ui/kit/Panel`).

- [ ] **Step 1: Rename the files, preserving history**

```bash
git mv src/shell/chrome/AdminNav.tsx src/shell/chrome/SettingsNav.tsx
git mv src/shell/chrome/AdminNav.test.tsx src/shell/chrome/SettingsNav.test.tsx
```

- [ ] **Step 2: Write the new (failing) test file**

Read `shell/src/shell/chrome/SettingsNav.test.tsx` (post-rename, still has the old content), then replace its full content with:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../../test/msw/server";
import { createItemClient } from "../../api/itemClient";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { SettingsNav } from "./SettingsNav";

function mockMe(privileges: string[]) {
  server.use(
    http.get("https://core.test/v1/me", () =>
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

function renderNav(initialPath = "/admin/extensions") {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <SettingsNav />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

const ALL_PRIVILEGES = [
  "admin.extensions.manage",
  "settings.instance.manage",
  "admin.roles.manage",
  "admin.users.manage",
  "admin.collections.manage",
  "admin.harvest.manage",
  "compliance.manage",
];

test("toujours les liens retour au catalogue et Général, même sans aucun privilège", async () => {
  mockMe([]);
  renderNav();
  expect(await screen.findByRole("link", { name: "← Retour au catalogue" })).toHaveAttribute(
    "href",
    "/",
  );
  expect(screen.getByRole("link", { name: "Général →" })).toHaveAttribute("href", "/settings");
  for (const name of [
    "Extensions →",
    "Outils d'infrastructure →",
    "Rôles et privilèges →",
    "Utilisateurs →",
    "Collections →",
    "Moissonnage →",
    "Conformité (RGPD) →",
  ]) {
    expect(screen.queryByRole("link", { name })).not.toBeInTheDocument();
  }
});

test("affiche Général et les sept liens admin quand tous les privilèges sont détenus", async () => {
  mockMe(ALL_PRIVILEGES);
  renderNav();
  expect(await screen.findByRole("link", { name: "Général →" })).toHaveAttribute(
    "href",
    "/settings",
  );
  expect(screen.getByRole("link", { name: "Extensions →" })).toHaveAttribute(
    "href",
    "/admin/extensions",
  );
  expect(screen.getByRole("link", { name: "Outils d'infrastructure →" })).toHaveAttribute(
    "href",
    "/admin/infrastructure",
  );
  expect(screen.getByRole("link", { name: "Rôles et privilèges →" })).toHaveAttribute(
    "href",
    "/admin/roles",
  );
  expect(screen.getByRole("link", { name: "Utilisateurs →" })).toHaveAttribute(
    "href",
    "/admin/users",
  );
  expect(screen.getByRole("link", { name: "Collections →" })).toHaveAttribute(
    "href",
    "/admin/collections",
  );
  expect(screen.getByRole("link", { name: "Moissonnage →" })).toHaveAttribute(
    "href",
    "/admin/harvest",
  );
  expect(screen.getByRole("link", { name: "Conformité (RGPD) →" })).toHaveAttribute(
    "href",
    "/admin/compliance",
  );
});

test("ne montre que Général et Rôles quand seul admin.roles.manage est détenu", async () => {
  mockMe(["admin.roles.manage"]);
  renderNav();
  expect(await screen.findByRole("link", { name: "Rôles et privilèges →" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Général →" })).toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Utilisateurs →" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Extensions →" })).not.toBeInTheDocument();
});

test("marque la page courante comme active (aria-current) parmi les liens admin", async () => {
  mockMe(ALL_PRIVILEGES);
  renderNav("/admin/roles");
  const rolesLink = await screen.findByRole("link", { name: "Rôles et privilèges →" });
  expect(rolesLink).toHaveAttribute("aria-current", "page");
  const usersLink = screen.getByRole("link", { name: "Utilisateurs →" });
  expect(usersLink).not.toHaveAttribute("aria-current");
});

test("marque Général comme actif sur /settings", async () => {
  mockMe([]);
  renderNav("/settings");
  const generalLink = await screen.findByRole("link", { name: "Général →" });
  expect(generalLink).toHaveAttribute("aria-current", "page");
});

test("permet de naviguer d'une page admin à une autre sans repasser par /admin/extensions", async () => {
  mockMe(ALL_PRIVILEGES);
  renderNav("/admin/roles");
  expect(await screen.findByRole("link", { name: "Utilisateurs →" })).toHaveAttribute(
    "href",
    "/admin/users",
  );
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `npx vitest run src/shell/chrome/SettingsNav.test.tsx`
Expected: FAIL — `SettingsNav` still has `AdminNav`'s old content (no "Général →" link, component still named `AdminNav`).

- [ ] **Step 4: Add the i18n keys**

Read `shell/src/i18n/catalog.fr.ts`, then apply this edit:

Old:
```ts
  // AdminNav (shell/chrome/AdminNav.tsx) — panneau de gauche partagé par les
  // sept pages d'administration, filtré par privilège comme la barre de
  // domaines (capabilities.ts) : un privilège manquant masque le lien.
  "adminNav.label": "Navigation d'administration",
  "extensions.linkExtensions": "Extensions →",
```

New:
```ts
  // SettingsNav (shell/chrome/SettingsNav.tsx) — panneau de gauche partagé
  // par la page Paramètres et les sept pages d'administration (fusion des
  // anciens domaines "admin"/"settings", capabilities.ts) : "Général" est
  // toujours visible, les sept liens admin restent filtrés par privilège
  // comme la barre de domaines — un privilège manquant masque le lien.
  "settingsNav.label": "Navigation des paramètres",
  "settingsNav.linkGeneral": "Général →",
  "extensions.linkExtensions": "Extensions →",
```

- [ ] **Step 5: Rewrite `SettingsNav.tsx`**

Read `shell/src/shell/chrome/SettingsNav.tsx` (post-rename, still has `AdminNav`'s content), then replace its full content with:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { Link, useLocation } from "react-router-dom";
import { useMe } from "../../api/hooks";
import { Panel } from "../../ui/kit/Panel";
import { t, type MessageKey } from "../../i18n";

// Liens partagés par la page Paramètres et les sept pages d'administration :
// fusion des anciens domaines "admin" et "settings" (capabilities.ts) en un
// seul point d'entrée toujours visible — "Général" (vers /settings) n'exige
// aucun privilège, les sept entrées admin gardent leur filtrage inchangé.
// Même doctrine que capabilities.ts : un privilège manquant MASQUE le lien.
const SETTINGS_LINKS: readonly { to: string; labelKey: MessageKey; privilege?: string }[] = [
  { to: "/settings", labelKey: "settingsNav.linkGeneral" },
  {
    to: "/admin/extensions",
    labelKey: "extensions.linkExtensions",
    privilege: "admin.extensions.manage",
  },
  {
    to: "/admin/infrastructure",
    labelKey: "extensions.linkInfrastructure",
    privilege: "settings.instance.manage",
  },
  { to: "/admin/roles", labelKey: "extensions.linkRoles", privilege: "admin.roles.manage" },
  { to: "/admin/users", labelKey: "extensions.linkUsers", privilege: "admin.users.manage" },
  {
    to: "/admin/collections",
    labelKey: "extensions.linkCollections",
    privilege: "admin.collections.manage",
  },
  { to: "/admin/harvest", labelKey: "extensions.linkHarvest", privilege: "admin.harvest.manage" },
  {
    to: "/admin/compliance",
    labelKey: "extensions.linkCompliance",
    privilege: "compliance.manage",
  },
] as const;

export function SettingsNav() {
  const meQuery = useMe();
  const location = useLocation();
  const visibleLinks = SETTINGS_LINKS.filter(
    (link) =>
      link.privilege === undefined || meQuery.data?.privileges.includes(link.privilege) === true,
  );

  return (
    <Panel className="m-3 flex flex-col gap-1 text-sm">
      <Link to="/" className="rounded-md px-2 py-1.5 text-accent hover:bg-sunken hover:underline">
        {t("nav.backToCatalog")}
      </Link>
      <nav
        aria-label={t("settingsNav.label")}
        className="mt-1 flex flex-col gap-0.5 border-t border-rule pt-2"
      >
        {visibleLinks.map((link) => {
          const active = location.pathname === link.to;
          return (
            <Link
              key={link.to}
              to={link.to}
              aria-current={active ? "page" : undefined}
              className={
                active
                  ? "rounded-md bg-accent-soft px-2 py-1.5 font-semibold text-accent-ink"
                  : "rounded-md px-2 py-1.5 text-ink-2 hover:bg-sunken hover:text-ink"
              }
            >
              {t(link.labelKey)}
            </Link>
          );
        })}
      </nav>
    </Panel>
  );
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `npx vitest run src/shell/chrome/SettingsNav.test.tsx`
Expected: PASS (7 tests).

- [ ] **Step 7: Update the 7 admin pages' import and usage**

Each of these 7 files has exactly two lines to change: the import, and the JSX usage inside `browse.content`. Read each file first, then apply both edits (identical old/new text in every file):

Edit A (import), applied to each of the 7 files below:
- Old: `import { AdminNav } from "../shell/chrome/AdminNav";`
- New: `import { SettingsNav } from "../shell/chrome/SettingsNav";`

Edit B (JSX usage), applied to each of the 7 files below:
- Old: `content: <AdminNav />,`
- New: `content: <SettingsNav />,`

Files to edit (both edits, each):
- `shell/src/pages/AdminExtensionsPage.tsx`
- `shell/src/pages/AdminInfrastructurePage.tsx`
- `shell/src/pages/CollectionsAdminPage.tsx`
- `shell/src/pages/HarvestSourcesAdminPage.tsx`
- `shell/src/pages/RolesAdminPage.tsx`
- `shell/src/pages/ComplianceAdminPage.tsx`
- `shell/src/pages/UsersAdminPage.tsx`

- [ ] **Step 8: Verify no stray reference remains**

Run: `grep -rn "AdminNav" src`
Expected: no output (empty). If anything prints, fix it before moving on (piège n°1 du dépôt : renommage partiel).

- [ ] **Step 9: Run the full affected test suite**

Run:
```bash
npx vitest run src/shell/chrome/SettingsNav.test.tsx src/pages/AdminExtensionsPage.test.tsx src/pages/UsersAdminPage.test.tsx
```
Expected: PASS — `AdminExtensionsPage.test.tsx` renders the page (which now uses `SettingsNav` internally) without referencing `AdminNav` by name, so it should keep passing unmodified.

- [ ] **Step 10: Commit**

```bash
git add -A src/shell/chrome src/pages src/i18n/catalog.fr.ts
git commit -m "refactor(shell): renomme AdminNav en SettingsNav, ajoute l'entrée Général

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 3: `SettingsPage` — profil, notifications, compte

Remplace `SettingsComingSoonPage.tsx` par une vraie page : profil en lecture seule (`GET /me`, déjà chargé partout via `useMe()`), préférence de notifications (déjà câblée côté API/hooks — `useNotificationPreference`/`useUpdateNotificationPreference`, `shell/src/api/domains/notifications.hooks.ts`), lien externe vers la console de compte Keycloak (masqué en mode mock).

**Files:**
- Create: `shell/src/auth/roleLabel.ts`, `shell/src/auth/roleLabel.test.ts`
- Create: `shell/src/pages/SettingsPage.tsx`, `shell/src/pages/SettingsPage.test.tsx`
- Delete: `shell/src/pages/SettingsComingSoonPage.tsx`
- Modify: `shell/src/shell/chrome/AccountMenu.tsx` (use the extracted `roleLabel`)
- Modify: `shell/src/shell/routes.tsx`, `shell/src/i18n/catalog.fr.ts`, `shell/e2e/triptych-narrow.spec.ts`

**Interfaces:**
- Consumes: `useMe()`, `useNotificationPreference()`, `useUpdateNotificationPreference()` (`shell/src/api/hooks`); `useConfig()` (Task 1, `shell/src/ConfigContext`); `SettingsNav` (Task 2, `shell/src/shell/chrome/SettingsNav`); `NotificationPreferenceValue` (`shell/src/api/types`); `Radio` (`shell/src/ui/kit/Radio`); `Badge` (`shell/src/ui/kit/Badge`).
- Produces: `roleLabel(me: Me | undefined): string`; `SettingsPage()` component, wired at route `/settings`.

- [ ] **Step 1: Extract `roleLabel` (currently private to `AccountMenu.tsx`) into a shared module**

Create `shell/src/auth/roleLabel.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import type { Me } from "../api/types";
import { t, type MessageKey } from "../i18n";

const BUILT_IN_ROLE_LABEL_KEYS: Record<string, MessageKey> = {
  admin: "account.roleAdmin",
  analyst: "account.roleAnalyst",
  creator: "account.roleCreator",
  reader: "account.roleReader",
};

export function roleLabel(me: Me | undefined): string {
  if (!me) return "";
  const key = BUILT_IN_ROLE_LABEL_KEYS[me.role.slug];
  return key ? t(key) : me.role.name;
}
```

- [ ] **Step 2: Write the failing test for `roleLabel`**

Create `shell/src/auth/roleLabel.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { roleLabel } from "./roleLabel";
import type { Me } from "../api/types";

function meWith(slug: string, name: string): Me {
  return {
    id: "u1",
    tenantId: "t1",
    tenantSlug: "demo",
    username: "alice",
    email: null,
    firstName: "",
    lastName: "",
    role: { id: "r1", name, slug },
    privileges: [],
    version: "0.1.0",
    capabilities: {
      readOnly: false,
      etlEnabled: false,
      exportEnabled: false,
      appExportEnabled: false,
      tileset3dEnabled: false,
      terrain3dEnabled: false,
      copilotEnabled: false,
      adminToolsEnabled: false,
      quotasEnabled: false,
    },
  };
}

test("traduit le libellé d'un rôle intégré", () => {
  expect(roleLabel(meWith("admin", "Administrateur"))).toBe("Administrateur");
});

test("retombe sur le nom du rôle pour un rôle sur mesure", () => {
  expect(roleLabel(meWith("role-abc123", "Cartographe"))).toBe("Cartographe");
});

test("retourne une chaîne vide sans profil", () => {
  expect(roleLabel(undefined)).toBe("");
});
```

Run: `npx vitest run src/auth/roleLabel.test.ts`
Expected: PASS (the module from Step 1 already exists — this step only proves it's correct in isolation before wiring consumers).

- [ ] **Step 3: Update `AccountMenu.tsx` to use the shared `roleLabel`**

Read `shell/src/shell/chrome/AccountMenu.tsx`, then apply:

Old:
```tsx
// SPDX-License-Identifier: Apache-2.0
import { useAuth } from "../../auth/useAuth";
import { useMe } from "../../api/hooks";
import type { Me } from "../../api/types";
import { Avatar } from "../../ui/kit/Avatar";
import { Popover } from "../../ui/kit/Popover";
import { Badge } from "../../ui/kit/Badge";
import { t } from "../../i18n";
import type { MessageKey } from "../../i18n";

const BUILT_IN_ROLE_LABEL_KEYS: Record<string, MessageKey> = {
  admin: "account.roleAdmin",
  analyst: "account.roleAnalyst",
  creator: "account.roleCreator",
  reader: "account.roleReader",
};

function roleLabel(me: Me | undefined): string {
  if (!me) return "";
  const key = BUILT_IN_ROLE_LABEL_KEYS[me.role.slug];
  return key ? t(key) : me.role.name;
}

function initials(username: string): string {
```

New:
```tsx
// SPDX-License-Identifier: Apache-2.0
import { useAuth } from "../../auth/useAuth";
import { useMe } from "../../api/hooks";
import { roleLabel } from "../../auth/roleLabel";
import { Avatar } from "../../ui/kit/Avatar";
import { Popover } from "../../ui/kit/Popover";
import { Badge } from "../../ui/kit/Badge";
import { t } from "../../i18n";

function initials(username: string): string {
```

Run: `npx vitest run src/shell/chrome/AccountMenu.test.tsx`
Expected: PASS unchanged (pure refactor, same rendered output).

- [ ] **Step 4: Add the i18n keys for `SettingsPage`, remove the orphaned `comingSoon.settings`**

Read `shell/src/i18n/catalog.fr.ts`, then apply these two edits:

Edit 1 — remove the orphaned coming-soon key:

Old:
```ts
  "domain.admin": "Administration",
  "domain.settings": "Paramètres",
  "domainBar.label": "Domaines",
  "bottomNav.label": "Navigation",
  "bottomNav.more": "Plus",
  "comingSoon.settings": "Les paramètres d'instance arrivent prochainement.",
```

New:
```ts
  "domain.admin": "Administration",
  "domain.settings": "Paramètres",
  "domainBar.label": "Domaines",
  "bottomNav.label": "Navigation",
  "bottomNav.more": "Plus",
```

Edit 2 — add the new `settings.*` keys, right before the `AdminInfrastructurePage` comment block (after the `SettingsNav` keys added in Task 2):

Old:
```ts
  "settingsNav.linkGeneral": "Général →",
  "extensions.linkExtensions": "Extensions →",
  "extensions.linkInfrastructure": "Outils d'infrastructure →",
  "extensions.linkRoles": "Rôles et privilèges →",
  "extensions.linkUsers": "Utilisateurs →",
  "extensions.linkCollections": "Collections →",
  "extensions.linkHarvest": "Moissonnage →",
  "extensions.linkCompliance": "Conformité (RGPD) →",

  // AdminInfrastructurePage
```

New:
```ts
  "settingsNav.linkGeneral": "Général →",
  "extensions.linkExtensions": "Extensions →",
  "extensions.linkInfrastructure": "Outils d'infrastructure →",
  "extensions.linkRoles": "Rôles et privilèges →",
  "extensions.linkUsers": "Utilisateurs →",
  "extensions.linkCollections": "Collections →",
  "extensions.linkHarvest": "Moissonnage →",
  "extensions.linkCompliance": "Conformité (RGPD) →",

  // SettingsPage (pages/SettingsPage.tsx) — espace personnel : profil en
  // lecture seule (identité gérée par Keycloak), préférence de notifications
  // (déjà servie par le cœur, GET/PATCH /notifications/preference), lien
  // vers la console de compte Keycloak (masqué en mode mock).
  "settings.heading": "Paramètres",
  "settings.detail": "Aide",
  "settings.helpText":
    "Ces réglages sont personnels : ils ne sont visibles que par vous, pas partagés avec les autres utilisateurs.",
  "settings.profileTitle": "Profil",
  "settings.profileUsername": "Nom d'utilisateur",
  "settings.profileEmail": "Email",
  "settings.profileName": "Nom complet",
  "settings.profileRole": "Rôle",
  "settings.profileTenant": "Tenant",
  "settings.notificationsTitle": "Notifications",
  "settings.notificationsAll": "Toutes",
  "settings.notificationsFailuresOnly": "Échecs seulement",
  "settings.notificationsNone": "Aucune",
  "settings.notificationsSaveError": "Échec de l'enregistrement de la préférence.",
  "settings.accountTitle": "Compte",
  "settings.accountKeycloakLink":
    "Gérer mon compte (mot de passe, authentification à deux facteurs) →",

  // AdminInfrastructurePage
```

- [ ] **Step 5: Write the failing test for `SettingsPage`**

Create `shell/src/pages/SettingsPage.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ConfigProvider } from "../ConfigContext";
import type { AppConfig } from "../config";
import { SettingsPage } from "./SettingsPage";

const OIDC_CONFIG: AppConfig = {
  coreUrl: "https://core.test",
  oidcAuthority: "https://kc.test/realms/geostudio",
  oidcClientId: "shell",
  oidcRedirectUri: "https://app.test/callback",
  authMode: "oidc",
};
const MOCK_CONFIG: AppConfig = { ...OIDC_CONFIG, authMode: "mock" };

function mockMe() {
  server.use(
    http.get("https://core.test/v1/me", () =>
      HttpResponse.json({
        id: "u1",
        tenantId: "t1",
        tenantSlug: "acme",
        username: "alice",
        email: "alice@example.com",
        firstName: "Alice",
        lastName: "Martin",
        role: { id: "role-1", name: "Créateur", slug: "creator" },
        privileges: [],
      }),
    ),
  );
}

function mockPreference(value = "all") {
  server.use(
    http.get("https://core.test/v1/notifications/preference", () =>
      HttpResponse.json({ value }),
    ),
  );
}

function renderPage(config: AppConfig = OIDC_CONFIG) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <ConfigProvider config={config}>
            <SettingsPage />
          </ConfigProvider>
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

test("affiche le profil et la préférence de notifications courante", async () => {
  mockMe();
  mockPreference("all");
  renderPage();
  expect(await screen.findByText("alice")).toBeInTheDocument();
  expect(screen.getByText("alice@example.com")).toBeInTheDocument();
  expect(screen.getByText("Alice Martin")).toBeInTheDocument();
  expect(screen.getByText("Créateur")).toBeInTheDocument();
  expect(screen.getByText("acme")).toBeInTheDocument();
  expect(await screen.findByRole("radio", { name: "Toutes" })).toBeChecked();
});

test("change la préférence de notifications appelle PATCH avec la nouvelle valeur", async () => {
  mockMe();
  mockPreference("all");
  let patchedBody: unknown = null;
  server.use(
    http.patch("https://core.test/v1/notifications/preference", async ({ request }) => {
      patchedBody = await request.json();
      return HttpResponse.json({ value: "failures_only" });
    }),
  );
  renderPage();
  const failuresRadio = await screen.findByRole("radio", { name: "Échecs seulement" });
  await userEvent.click(failuresRadio);
  await waitFor(() => expect(patchedBody).toEqual({ value: "failures_only" }));
});

test("affiche une erreur si la sauvegarde de la préférence échoue", async () => {
  mockMe();
  mockPreference("all");
  server.use(
    http.patch(
      "https://core.test/v1/notifications/preference",
      () => new HttpResponse(null, { status: 500 }),
    ),
  );
  renderPage();
  const noneRadio = await screen.findByRole("radio", { name: "Aucune" });
  await userEvent.click(noneRadio);
  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Échec de l'enregistrement de la préférence.",
  );
});

test("masque la section Compte en mode mock", async () => {
  mockMe();
  mockPreference("all");
  renderPage(MOCK_CONFIG);
  await screen.findByText("alice");
  expect(
    screen.queryByRole("link", { name: /Gérer mon compte/ }),
  ).not.toBeInTheDocument();
});

test("affiche le lien vers la console de compte Keycloak en mode oidc", async () => {
  mockMe();
  mockPreference("all");
  renderPage(OIDC_CONFIG);
  const link = await screen.findByRole("link", { name: /Gérer mon compte/ });
  expect(link).toHaveAttribute("href", "https://kc.test/realms/geostudio/account");
  expect(link).toHaveAttribute("target", "_blank");
});
```

- [ ] **Step 6: Run test to verify it fails**

Run: `npx vitest run src/pages/SettingsPage.test.tsx`
Expected: FAIL — `Cannot find module './SettingsPage'`.

- [ ] **Step 7: Write `SettingsPage.tsx`**

Create `shell/src/pages/SettingsPage.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useMe, useNotificationPreference, useUpdateNotificationPreference } from "../api/hooks";
import type { NotificationPreferenceValue } from "../api/types";
import { roleLabel } from "../auth/roleLabel";
import { useConfig } from "../ConfigContext";
import { Badge } from "../ui/kit/Badge";
import { Radio } from "../ui/kit/Radio";
import { SettingsNav } from "../shell/chrome/SettingsNav";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

function ProfileSection() {
  const meQuery = useMe();
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-semibold text-ink">{t("settings.profileTitle")}</h2>
      {meQuery.isLoading && <p role="status">{t("common.loading")}</p>}
      {meQuery.data && (
        <dl className="grid grid-cols-[auto_1fr] gap-x-2 gap-y-1 text-sm text-ink-2">
          <dt>{t("settings.profileUsername")}</dt>
          <dd>{meQuery.data.username}</dd>
          <dt>{t("settings.profileEmail")}</dt>
          <dd>{meQuery.data.email ?? "—"}</dd>
          <dt>{t("settings.profileName")}</dt>
          <dd>
            {[meQuery.data.firstName, meQuery.data.lastName].filter(Boolean).join(" ") || "—"}
          </dd>
          <dt>{t("settings.profileRole")}</dt>
          <dd>
            <Badge>{roleLabel(meQuery.data)}</Badge>
          </dd>
          <dt>{t("settings.profileTenant")}</dt>
          <dd>{meQuery.data.tenantSlug}</dd>
        </dl>
      )}
    </section>
  );
}

function NotificationsSection() {
  const preferenceQuery = useNotificationPreference();
  const updatePreference = useUpdateNotificationPreference();
  const [saveError, setSaveError] = useState(false);

  async function handleChange(value: NotificationPreferenceValue) {
    setSaveError(false);
    try {
      await updatePreference.mutateAsync(value);
    } catch {
      setSaveError(true);
    }
  }

  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-semibold text-ink">{t("settings.notificationsTitle")}</h2>
      {preferenceQuery.isLoading && <p role="status">{t("common.loading")}</p>}
      {preferenceQuery.data && (
        <Radio.Group
          aria-label={t("settings.notificationsTitle")}
          value={preferenceQuery.data}
          disabled={updatePreference.isPending}
          onValueChange={(value) => void handleChange(value as NotificationPreferenceValue)}
        >
          <Radio.Item value="all">{t("settings.notificationsAll")}</Radio.Item>
          <Radio.Item value="failuresOnly">{t("settings.notificationsFailuresOnly")}</Radio.Item>
          <Radio.Item value="none">{t("settings.notificationsNone")}</Radio.Item>
        </Radio.Group>
      )}
      {saveError && (
        <p role="alert" className="text-sm text-danger">
          {t("settings.notificationsSaveError")}
        </p>
      )}
    </section>
  );
}

function AccountSection() {
  const config = useConfig();
  if (config.authMode === "mock") return null;
  return (
    <section className="flex flex-col gap-2">
      <h2 className="text-base font-semibold text-ink">{t("settings.accountTitle")}</h2>
      <a
        href={`${config.oidcAuthority}/account`}
        target="_blank"
        rel="noopener noreferrer"
        className="text-accent hover:underline"
      >
        {t("settings.accountKeycloakLink")}
      </a>
    </section>
  );
}

export function SettingsPage() {
  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: t("domain.catalog"),
          content: <SettingsNav />,
        }}
        work={{
          id: "settings",
          label: t("domain.settings"),
          content: (
            <div className="flex h-full flex-col gap-6 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">{t("settings.heading")}</h1>
              <ProfileSection />
              <NotificationsSection />
              <AccountSection />
            </div>
          ),
        }}
        inspect={{
          id: "help",
          label: t("settings.detail"),
          content: (
            <div className="flex flex-col gap-2 p-3 text-sm text-ink-2">
              <p>{t("settings.helpText")}</p>
            </div>
          ),
        }}
      />
    </div>
  );
}
```

- [ ] **Step 8: Run test to verify it passes**

Run: `npx vitest run src/pages/SettingsPage.test.tsx`
Expected: PASS (5 tests).

- [ ] **Step 9: Wire the route, delete the old placeholder page**

Read `shell/src/shell/routes.tsx`, then apply:

Old:
```tsx
const SettingsComingSoonPage = lazy(() =>
  import("../pages/SettingsComingSoonPage").then((m) => ({ default: m.SettingsComingSoonPage })),
);
```

New:
```tsx
const SettingsPage = lazy(() =>
  import("../pages/SettingsPage").then((m) => ({ default: m.SettingsPage })),
);
```

Old:
```tsx
          <Route path="/settings" element={<SettingsComingSoonPage />} />
```

New:
```tsx
          <Route path="/settings" element={<SettingsPage />} />
```

Then:
```bash
git rm src/pages/SettingsComingSoonPage.tsx
```

- [ ] **Step 10: Update the narrow-viewport E2E fixture for `/settings`**

Read `shell/e2e/triptych-narrow.spec.ts`, then apply:

Old:
```ts
  {
    name: "Paramètres",
    path: "/settings",
    // SettingsComingSoonPage.tsx ne rend qu'un <EmptyState> — aucune grille
    // TriptychLayout à cet écran (confirmé par lecture directe du fichier,
    // pas supposé) : passage réel et significatif, pas vacant. Aucun appel
    // réseau non plus (rendu synchrone) : l'ancre est un filet de
    // cohérence, pas une preuve de settle nécessaire ici.
    // Texte migré vers la clé i18n `comingSoon.settings` par SP-57a — le
    // littéral d'origine ("... arrivent avec SP-33.") n'existe plus.
    readyAnchor: (p) => p.getByText("Les paramètres d'instance arrivent prochainement.").waitFor(),
  },
```

New:
```ts
  {
    name: "Paramètres",
    path: "/settings",
    // SettingsPage.tsx (fusion Paramètres/Administration) rend une grille
    // TriptychLayout complète : profil (GET /me, déjà mocké par mockCore())
    // et préférence de notifications (GET /notifications/preference, mockée
    // ci-dessous). L'ancre attend la section Profil, seule à dépendre d'un
    // appel réseau non couvert par défaut par mockCore().
    before: (p) =>
      p.route("https://core.test/v1/notifications/preference", (route) =>
        route.fulfill({ json: { value: "all" } }),
      ),
    readyAnchor: (p) => p.getByRole("heading", { name: "Profil" }).waitFor(),
  },
```

- [ ] **Step 11: Run the full affected test suite**

Run:
```bash
npx vitest run src/pages/SettingsPage.test.tsx src/auth/roleLabel.test.ts src/shell/chrome/AccountMenu.test.tsx
npm run lint
```
Expected: PASS. `npm run lint` in particular confirms no hardcoded French string slipped into `SettingsPage.tsx`.

- [ ] **Step 12: Commit**

```bash
git add -A src/pages src/auth src/shell/routes.tsx src/i18n/catalog.fr.ts src/shell/chrome/AccountMenu.tsx e2e/triptych-narrow.spec.ts
git commit -m "feat(shell): page Paramètres — profil, notifications, lien de compte

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 4: Fusionner le domaine `admin` dans `settings`

`capabilities.ts` déclare aujourd'hui deux domaines de navigation distincts (`admin`, filtré par privilège ; `settings`, toujours visible). Cette tâche les fusionne en un seul (`settings`) — la barre de domaines et le menu « Plus » n'affichent plus qu'une entrée « Paramètres », toujours visible, qui atterrit toujours sur `/settings`. La visibilité des 7 destinations admin reste gérée par `SettingsNav` (Task 2), pas ici.

**Files:**
- Modify: `shell/src/auth/capabilities.ts`, `shell/src/auth/capabilities.test.ts`
- Modify: `shell/src/shell/chrome/domainRoutes.ts` (full rewrite — see below)
- Modify: `shell/src/shell/chrome/DomainBar.tsx`, `shell/src/shell/chrome/DomainBar.test.tsx`
- Modify: `shell/src/shell/chrome/BottomNav.tsx`, `shell/src/shell/chrome/BottomNav.test.tsx`
- Modify: `shell/src/i18n/catalog.fr.ts`

**Interfaces:**
- Produces: `DOMAIN_PATHS: Record<DomainId, string>` (unchanged shape, one fewer key); `isDomainActive` (unchanged). `getDomainPath()` is removed — its only special case (`admin`) no longer exists, so every call site reads `DOMAIN_PATHS[domain.id]` directly.
- Consumes: nothing new.

- [ ] **Step 1: Remove `admin` from `DomainId` and `DOMAINS`**

Read `shell/src/auth/capabilities.ts`, then apply:

Old:
```ts
export type DomainId =
  | "catalog"
  | "maps"
  | "data"
  | "apps"
  | "automation"
  | "analytics"
  | "tasks"
  | "admin"
  | "settings";
```

New:
```ts
export type DomainId =
  | "catalog"
  | "maps"
  | "data"
  | "apps"
  | "automation"
  | "analytics"
  | "tasks"
  | "settings";
```

Old:
```ts
  { id: "tasks", labelKey: "domain.tasks", requiresPrivilege: "tasks.view" },
  {
    id: "admin",
    labelKey: "domain.admin",
    requiresPrivilege: [
      "admin.users.manage",
      "admin.roles.manage",
      "admin.harvest.manage",
      "admin.collections.manage",
      "admin.extensions.manage",
      "admin.secrets.manage",
    ],
  },
  { id: "settings", labelKey: "domain.settings" },
] as const;
```

New:
```ts
  { id: "tasks", labelKey: "domain.tasks", requiresPrivilege: "tasks.view" },
  // Fusionné avec l'ancien domaine "admin" : "settings" est désormais
  // l'unique point d'entrée, toujours visible — la visibilité par privilège
  // des 7 destinations admin se fait dans SettingsNav
  // (shell/chrome/SettingsNav.tsx), pas ici. Un privilège manquant masque
  // toujours l'entrée correspondante, doctrine inchangée.
  { id: "settings", labelKey: "domain.settings" },
] as const;
```

- [ ] **Step 2: Rewrite `domainRoutes.ts`**

Read `shell/src/shell/chrome/domainRoutes.ts`, then replace its full content with:

```ts
// SPDX-License-Identifier: Apache-2.0
import type { DomainId } from "../../auth/capabilities";

// Cartes/Données/Apps & sites/Automatisation n'ont pas encore de page dédiée
// (SP-30b+ les reconstruit sur TriptychLayout) : en attendant, leur entrée de
// la barre de domaines pointe vers le Catalogue pré-filtré par type
// (CatalogPage lit `?type=`, cf. Task 6) — pas une fausse promesse de
// fonctionnalité manquante, juste une réorganisation de ce qui existe déjà.
export const DOMAIN_PATHS: Record<DomainId, string> = {
  catalog: "/",
  maps: "/?type=map",
  data: "/?type=dataset",
  apps: "/?type=app",
  automation: "/?type=pipeline",
  // SP-42, revue de la dernière passe de correctifs (point 7) : ne pointe
  // plus vers /analytics/sql (RequirePrivilege="analytics.sql_lab.access",
  // hors d'atteinte d'un Créateur qui n'a qu'analytics.view — cf.
  // capabilities.ts, DOMAINS["analytics"], qui redevient visible sur
  // analytics.view). Rejoint le même patron que Cartes/Données/Apps &
  // sites/Automatisation ci-dessus : catalogue filtré par type, sans garde.
  analytics: "/?type=bookmark",
  tasks: "/tasks",
  // Fusion des anciens domaines "admin"/"settings" (capabilities.ts) :
  // /settings est toujours la destination, quel que soit le profil — plus
  // besoin de deviner un premier /admin/* accessible (ancien
  // ADMIN_DESTINATIONS/cas spécial de getDomainPath, retiré). La visibilité
  // par privilège des 7 destinations admin se fait dans SettingsNav
  // (shell/chrome/SettingsNav.tsx), pas ici.
  settings: "/settings",
};

// Plusieurs domaines (Cartes/Données/Apps & sites/Automatisation) pointent
// tous vers "/" avec un ?type= différent (Task 6) : comparer seulement le
// pathname les ferait paraître actifs tous en même temps. Comparer aussi la
// recherche pour ceux dont le chemin en porte une ; pour les autres (dont
// Catalogue, "/" sans ?type=), comparer le pathname ET exiger une recherche
// vide — sinon Catalogue ("/") paraîtrait actif même sur "/?type=map", qui
// partage le même pathname.
//
// Utiliser cette fonction avec `Link`, jamais `NavLink` : `NavLink` calcule
// sa PROPRE notion d'« actif » à partir du seul pathname de `to` (la query
// est perdue par `useResolvedPath`), et sa déstructuration par défaut
// réinjecte "page" dès qu'on lui passe `aria-current: undefined` —
// impossible d'annuler son `aria-current`/`className` internes depuis
// l'extérieur. Vérifié empiriquement : `NavLink` marquait Catalogue actif sur
// "/?type=map" malgré un `aria-current` explicite à `undefined`.
export function isDomainActive(path: string, location: { pathname: string; search: string }) {
  const currentHref = location.pathname + location.search;
  return path.includes("?")
    ? currentHref === path
    : location.pathname === path && location.search === "";
}
```

- [ ] **Step 3: Update `DomainBar.tsx` and `BottomNav.tsx` call sites**

Read `shell/src/shell/chrome/DomainBar.tsx`, then apply:

Old:
```tsx
import { Link, useLocation } from "react-router-dom";
import { navigableDomains, type Profile } from "../../auth/capabilities";
import { getDomainPath, isDomainActive } from "./domainRoutes";
import { t } from "../../i18n";
```

New:
```tsx
import { Link, useLocation } from "react-router-dom";
import { navigableDomains, type Profile } from "../../auth/capabilities";
import { DOMAIN_PATHS, isDomainActive } from "./domainRoutes";
import { t } from "../../i18n";
```

Old:
```tsx
      {domains.map(({ domain, state }) => {
        const path = getDomainPath(domain.id, profile);
```

New:
```tsx
      {domains.map(({ domain, state }) => {
        const path = DOMAIN_PATHS[domain.id];
```

Read `shell/src/shell/chrome/BottomNav.tsx`, then apply:

Old:
```tsx
import { navigableDomains, type Profile } from "../../auth/capabilities";
import { getDomainPath, isDomainActive } from "./domainRoutes";
```

New:
```tsx
import { navigableDomains, type Profile } from "../../auth/capabilities";
import { DOMAIN_PATHS, isDomainActive } from "./domainRoutes";
```

This file calls `getDomainPath(domain.id, profile)` twice (once for `fixed`, once for `rest`) — both with the exact same line of code. Replace both occurrences:

Old (×2):
```tsx
        const path = getDomainPath(domain.id, profile);
```

New (×2):
```tsx
        const path = DOMAIN_PATHS[domain.id];
```

- [ ] **Step 4: Update `capabilities.test.ts`**

Read `shell/src/auth/capabilities.test.ts`, then apply these edits:

Old:
```ts
  it("déclare les neuf domaines de la spec", () => {
    expect(DOMAINS.map((d) => d.id)).toEqual([
      "catalog",
      "maps",
      "data",
      "apps",
      "automation",
      "analytics",
      "tasks",
      "admin",
      "settings",
    ]);
  });

  it("masque le domaine admin sans aucun privilège admin.*, le montre à l'admin", () => {
    expect(stateOf("admin", reader)).toBe("hidden");
    expect(stateOf("admin", creator)).toBe("hidden");
    expect(stateOf("admin", admin)).toBe("visible");
  });
```

New:
```ts
  it("déclare les huit domaines de la spec", () => {
    expect(DOMAINS.map((d) => d.id)).toEqual([
      "catalog",
      "maps",
      "data",
      "apps",
      "automation",
      "analytics",
      "tasks",
      "settings",
    ]);
  });

  it("le domaine settings (fusionné avec l'ancien admin) est toujours visible, quel que soit le privilège", () => {
    expect(stateOf("settings", reader)).toBe("visible");
    expect(stateOf("settings", creator)).toBe("visible");
    expect(stateOf("settings", admin)).toBe("visible");
  });
```

Old:
```ts
  it("un domaine visible doit toujours pouvoir atteindre le privilège réellement gardé par sa destination (F-securite-autorisation-08)", () => {
    // Cf. shell/src/shell/routes.tsx pour la garde RequirePrivilege réelle de
    // chaque destination de DOMAIN_PATHS (domainRoutes.ts) — dupliqué ici
    // faute de pouvoir importer routes.tsx (React Router) dans un test de
    // logique pure. admin est délibérément absent : sa destination varie
    // par profil (getDomainPath), déjà couvert par domainRoutes.test.ts.
    // Vide aujourd'hui (SP-42, revue de la dernière passe de correctifs,
    // points 7/8) : ni Cartes (/?type=map) ni Analytique (/?type=bookmark)
    // n'ont plus de destination gardée — gardé comme filet pour un futur
    // domaine dont la destination exigerait réellement un privilège.
    const destinationPrivilege: Partial<Record<string, string>> = {};
    for (const profile of [admin, creator, analyst, reader]) {
      for (const domain of DOMAINS) {
        if (domain.id === "admin") continue;
        const required = destinationPrivilege[domain.id];
        if (!required) continue;
        if (domainState(domain, profile) === "visible") {
          expect(profile.privileges.has(required)).toBe(true);
        }
      }
    }
  });
```

New:
```ts
  it("un domaine visible doit toujours pouvoir atteindre le privilège réellement gardé par sa destination (F-securite-autorisation-08)", () => {
    // Cf. shell/src/shell/routes.tsx pour la garde RequirePrivilege réelle de
    // chaque destination de DOMAIN_PATHS (domainRoutes.ts). Vide aujourd'hui
    // (SP-42, revue de la dernière passe de correctifs, points 7/8) : ni
    // Cartes (/?type=map) ni Analytique (/?type=bookmark) n'ont plus de
    // destination gardée — gardé comme filet pour un futur domaine dont la
    // destination exigerait réellement un privilège. "admin" (dont la
    // destination variait par profil via getDomainPath) a disparu avec la
    // fusion Paramètres/Administration : /settings est désormais une
    // destination statique pour tous les profils.
    const destinationPrivilege: Partial<Record<string, string>> = {};
    for (const profile of [admin, creator, analyst, reader]) {
      for (const domain of DOMAINS) {
        const required = destinationPrivilege[domain.id];
        if (!required) continue;
        if (domainState(domain, profile) === "visible") {
          expect(profile.privileges.has(required)).toBe(true);
        }
      }
    }
  });
```

Old:
```ts
describe("navigableDomains", () => {
  it("ne rend que le visible et le verrouillé, dans l'ordre déclaré", () => {
    const etlOff: Profile = { ...creator, capabilities: { ...ALL_ON, etlEnabled: false } };
    const rendered = navigableDomains(etlOff);
    expect(rendered.map((r) => r.domain.id)).not.toContain("admin");
    // "analytics" présent : `creator` a analytics.view (SP-42, revue de la
    // dernière passe de correctifs, points 7/8 ci-dessus) — pas un effet de
    // etlOff.
    expect(rendered.map((r) => r.domain.id)).toContain("analytics");
```

New:
```ts
describe("navigableDomains", () => {
  it("ne rend que le visible et le verrouillé, dans l'ordre déclaré", () => {
    const etlOff: Profile = { ...creator, capabilities: { ...ALL_ON, etlEnabled: false } };
    const rendered = navigableDomains(etlOff);
    // "analytics" présent : `creator` a analytics.view (SP-42, revue de la
    // dernière passe de correctifs, points 7/8 ci-dessus) — pas un effet de
    // etlOff.
    expect(rendered.map((r) => r.domain.id)).toContain("analytics");
```

- [ ] **Step 5: Update `DomainBar.test.tsx`**

Read `shell/src/shell/chrome/DomainBar.test.tsx`, then apply:

Old:
```ts
test("affiche les huit domaines accessibles à un créateur, avec Analytique mais sans Administration", () => {
  renderBar(BASE_PROFILE);
  for (const label of [
    "Catalogue",
    "Cartes",
    "Données",
    "Apps & sites",
    "Automatisation",
    "Analytique",
    "Tâches",
    "Paramètres",
  ]) {
    expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
  }
  expect(screen.queryByRole("link", { name: "Administration" })).not.toBeInTheDocument();
});

test("affiche Administration pour un administrateur", () => {
  renderBar({
    ...BASE_PROFILE,
    privileges: new Set([...BASE_PROFILE.privileges, "admin.users.manage"]),
  });
  expect(screen.getByRole("link", { name: "Administration" })).toBeInTheDocument();
});
```

New:
```ts
test("affiche les huit domaines accessibles à un créateur, avec Analytique et Paramètres", () => {
  renderBar(BASE_PROFILE);
  for (const label of [
    "Catalogue",
    "Cartes",
    "Données",
    "Apps & sites",
    "Automatisation",
    "Analytique",
    "Tâches",
    "Paramètres",
  ]) {
    expect(screen.getByRole("link", { name: label })).toBeInTheDocument();
  }
});

test("Paramètres reste visible même sans aucun privilège admin.*", () => {
  renderBar({ ...BASE_PROFILE, privileges: new Set() });
  expect(screen.getByRole("link", { name: "Paramètres" })).toBeInTheDocument();
});
```

Old (delete this whole test — it exercised `getDomainPath`'s admin-only special case, which no longer exists):
```ts
test("SP-42/F-securite-autorisation-08(b) : Administration pointe vers la route accessible au privilège réellement détenu", () => {
  renderBar({
    ...BASE_PROFILE,
    // Ni admin.extensions.manage (destination par défaut de DOMAIN_PATHS)
    // ni aucun autre privilège admin que admin.users.manage.
    privileges: new Set([...BASE_PROFILE.privileges, "admin.users.manage"]),
  });
  expect(screen.getByRole("link", { name: "Administration" })).toHaveAttribute(
    "href",
    "/admin/users",
  );
});
```

New: (nothing — delete the block above; the test that follows it, if any, is unaffected since these blocks are independent `test(...)` calls, not nested.)

- [ ] **Step 6: Update `BottomNav.test.tsx`**

Read `shell/src/shell/chrome/BottomNav.test.tsx`, then apply:

Old:
```ts
    await userEvent.click(screen.getByRole("button", { name: "Plus" }));
    expect(screen.getByRole("link", { name: "Administration" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Données" })).toBeInTheDocument();
```

New:
```ts
    await userEvent.click(screen.getByRole("button", { name: "Plus" }));
    expect(screen.getByRole("link", { name: "Paramètres" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Données" })).toBeInTheDocument();
```

Old:
```ts
    expect(screen.getByRole("link", { name: "Automatisation" })).not.toHaveAttribute(
      "aria-current",
    );
    expect(screen.getByRole("link", { name: "Administration" })).not.toHaveAttribute(
      "aria-current",
    );
```

New:
```ts
    expect(screen.getByRole("link", { name: "Automatisation" })).not.toHaveAttribute(
      "aria-current",
    );
    expect(screen.getByRole("link", { name: "Paramètres" })).not.toHaveAttribute(
      "aria-current",
    );
```

- [ ] **Step 7: Remove the now-orphaned `domain.admin` i18n key**

Read `shell/src/i18n/catalog.fr.ts`, then apply:

Old:
```ts
  "domain.tasks": "Tâches",
  "domain.admin": "Administration",
  "domain.settings": "Paramètres",
```

New:
```ts
  "domain.tasks": "Tâches",
  "domain.settings": "Paramètres",
```

- [ ] **Step 8: Run the full affected test suite**

Run:
```bash
npx vitest run src/auth/capabilities.test.ts src/shell/chrome/DomainBar.test.tsx src/shell/chrome/BottomNav.test.tsx
```
Expected: PASS.

Then run: `grep -rn '"admin"' src/auth/capabilities.ts src/shell/chrome/domainRoutes.ts`
Expected: no output — confirms the `admin` `DomainId` literal is fully gone from both files.

- [ ] **Step 9: Run the full shell test suite**

Run: `npm test`
Expected: PASS, entirely green (this is the point in the plan where every file touched across Tasks 1–4 gets exercised together).

- [ ] **Step 10: Commit**

```bash
git add -A src/auth src/shell/chrome src/i18n/catalog.fr.ts
git commit -m "refactor(shell): fusionne le domaine admin dans settings

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Task 5: E2E — navigation fusionnée, persistance de la préférence

**Files:**
- Create: `shell/e2e/settings-page.spec.ts`

**Interfaces:**
- Consumes: `mockCore`, `mockMe`, `ADMIN_ME`, `READER_ME` (`shell/e2e/mocks.ts`, all pre-existing).

- [ ] **Step 1: Write the E2E spec**

Create `shell/e2e/settings-page.spec.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore, mockMe, ADMIN_ME, READER_ME } from "./mocks";

test("un profil sans privilège admin ne voit que Général dans la navigation Paramètres", async ({
  page,
}) => {
  await mockCore(page);
  await mockMe(page, READER_ME);
  await page.route("https://core.test/v1/notifications/preference", (route) =>
    route.fulfill({ json: { value: "all" } }),
  );
  await page.goto("/settings");
  await expect(page.getByRole("link", { name: "Général →" })).toBeVisible();
  for (const name of [
    "Extensions →",
    "Outils d'infrastructure →",
    "Rôles et privilèges →",
    "Utilisateurs →",
    "Collections →",
    "Moissonnage →",
    "Conformité (RGPD) →",
  ]) {
    await expect(page.getByRole("link", { name })).not.toBeVisible();
  }
});

test("un admin navigue de Paramètres vers Extensions sans repasser par la barre de domaines", async ({
  page,
}) => {
  await mockCore(page);
  await mockMe(page, ADMIN_ME);
  await page.route("https://core.test/v1/notifications/preference", (route) =>
    route.fulfill({ json: { value: "all" } }),
  );
  await page.route("https://core.test/v1/extensions**", (route) =>
    route.fulfill({ json: { extensions: [] } }),
  );
  await page.goto("/settings");
  await page.getByRole("link", { name: "Extensions →" }).click();
  await expect(page).toHaveURL(/\/admin\/extensions$/);
  await expect(page.getByRole("heading", { name: "Extensions" })).toBeVisible();
});

test("changer la préférence de notifications persiste après rechargement", async ({ page }) => {
  await mockCore(page);
  await mockMe(page, READER_ME);
  let preference = "all";
  await page.route("https://core.test/v1/notifications/preference", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = (await route.request().postDataJSON()) as { value: string };
      preference = body.value;
      await route.fulfill({ json: { value: preference } });
      return;
    }
    await route.fulfill({ json: { value: preference } });
  });
  await page.goto("/settings");
  await page.getByRole("radio", { name: "Échecs seulement" }).click();
  await expect(page.getByRole("radio", { name: "Échecs seulement" })).toBeChecked();
  await page.reload();
  await expect(page.getByRole("radio", { name: "Échecs seulement" })).toBeChecked();
});
```

- [ ] **Step 2: Run the new spec**

Run: `npx playwright test e2e/settings-page.spec.ts`
Expected: PASS (3 tests).

- [ ] **Step 3: Run the full E2E suite**

Run: `npm run e2e`
Expected: PASS, entirely green — this is the point where `triptych-narrow.spec.ts` (Task 3, Step 10) and every other spec touching `AdminNav`/domain navigation gets exercised together with the new `/settings` page.

- [ ] **Step 4: Commit**

```bash
git add e2e/settings-page.spec.ts
git commit -m "test(e2e): navigation Paramètres/Administration fusionnée, persistance de la préférence de notifications

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>"
```

---

## Self-Review Notes (completed during planning, kept for the implementer)

- **Spec coverage:** §2.1 (Profil/Notifications/Compte) → Task 3. §2.2 (fusion navigation, `SettingsNav`, entrée Général, domaine fusionné) → Tasks 2 and 4. §3 (fichiers touchés) → matches Tasks 1–4 file lists, plus `ConfigContext` (not anticipated in the spec's file list, needed once the `Compte` section's mock-mode masking was worked out precisely — `AppConfig` had no existing distribution mechanism to a route-level page). §4 (tests) → Tasks 2, 3, 4 (unit) and Task 5 (E2E). §5 (hors périmètre) → respected: no profile editing, no `/admin/*` URL change, no self-deletion. §6 (points d'attention) → the `AdminNav` rename's 7-file blast radius is Task 2 Step 7-8; the `getDomainPath` signature question is resolved in Task 4 Step 2-3 (fully removed, both call sites updated) since it turned out to have exactly 2 call sites, both trivial.
- **Type consistency:** `NotificationPreferenceValue` ("all" | "failuresOnly" | "none") flows unchanged from `api/types.ts` through `useNotificationPreference`/`useUpdateNotificationPreference` (Task 3) — the `Radio.Item` values match exactly. `roleLabel(me: Me | undefined): string` signature is identical between its Task 3 Step 1 definition and its two call sites (`AccountMenu.tsx`, `SettingsPage.tsx`). `SettingsNav`/`useConfig` exports match their import statements in `SettingsPage.tsx` (Task 3) exactly as produced in Tasks 1–2.
- **Placeholder scan:** none found — every step above either shows exact code or an exact shell command with an expected result.
