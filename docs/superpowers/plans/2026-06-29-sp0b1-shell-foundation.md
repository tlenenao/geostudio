# Shell Foundation (SP-0b.1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the authenticated GeoStudio shell foundation — a React/Vite/TypeScript app with Tailwind + shadcn-style UI, OIDC auth (with a mock mode for tests), a typed `item-client` façade over GeoNode + the Builder Service, and a browsable read-only item catalog with search/filter/pagination and an item detail page.

**Architecture:** A Vite SPA. `config` reads `VITE_*` env. `item-client` is a factory that injects the bearer token and maps GeoNode/Builder responses to a typed `Item`. TanStack Query hooks wrap the client. Auth uses `react-oidc-context` behind a thin `useAuth` wrapper with a `mock` mode for tests/E2E. React Router composes the shell layout, catalog, and item detail pages.

**Tech Stack:** React 19, Vite 6, TypeScript, Tailwind CSS v4 (`@tailwindcss/vite`), class-variance-authority + clsx + tailwind-merge (shadcn-style primitives), react-oidc-context, @tanstack/react-query, react-router-dom, Vitest + @testing-library/react + jsdom, MSW, Playwright.

## Global Constraints

- Node version floor: **20** (`node --version` ≥ v20).
- All app code lives under `shell/`. Package manager: **npm** (use `npm`, commit `package-lock.json`).
- No secret/token in `localStorage` — tokens stay in memory (oidc-client-ts default `WebStorageStateStore` is replaced by in-memory user store; see Task 5).
- All network access goes through `item-client`; no `fetch`/axios calls to GeoNode or the Builder Service anywhere else.
- All external URLs/ids come from `VITE_*` env via the `config` module; no hard-coded URLs.
- The Builder Service `ConfigRead` contract from SP-0a is consumed as-is; the GeoNode resource shape is mapped in `item-client` only.
- Test output must be clean (no unhandled-request warnings from MSW; `onUnhandledRequest: "error"`).
- Type names are fixed and shared across tasks: `AppConfig`, `Item`, `ItemPage`, `Me`, `ItemClient`, `ListItemsParams`.

---

### Task 1: Scaffold the shell app (Vite + TS + Tailwind v4 + Vitest)

**Files:**
- Create: `shell/package.json`
- Create: `shell/tsconfig.json`
- Create: `shell/tsconfig.node.json`
- Create: `shell/vite.config.ts`
- Create: `shell/index.html`
- Create: `shell/src/index.css`
- Create: `shell/src/main.tsx`
- Create: `shell/src/App.tsx`
- Create: `shell/src/test/setup.ts`
- Create: `shell/.gitignore`
- Test: `shell/src/App.test.tsx`

**Interfaces:**
- Consumes: nothing.
- Produces: `App` (default export, React component rendering a `<main>` with heading text `GeoStudio`); a working `npm test` (Vitest, jsdom) and `npm run build`.

- [ ] **Step 1: Create `shell/package.json`**

```json
{
  "name": "geostudio-shell",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc -b && vite build",
    "preview": "vite preview",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "react": "^19.0.0",
    "react-dom": "^19.0.0"
  },
  "devDependencies": {
    "@tailwindcss/vite": "^4.0.0",
    "@testing-library/jest-dom": "^6.4.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/user-event": "^14.5.0",
    "@types/react": "^19.0.0",
    "@types/react-dom": "^19.0.0",
    "@vitejs/plugin-react": "^4.3.0",
    "jsdom": "^25.0.0",
    "tailwindcss": "^4.0.0",
    "typescript": "^5.6.0",
    "vite": "^6.0.0",
    "vitest": "^2.1.0"
  }
}
```

- [ ] **Step 2: Create `shell/tsconfig.json` and `shell/tsconfig.node.json`**

`shell/tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "useDefineForClassFields": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "resolveJsonModule": true,
    "isolatedModules": true,
    "noEmit": true,
    "jsx": "react-jsx",
    "strict": true,
    "noUnusedLocals": true,
    "noUnusedParameters": true,
    "noFallthroughCasesInSwitch": true,
    "types": ["vitest/globals", "@testing-library/jest-dom"],
    "baseUrl": ".",
    "paths": { "@/*": ["src/*"] }
  },
  "include": ["src"],
  "references": [{ "path": "./tsconfig.node.json" }]
}
```

`shell/tsconfig.node.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "lib": ["ES2023"],
    "module": "ESNext",
    "skipLibCheck": true,
    "moduleResolution": "bundler",
    "allowImportingTsExtensions": true,
    "isolatedModules": true,
    "noEmit": true,
    "strict": true
  },
  "include": ["vite.config.ts"]
}
```

- [ ] **Step 3: Create `shell/vite.config.ts`**

```ts
/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { fileURLToPath, URL } from "node:url";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "jsdom",
    globals: true,
    setupFiles: ["./src/test/setup.ts"],
    css: true,
  },
});
```

- [ ] **Step 4: Create `shell/index.html`, `shell/src/index.css`, `shell/.gitignore`**

`shell/index.html`:

```html
<!doctype html>
<html lang="fr">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>GeoStudio</title>
  </head>
  <body>
    <div id="root"></div>
    <script type="module" src="/src/main.tsx"></script>
  </body>
</html>
```

`shell/src/index.css`:

```css
@import "tailwindcss";
```

`shell/.gitignore`:

```
node_modules/
dist/
*.local
.env
coverage/
playwright-report/
test-results/
```

- [ ] **Step 5: Create `shell/src/test/setup.ts`**

```ts
import "@testing-library/jest-dom/vitest";
```

- [ ] **Step 6: Write the failing test**

Create `shell/src/App.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import App from "./App";

test("renders the GeoStudio heading", () => {
  render(<App />);
  expect(
    screen.getByRole("heading", { name: /geostudio/i }),
  ).toBeInTheDocument();
});
```

- [ ] **Step 7: Run test to verify it fails**

Run (from `shell/`): `npm install` then `npm test`.
Expected: FAIL — cannot resolve `./App`.

- [ ] **Step 8: Create `shell/src/App.tsx` and `shell/src/main.tsx`**

`shell/src/App.tsx`:

```tsx
export default function App() {
  return (
    <main className="p-8">
      <h1 className="text-2xl font-semibold">GeoStudio</h1>
    </main>
  );
}
```

`shell/src/main.tsx`:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 9: Run tests and build**

Run: `npm test` → expect PASS (1 test). Then `npm run build` → expect success (dist produced).

- [ ] **Step 10: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/tsconfig.json shell/tsconfig.node.json shell/vite.config.ts shell/index.html shell/src/index.css shell/src/main.tsx shell/src/App.tsx shell/src/test/setup.ts shell/src/App.test.tsx shell/.gitignore
git commit -m "feat(shell): scaffold Vite React TS app with Tailwind v4 and Vitest"
```

---

### Task 2: Config module (`VITE_*` env)

**Files:**
- Create: `shell/src/config.ts`
- Test: `shell/src/config.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `type AppConfig = { geonodeUrl: string; builderUrl: string; oidcAuthority: string; oidcClientId: string; oidcRedirectUri: string; authMode: "oidc" | "mock" }`
  - `loadConfig(env: Record<string, string | undefined>): AppConfig` — reads `VITE_GEONODE_URL`, `VITE_BUILDER_URL`, `VITE_OIDC_AUTHORITY`, `VITE_OIDC_CLIENT_ID`, `VITE_OIDC_REDIRECT_URI`, `VITE_AUTH_MODE` (defaults to `"oidc"`); throws `Error` listing every missing required var. When `authMode === "mock"`, the OIDC vars are optional and default to empty strings.

- [ ] **Step 1: Write the failing test**

Create `shell/src/config.test.ts`:

```ts
import { loadConfig } from "./config";

const base = {
  VITE_GEONODE_URL: "https://geonode.test",
  VITE_BUILDER_URL: "https://builder.test",
  VITE_OIDC_AUTHORITY: "https://kc.test/realms/gis",
  VITE_OIDC_CLIENT_ID: "shell",
  VITE_OIDC_REDIRECT_URI: "https://app.test/callback",
};

test("loads a full oidc config", () => {
  const cfg = loadConfig(base);
  expect(cfg.geonodeUrl).toBe("https://geonode.test");
  expect(cfg.authMode).toBe("oidc");
  expect(cfg.oidcClientId).toBe("shell");
});

test("throws listing all missing required vars in oidc mode", () => {
  expect(() => loadConfig({})).toThrow(/VITE_GEONODE_URL/);
  expect(() => loadConfig({})).toThrow(/VITE_OIDC_AUTHORITY/);
});

test("mock mode does not require oidc vars", () => {
  const cfg = loadConfig({
    VITE_GEONODE_URL: "https://geonode.test",
    VITE_BUILDER_URL: "https://builder.test",
    VITE_AUTH_MODE: "mock",
  });
  expect(cfg.authMode).toBe("mock");
  expect(cfg.oidcAuthority).toBe("");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/config.test.ts`
Expected: FAIL — cannot resolve `./config`.

- [ ] **Step 3: Create `shell/src/config.ts`**

```ts
export type AppConfig = {
  geonodeUrl: string;
  builderUrl: string;
  oidcAuthority: string;
  oidcClientId: string;
  oidcRedirectUri: string;
  authMode: "oidc" | "mock";
};

export function loadConfig(env: Record<string, string | undefined>): AppConfig {
  const authMode = env.VITE_AUTH_MODE === "mock" ? "mock" : "oidc";

  const required: Record<string, string | undefined> = {
    VITE_GEONODE_URL: env.VITE_GEONODE_URL,
    VITE_BUILDER_URL: env.VITE_BUILDER_URL,
  };
  if (authMode === "oidc") {
    required.VITE_OIDC_AUTHORITY = env.VITE_OIDC_AUTHORITY;
    required.VITE_OIDC_CLIENT_ID = env.VITE_OIDC_CLIENT_ID;
    required.VITE_OIDC_REDIRECT_URI = env.VITE_OIDC_REDIRECT_URI;
  }

  const missing = Object.entries(required)
    .filter(([, value]) => !value)
    .map(([key]) => key);
  if (missing.length > 0) {
    throw new Error(`Missing required env vars: ${missing.join(", ")}`);
  }

  return {
    geonodeUrl: env.VITE_GEONODE_URL!,
    builderUrl: env.VITE_BUILDER_URL!,
    oidcAuthority: env.VITE_OIDC_AUTHORITY ?? "",
    oidcClientId: env.VITE_OIDC_CLIENT_ID ?? "",
    oidcRedirectUri: env.VITE_OIDC_REDIRECT_URI ?? "",
    authMode,
  };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- src/config.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/config.ts shell/src/config.test.ts
git commit -m "feat(shell): add env-driven config loader"
```

---

### Task 3: `item-client` façade + MSW handlers

**Files:**
- Create: `shell/src/api/types.ts`
- Create: `shell/src/api/itemClient.ts`
- Create: `shell/src/test/msw/handlers.ts`
- Create: `shell/src/test/msw/server.ts`
- Modify: `shell/src/test/setup.ts`
- Modify: `shell/package.json` (add `msw` dev dependency)
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `shell/src/api/types.ts`:
    - `type ResourceType = "app" | "dashboard" | "map"`
    - `type Item = { pk: string; resourceType: ResourceType; title: string; abstract: string; owner: string; thumbnailUrl: string | null; date: string; configId: string | null }`
    - `type ItemPage = { items: Item[]; total: number; page: number; pageSize: number }`
    - `type Me = { username: string; firstName: string; lastName: string }`
    - `type ListItemsParams = { q?: string; type?: ResourceType; page?: number; pageSize?: number }`
    - `interface ItemClient { listItems(params?: ListItemsParams): Promise<ItemPage>; getItem(pk: string): Promise<Item>; getMe(): Promise<Me> }`
  - `shell/src/api/itemClient.ts`: `createItemClient(opts: { geonodeUrl: string; builderUrl: string; getToken: () => string | undefined }): ItemClient`. Calls `GET {geonodeUrl}/api/v2/resources?search={q}&filter{resource_type.in}={type}&page={page}&page_size={pageSize}`, `GET {geonodeUrl}/api/v2/resources/{pk}`, `GET {geonodeUrl}/api/v2/users/me`. Sends `Authorization: Bearer {token}` when a token exists. Throws `Error` with the status code on non-2xx.

- [ ] **Step 1: Add MSW dependency**

Add `"msw": "^2.4.0"` to `devDependencies` in `shell/package.json`, then run `npm install`.

- [ ] **Step 2: Create `shell/src/api/types.ts`**

```ts
export type ResourceType = "app" | "dashboard" | "map";

export type Item = {
  pk: string;
  resourceType: ResourceType;
  title: string;
  abstract: string;
  owner: string;
  thumbnailUrl: string | null;
  date: string;
  configId: string | null;
};

export type ItemPage = {
  items: Item[];
  total: number;
  page: number;
  pageSize: number;
};

export type Me = {
  username: string;
  firstName: string;
  lastName: string;
};

export type ListItemsParams = {
  q?: string;
  type?: ResourceType;
  page?: number;
  pageSize?: number;
};

export interface ItemClient {
  listItems(params?: ListItemsParams): Promise<ItemPage>;
  getItem(pk: string): Promise<Item>;
  getMe(): Promise<Me>;
}
```

- [ ] **Step 3: Create MSW handlers and server**

`shell/src/test/msw/handlers.ts`:

```ts
import { http, HttpResponse } from "msw";

const GEONODE = "https://geonode.test";

function resource(pk: string, type = "app", title = `Item ${pk}`) {
  return {
    pk,
    resource_type: type,
    title,
    abstract: `Abstract ${pk}`,
    owner: { username: "alice" },
    thumbnail_url: `${GEONODE}/thumbs/${pk}.png`,
    date: "2026-01-01T00:00:00Z",
  };
}

export const handlers = [
  http.get(`${GEONODE}/api/v2/resources`, ({ request }) => {
    const url = new URL(request.url);
    const search = url.searchParams.get("search");
    const all = [resource("1", "app", "Alpha"), resource("2", "dashboard", "Beta")];
    const filtered = search
      ? all.filter((r) => r.title.toLowerCase().includes(search.toLowerCase()))
      : all;
    return HttpResponse.json({
      total: filtered.length,
      page: Number(url.searchParams.get("page") ?? "1"),
      page_size: Number(url.searchParams.get("page_size") ?? "12"),
      resources: filtered,
    });
  }),

  http.get(`${GEONODE}/api/v2/resources/:pk`, ({ params }) => {
    const pk = String(params.pk);
    if (pk === "404") return new HttpResponse(null, { status: 404 });
    return HttpResponse.json({ resource: resource(pk) });
  }),

  http.get(`${GEONODE}/api/v2/users/me`, () =>
    HttpResponse.json({
      user: { username: "alice", first_name: "Alice", last_name: "Martin" },
    }),
  ),
];
```

`shell/src/test/msw/server.ts`:

```ts
import { setupServer } from "msw/node";
import { handlers } from "./handlers";

export const server = setupServer(...handlers);
```

- [ ] **Step 4: Wire MSW into `shell/src/test/setup.ts`**

Replace the contents of `shell/src/test/setup.ts` with:

```ts
import "@testing-library/jest-dom/vitest";
import { afterAll, afterEach, beforeAll } from "vitest";
import { server } from "./msw/server";

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
```

- [ ] **Step 5: Write the failing test**

Create `shell/src/api/itemClient.test.ts`:

```ts
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "./itemClient";

function makeClient(token: string | undefined = "test-token") {
  return createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => token,
  });
}

test("listItems maps GeoNode resources to Items", async () => {
  const page = await makeClient().listItems();
  expect(page.total).toBe(2);
  expect(page.items[0]).toMatchObject({
    pk: "1",
    resourceType: "app",
    title: "Alpha",
    owner: "alice",
  });
});

test("listItems forwards the search term", async () => {
  const page = await makeClient().listItems({ q: "beta" });
  expect(page.items).toHaveLength(1);
  expect(page.items[0].title).toBe("Beta");
});

test("listItems sends the bearer token", async () => {
  let auth: string | null = null;
  server.use(
    http.get("https://geonode.test/api/v2/resources", ({ request }) => {
      auth = request.headers.get("authorization");
      return HttpResponse.json({ total: 0, page: 1, page_size: 12, resources: [] });
    }),
  );
  await makeClient("abc").listItems();
  expect(auth).toBe("Bearer abc");
});

test("getItem maps a single resource", async () => {
  const item = await makeClient().getItem("7");
  expect(item.pk).toBe("7");
  expect(item.thumbnailUrl).toContain("/thumbs/7.png");
});

test("getItem throws on 404", async () => {
  await expect(makeClient().getItem("404")).rejects.toThrow(/404/);
});

test("getMe maps the current user", async () => {
  const me = await makeClient().getMe();
  expect(me).toEqual({ username: "alice", firstName: "Alice", lastName: "Martin" });
});
```

- [ ] **Step 6: Run test to verify it fails**

Run: `npm test -- src/api/itemClient.test.ts`
Expected: FAIL — cannot resolve `./itemClient`.

- [ ] **Step 7: Create `shell/src/api/itemClient.ts`**

```ts
import type { Item, ItemClient, ItemPage, ListItemsParams, Me, ResourceType } from "./types";

type GeoNodeResource = {
  pk: number | string;
  resource_type: string;
  title: string;
  abstract?: string;
  owner?: { username?: string };
  thumbnail_url?: string | null;
  date?: string;
};

function toItem(r: GeoNodeResource): Item {
  return {
    pk: String(r.pk),
    resourceType: (r.resource_type as ResourceType) ?? "map",
    title: r.title,
    abstract: r.abstract ?? "",
    owner: r.owner?.username ?? "",
    thumbnailUrl: r.thumbnail_url ?? null,
    date: r.date ?? "",
    configId: null,
  };
}

export function createItemClient(opts: {
  geonodeUrl: string;
  builderUrl: string;
  getToken: () => string | undefined;
}): ItemClient {
  const { geonodeUrl, getToken } = opts;

  async function get<T>(path: string): Promise<T> {
    const token = getToken();
    const res = await fetch(`${geonodeUrl}${path}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status} ${path}`);
    }
    return (await res.json()) as T;
  }

  return {
    async listItems(params: ListItemsParams = {}): Promise<ItemPage> {
      const q = new URLSearchParams();
      if (params.q) q.set("search", params.q);
      if (params.type) q.set("filter{resource_type}", params.type);
      q.set("page", String(params.page ?? 1));
      q.set("page_size", String(params.pageSize ?? 12));
      const data = await get<{
        total: number;
        page: number;
        page_size: number;
        resources: GeoNodeResource[];
      }>(`/api/v2/resources?${q.toString()}`);
      return {
        items: data.resources.map(toItem),
        total: data.total,
        page: data.page,
        pageSize: data.page_size,
      };
    },

    async getItem(pk: string): Promise<Item> {
      const data = await get<{ resource: GeoNodeResource }>(`/api/v2/resources/${pk}`);
      return toItem(data.resource);
    },

    async getMe(): Promise<Me> {
      const data = await get<{
        user: { username: string; first_name?: string; last_name?: string };
      }>(`/api/v2/users/me`);
      return {
        username: data.user.username,
        firstName: data.user.first_name ?? "",
        lastName: data.user.last_name ?? "",
      };
    },
  };
}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `npm test -- src/api/itemClient.test.ts`
Expected: PASS (6 tests).

- [ ] **Step 9: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/src/api shell/src/test
git commit -m "feat(shell): add typed item-client façade over GeoNode with MSW tests"
```

---

### Task 4: TanStack Query hooks + ItemClient context

**Files:**
- Create: `shell/src/api/ItemClientProvider.tsx`
- Create: `shell/src/api/hooks.ts`
- Modify: `shell/package.json` (add `@tanstack/react-query`)
- Test: `shell/src/api/hooks.test.tsx`

**Interfaces:**
- Consumes: `ItemClient`, `ListItemsParams`, `ItemPage`, `Item`, `Me` from `./types`; `createItemClient` from `./itemClient`.
- Produces:
  - `ItemClientProvider({ client, children }: { client: ItemClient; children: React.ReactNode })` — React context provider.
  - `useItemClient(): ItemClient` — throws if used outside the provider.
  - `useItems(params: ListItemsParams)` → TanStack `UseQueryResult<ItemPage>` (queryKey `["items", params]`).
  - `useItem(pk: string)` → `UseQueryResult<Item>` (queryKey `["item", pk]`).
  - `useMe()` → `UseQueryResult<Me>` (queryKey `["me"]`).

- [ ] **Step 1: Add dependency**

Add `"@tanstack/react-query": "^5.59.0"` to `dependencies` in `shell/package.json`, then `npm install`.

- [ ] **Step 2: Write the failing test**

Create `shell/src/api/hooks.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { renderHook, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { createItemClient } from "./itemClient";
import { ItemClientProvider } from "./ItemClientProvider";
import { useItems, useMe } from "./hooks";

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "test-token",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("useItems returns the mapped page", async () => {
  const { result } = renderHook(() => useItems({}), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.total).toBe(2);
});

test("useMe returns the current user", async () => {
  const { result } = renderHook(() => useMe(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.username).toBe("alice");
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `npm test -- src/api/hooks.test.tsx`
Expected: FAIL — cannot resolve `./hooks` / `./ItemClientProvider`.

- [ ] **Step 4: Create `shell/src/api/ItemClientProvider.tsx`**

```tsx
import { createContext, useContext } from "react";
import type { ItemClient } from "./types";

const ItemClientContext = createContext<ItemClient | null>(null);

export function ItemClientProvider({
  client,
  children,
}: {
  client: ItemClient;
  children: React.ReactNode;
}) {
  return (
    <ItemClientContext.Provider value={client}>{children}</ItemClientContext.Provider>
  );
}

export function useItemClient(): ItemClient {
  const client = useContext(ItemClientContext);
  if (!client) {
    throw new Error("useItemClient must be used within an ItemClientProvider");
  }
  return client;
}
```

- [ ] **Step 5: Create `shell/src/api/hooks.ts`**

```ts
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "./ItemClientProvider";
import type { ListItemsParams } from "./types";

export function useItems(params: ListItemsParams) {
  const client = useItemClient();
  return useQuery({
    queryKey: ["items", params],
    queryFn: () => client.listItems(params),
  });
}

export function useItem(pk: string) {
  const client = useItemClient();
  return useQuery({
    queryKey: ["item", pk],
    queryFn: () => client.getItem(pk),
  });
}

export function useMe() {
  const client = useItemClient();
  return useQuery({ queryKey: ["me"], queryFn: () => client.getMe() });
}
```

- [ ] **Step 6: Run test to verify it passes**

Run: `npm test -- src/api/hooks.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 7: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/src/api/ItemClientProvider.tsx shell/src/api/hooks.ts shell/src/api/hooks.test.tsx
git commit -m "feat(shell): add TanStack Query hooks and item-client context"
```

---

### Task 5: Auth (OIDC wrapper + mock mode + RequireAuth)

**Files:**
- Create: `shell/src/auth/useAuth.ts`
- Create: `shell/src/auth/AuthProvider.tsx`
- Create: `shell/src/auth/RequireAuth.tsx`
- Modify: `shell/package.json` (add `react-oidc-context`, `oidc-client-ts`)
- Test: `shell/src/auth/RequireAuth.test.tsx`

**Interfaces:**
- Consumes: `AppConfig` from `../config`.
- Produces:
  - `type AuthState = { isLoading: boolean; isAuthenticated: boolean; username: string | null; getAccessToken: () => string | undefined; signIn: () => void; signOut: () => void }`
  - `useAuth(): AuthState` — wraps `react-oidc-context`'s `useAuth`, mapping to `AuthState`.
  - `AuthProvider({ config, children })` — when `config.authMode === "oidc"`, renders `react-oidc-context`'s `<AuthProvider>` configured with in-memory user store (no localStorage); when `"mock"`, renders a context that reports an authenticated user `"mockuser"` with token `"mock-token"`.
  - `RequireAuth({ children })` — uses `useAuth`: while `isLoading` renders a `role="status"` loading element; if not authenticated calls `signIn()` once and renders nothing; otherwise renders `children`.
- For tests, the `useAuth` module is mocked via `vi.mock`.

- [ ] **Step 1: Add dependencies**

Add to `shell/package.json` `dependencies`: `"react-oidc-context": "^3.2.0"`, `"oidc-client-ts": "^3.1.0"`. Run `npm install`.

- [ ] **Step 2: Create `shell/src/auth/useAuth.ts`**

```ts
import { useAuth as useOidcAuth } from "react-oidc-context";

export type AuthState = {
  isLoading: boolean;
  isAuthenticated: boolean;
  username: string | null;
  getAccessToken: () => string | undefined;
  signIn: () => void;
  signOut: () => void;
};

export function useAuth(): AuthState {
  const oidc = useOidcAuth();
  return {
    isLoading: oidc.isLoading,
    isAuthenticated: oidc.isAuthenticated,
    username: (oidc.user?.profile.preferred_username as string) ?? null,
    getAccessToken: () => oidc.user?.access_token,
    signIn: () => void oidc.signinRedirect(),
    signOut: () => void oidc.signoutRedirect(),
  };
}
```

- [ ] **Step 3: Create `shell/src/auth/AuthProvider.tsx`**

```tsx
import { AuthProvider as OidcProvider } from "react-oidc-context";
import { WebStorageStateStore } from "oidc-client-ts";
import { createContext } from "react";
import type { AppConfig } from "../config";

// Mock context value mirrors the react-oidc-context User minimally; only used in tests/E2E.
export const MockAuthContext = createContext(true);

export function AuthProvider({
  config,
  children,
}: {
  config: AppConfig;
  children: React.ReactNode;
}) {
  if (config.authMode === "mock") {
    return <MockAuthContext.Provider value={true}>{children}</MockAuthContext.Provider>;
  }
  return (
    <OidcProvider
      authority={config.oidcAuthority}
      client_id={config.oidcClientId}
      redirect_uri={config.oidcRedirectUri}
      response_type="code"
      scope="openid profile email"
      // In-memory store: nothing persisted to localStorage.
      userStore={new WebStorageStateStore({ store: new InMemoryStore() })}
    >
      {children}
    </OidcProvider>
  );
}

// Minimal in-memory implementation of oidc-client-ts AsyncStorage.
class InMemoryStore {
  private data = new Map<string, string>();
  async getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  async setItem(key: string, value: string) {
    this.data.set(key, value);
  }
  async removeItem(key: string) {
    this.data.delete(key);
  }
  async getAllKeys() {
    return [...this.data.keys()];
  }
}
```

Note for the implementer: `react-oidc-context` re-exports nothing for the mock path; in mock mode we deliberately bypass it and the mocked `useAuth` (Task 7 wiring / E2E) supplies the authenticated state. The `MockAuthContext` is a marker so the tree still has a provider.

- [ ] **Step 4: Write the failing test**

Create `shell/src/auth/RequireAuth.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { AuthState } from "./useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: false,
  username: null,
  getAccessToken: () => undefined,
  signIn: vi.fn(),
  signOut: vi.fn(),
};

vi.mock("./useAuth", () => ({ useAuth: () => authState }));

// Import after the mock is registered.
const { RequireAuth } = await import("./RequireAuth");

afterEach(() => {
  authState.isLoading = false;
  authState.isAuthenticated = false;
  (authState.signIn as ReturnType<typeof vi.fn>).mockClear();
});

test("shows loading while auth resolves", () => {
  authState.isLoading = true;
  render(<RequireAuth><div>secret</div></RequireAuth>);
  expect(screen.getByRole("status")).toBeInTheDocument();
  expect(screen.queryByText("secret")).not.toBeInTheDocument();
});

test("triggers signIn and hides children when unauthenticated", () => {
  authState.isAuthenticated = false;
  render(<RequireAuth><div>secret</div></RequireAuth>);
  expect(authState.signIn).toHaveBeenCalledTimes(1);
  expect(screen.queryByText("secret")).not.toBeInTheDocument();
});

test("renders children when authenticated", () => {
  authState.isAuthenticated = true;
  render(<RequireAuth><div>secret</div></RequireAuth>);
  expect(screen.getByText("secret")).toBeInTheDocument();
});
```

- [ ] **Step 5: Run test to verify it fails**

Run: `npm test -- src/auth/RequireAuth.test.tsx`
Expected: FAIL — cannot resolve `./RequireAuth`.

- [ ] **Step 6: Create `shell/src/auth/RequireAuth.tsx`**

```tsx
import { useEffect } from "react";
import { useAuth } from "./useAuth";

export function RequireAuth({ children }: { children: React.ReactNode }) {
  const { isLoading, isAuthenticated, signIn } = useAuth();

  useEffect(() => {
    if (!isLoading && !isAuthenticated) {
      signIn();
    }
  }, [isLoading, isAuthenticated, signIn]);

  if (isLoading) {
    return (
      <div role="status" className="p-8 text-sm text-muted-foreground">
        Connexion…
      </div>
    );
  }
  if (!isAuthenticated) {
    return null;
  }
  return <>{children}</>;
}
```

- [ ] **Step 7: Run test to verify it passes**

Run: `npm test -- src/auth/RequireAuth.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 8: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/src/auth
git commit -m "feat(shell): add OIDC auth wrapper, in-memory token store, RequireAuth guard"
```

---

### Task 6: UI primitives + ItemCard

**Files:**
- Create: `shell/src/lib/utils.ts`
- Create: `shell/src/ui/button.tsx`
- Create: `shell/src/ui/input.tsx`
- Create: `shell/src/ui/card.tsx`
- Create: `shell/src/ui/ItemCard.tsx`
- Modify: `shell/package.json` (add `clsx`, `tailwind-merge`, `class-variance-authority`)
- Test: `shell/src/ui/ItemCard.test.tsx`

**Interfaces:**
- Consumes: `Item` from `../api/types`.
- Produces:
  - `cn(...inputs: ClassValue[]): string` in `lib/utils.ts`.
  - `Button`, `Input`, `Card` (shadcn-style) in `ui/`.
  - `ItemCard({ item, onOpen }: { item: Item; onOpen: (pk: string) => void })` — renders the title (as a heading), the resource type badge, and an "Ouvrir" button that calls `onOpen(item.pk)`.

- [ ] **Step 1: Add dependencies**

Add to `shell/package.json` `dependencies`: `"clsx": "^2.1.0"`, `"tailwind-merge": "^2.5.0"`, `"class-variance-authority": "^0.7.0"`. Run `npm install`.

- [ ] **Step 2: Create `shell/src/lib/utils.ts`**

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]): string {
  return twMerge(clsx(inputs));
}
```

- [ ] **Step 3: Create `shell/src/ui/button.tsx`**

```tsx
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../lib/utils";

const buttonVariants = cva(
  "inline-flex items-center justify-center rounded-md text-sm font-medium transition-colors focus-visible:outline-none focus-visible:ring-2 disabled:pointer-events-none disabled:opacity-50",
  {
    variants: {
      variant: {
        default: "bg-slate-900 text-white hover:bg-slate-800",
        outline: "border border-slate-300 bg-white hover:bg-slate-100",
        ghost: "hover:bg-slate-100",
      },
      size: { default: "h-9 px-4 py-2", sm: "h-8 px-3", icon: "h-9 w-9" },
    },
    defaultVariants: { variant: "default", size: "default" },
  },
);

export type ButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> &
  VariantProps<typeof buttonVariants>;

export function Button({ className, variant, size, ...props }: ButtonProps) {
  return (
    <button className={cn(buttonVariants({ variant, size }), className)} {...props} />
  );
}
```

- [ ] **Step 4: Create `shell/src/ui/input.tsx` and `shell/src/ui/card.tsx`**

`shell/src/ui/input.tsx`:

```tsx
import { cn } from "../lib/utils";

export function Input({
  className,
  ...props
}: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm focus-visible:outline-none focus-visible:ring-2",
        className,
      )}
      {...props}
    />
  );
}
```

`shell/src/ui/card.tsx`:

```tsx
import { cn } from "../lib/utils";

export function Card({
  className,
  ...props
}: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-lg border border-slate-200 bg-white shadow-sm", className)}
      {...props}
    />
  );
}
```

- [ ] **Step 5: Write the failing test**

Create `shell/src/ui/ItemCard.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { Item } from "../api/types";
import { ItemCard } from "./ItemCard";

const item: Item = {
  pk: "42",
  resourceType: "dashboard",
  title: "Suivi incidents",
  abstract: "Tableau de bord",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-01-01T00:00:00Z",
  configId: null,
};

test("renders title and type", () => {
  render(<ItemCard item={item} onOpen={() => {}} />);
  expect(screen.getByRole("heading", { name: "Suivi incidents" })).toBeInTheDocument();
  expect(screen.getByText(/dashboard/i)).toBeInTheDocument();
});

test("calls onOpen with the pk", async () => {
  const onOpen = vi.fn();
  render(<ItemCard item={item} onOpen={onOpen} />);
  await userEvent.click(screen.getByRole("button", { name: /ouvrir/i }));
  expect(onOpen).toHaveBeenCalledWith("42");
});
```

- [ ] **Step 6: Run test to verify it fails**

Run: `npm test -- src/ui/ItemCard.test.tsx`
Expected: FAIL — cannot resolve `./ItemCard`.

- [ ] **Step 7: Create `shell/src/ui/ItemCard.tsx`**

```tsx
import type { Item } from "../api/types";
import { Button } from "./button";
import { Card } from "./card";

export function ItemCard({
  item,
  onOpen,
}: {
  item: Item;
  onOpen: (pk: string) => void;
}) {
  return (
    <Card className="flex flex-col gap-2 p-4">
      <span className="w-fit rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
        {item.resourceType}
      </span>
      <h3 className="text-base font-semibold">{item.title}</h3>
      <p className="line-clamp-2 text-sm text-slate-500">{item.abstract}</p>
      <Button size="sm" className="mt-2 w-fit" onClick={() => onOpen(item.pk)}>
        Ouvrir
      </Button>
    </Card>
  );
}
```

- [ ] **Step 8: Run test to verify it passes**

Run: `npm test -- src/ui/ItemCard.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 9: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/src/lib shell/src/ui
git commit -m "feat(shell): add shadcn-style UI primitives and ItemCard"
```

---

### Task 7: Catalog page (search / filter / pagination / states)

**Files:**
- Create: `shell/src/pages/CatalogPage.tsx`
- Test: `shell/src/pages/CatalogPage.test.tsx`

**Interfaces:**
- Consumes: `useItems` from `../api/hooks`; `ItemCard` from `../ui/ItemCard`; `Input`, `Button` from `../ui/*`.
- Produces: `CatalogPage({ onOpenItem }: { onOpenItem: (pk: string) => void })` — search input (label "Rechercher"), a type `<select>` (label "Type": all/app/dashboard/map), a grid of `ItemCard`, Prev/Next pagination, and loading / error / empty states. Local state holds `q`, `type`, `page`; passes them to `useItems`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/pages/CatalogPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { CatalogPage } from "./CatalogPage";

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "test-token",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("lists items from the catalog", async () => {
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  expect(await screen.findByText("Alpha")).toBeInTheDocument();
  expect(screen.getByText("Beta")).toBeInTheDocument();
});

test("filters by search term", async () => {
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  await screen.findByText("Alpha");
  await userEvent.type(screen.getByLabelText("Rechercher"), "beta");
  await waitFor(() => expect(screen.queryByText("Alpha")).not.toBeInTheDocument());
  expect(screen.getByText("Beta")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/pages/CatalogPage.test.tsx`
Expected: FAIL — cannot resolve `./CatalogPage`.

- [ ] **Step 3: Create `shell/src/pages/CatalogPage.tsx`**

```tsx
import { useState } from "react";
import { useItems } from "../api/hooks";
import type { ResourceType } from "../api/types";
import { ItemCard } from "../ui/ItemCard";
import { Input } from "../ui/input";
import { Button } from "../ui/button";

const PAGE_SIZE = 12;

export function CatalogPage({ onOpenItem }: { onOpenItem: (pk: string) => void }) {
  const [q, setQ] = useState("");
  const [type, setType] = useState<ResourceType | "">("");
  const [page, setPage] = useState(1);

  const query = useItems({
    q: q || undefined,
    type: type || undefined,
    page,
    pageSize: PAGE_SIZE,
  });

  const totalPages = query.data ? Math.max(1, Math.ceil(query.data.total / PAGE_SIZE)) : 1;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1 text-sm">
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
        <label className="flex flex-col gap-1 text-sm">
          Type
          <select
            aria-label="Type"
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
            value={type}
            onChange={(e) => {
              setType(e.target.value as ResourceType | "");
              setPage(1);
            }}
          >
            <option value="">Tous</option>
            <option value="app">App</option>
            <option value="dashboard">Dashboard</option>
            <option value="map">Map</option>
          </select>
        </label>
      </div>

      {query.isLoading && <p role="status">Chargement…</p>}
      {query.isError && (
        <div role="alert" className="text-sm text-red-600">
          Erreur de chargement.{" "}
          <Button size="sm" variant="outline" onClick={() => query.refetch()}>
            Réessayer
          </Button>
        </div>
      )}
      {query.isSuccess && query.data.items.length === 0 && (
        <p className="text-sm text-slate-500">Aucun élément.</p>
      )}

      {query.isSuccess && query.data.items.length > 0 && (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {query.data.items.map((item) => (
            <ItemCard key={item.pk} item={item} onOpen={onOpenItem} />
          ))}
        </div>
      )}

      <div className="flex items-center gap-3">
        <Button
          size="sm"
          variant="outline"
          disabled={page <= 1}
          onClick={() => setPage((p) => Math.max(1, p - 1))}
        >
          Précédent
        </Button>
        <span className="text-sm text-slate-500">
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
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- src/pages/CatalogPage.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/CatalogPage.tsx shell/src/pages/CatalogPage.test.tsx
git commit -m "feat(shell): add catalog page with search, filter, pagination"
```

---

### Task 8: Item detail page

**Files:**
- Create: `shell/src/pages/ItemDetailPage.tsx`
- Test: `shell/src/pages/ItemDetailPage.test.tsx`

**Interfaces:**
- Consumes: `useItem` from `../api/hooks`.
- Produces: `ItemDetailPage({ pk }: { pk: string })` — renders the item title (heading), abstract, type, owner, and a disabled "Ouvrir dans l'éditeur" button (the editor arrives in SP-0d). Loading / error states. Uses `useItem(pk)`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/pages/ItemDetailPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ItemDetailPage } from "./ItemDetailPage";

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "test-token",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("shows the item detail", async () => {
  render(<ItemDetailPage pk="7" />, { wrapper });
  expect(await screen.findByRole("heading", { name: "Item 7" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /éditeur/i })).toBeDisabled();
});

test("shows an error for a missing item", async () => {
  render(<ItemDetailPage pk="404" />, { wrapper });
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm test -- src/pages/ItemDetailPage.test.tsx`
Expected: FAIL — cannot resolve `./ItemDetailPage`.

- [ ] **Step 3: Create `shell/src/pages/ItemDetailPage.tsx`**

```tsx
import { useItem } from "../api/hooks";
import { Button } from "../ui/button";

export function ItemDetailPage({ pk }: { pk: string }) {
  const query = useItem(pk);

  if (query.isLoading) return <p role="status">Chargement…</p>;
  if (query.isError || !query.data)
    return (
      <p role="alert" className="text-sm text-red-600">
        Élément introuvable.
      </p>
    );

  const item = query.data;
  return (
    <article className="flex flex-col gap-3">
      <span className="w-fit rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
        {item.resourceType}
      </span>
      <h2 className="text-xl font-semibold">{item.title}</h2>
      <p className="text-sm text-slate-500">Propriétaire : {item.owner}</p>
      <p className="text-sm">{item.abstract}</p>
      <Button className="w-fit" disabled title="Disponible avec l'éditeur (SP-0d)">
        Ouvrir dans l'éditeur
      </Button>
    </article>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `npm test -- src/pages/ItemDetailPage.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/ItemDetailPage.tsx shell/src/pages/ItemDetailPage.test.tsx
git commit -m "feat(shell): add read-only item detail page"
```

---

### Task 9: App shell (layout + router + provider composition)

**Files:**
- Create: `shell/src/shell/AppLayout.tsx`
- Create: `shell/src/shell/routes.tsx`
- Modify: `shell/src/App.tsx`
- Modify: `shell/src/main.tsx`
- Modify: `shell/package.json` (add `react-router-dom`)
- Test: `shell/src/shell/AppLayout.test.tsx`
- Test: `shell/src/shell/routes.test.tsx`

**Interfaces:**
- Consumes: `useAuth` from `../auth/useAuth`; `CatalogPage`, `ItemDetailPage`; React Router.
- Produces:
  - `AppLayout({ children })` — header with brand "GeoStudio", the username (from `useAuth`), a "Déconnexion" button calling `signOut`, a sidebar nav link "Catalogue", and a `<main>` for content.
  - `routes.tsx` exporting `AppRoutes()` — `<Routes>` with `/` → `CatalogPage` (navigates to `/items/:pk` on open) and `/items/:pk` → `ItemDetailPage`. Uses `useNavigate` / `useParams`.
  - `App.tsx` composes: `AuthProvider(config)` → `QueryClientProvider` → `ItemClientProvider(client)` → `BrowserRouter` → `RequireAuth` → `AppLayout` → `AppRoutes`. The `item-client` is created with `getToken` bound to `useAuth().getAccessToken` (via a small inner component so the hook runs inside `AuthProvider`).

- [ ] **Step 1: Add dependency**

Add `"react-router-dom": "^6.26.0"` to `shell/package.json` `dependencies`. Run `npm install`.

- [ ] **Step 2: Write the failing tests**

Create `shell/src/shell/AppLayout.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "alice",
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

const { AppLayout } = await import("./AppLayout");

test("shows brand, username and sign-out", async () => {
  render(<AppLayout><div>content</div></AppLayout>);
  expect(screen.getByText("GeoStudio")).toBeInTheDocument();
  expect(screen.getByText("alice")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /déconnexion/i }));
  expect(authState.signOut).toHaveBeenCalled();
});
```

Create `shell/src/shell/routes.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRoutes } from "./routes";

function wrap(children: ReactNode, initial = "/") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "t",
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("navigates from catalog to item detail on open", async () => {
  wrap(<AppRoutes />);
  await userEvent.click((await screen.findAllByRole("button", { name: /ouvrir/i }))[0]);
  expect(await screen.findByRole("heading", { name: /item 1/i })).toBeInTheDocument();
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `npm test -- src/shell/`
Expected: FAIL — cannot resolve `./AppLayout` / `./routes`.

- [ ] **Step 4: Create `shell/src/shell/AppLayout.tsx`**

```tsx
import { Link } from "react-router-dom";
import { useAuth } from "../auth/useAuth";
import { Button } from "../ui/button";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const { username, signOut } = useAuth();
  return (
    <div className="flex min-h-screen flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 px-6 py-3">
        <span className="text-lg font-bold">GeoStudio</span>
        <div className="flex items-center gap-3 text-sm">
          <span>{username}</span>
          <Button size="sm" variant="outline" onClick={signOut}>
            Déconnexion
          </Button>
        </div>
      </header>
      <div className="flex flex-1">
        <nav className="w-48 border-r border-slate-200 p-4">
          <Link to="/" className="text-sm font-medium hover:underline">
            Catalogue
          </Link>
        </nav>
        <main className="flex-1 p-6">{children}</main>
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Create `shell/src/shell/routes.tsx`**

```tsx
import { Routes, Route, useNavigate, useParams } from "react-router-dom";
import { CatalogPage } from "../pages/CatalogPage";
import { ItemDetailPage } from "../pages/ItemDetailPage";

function CatalogRoute() {
  const navigate = useNavigate();
  return <CatalogPage onOpenItem={(pk) => navigate(`/items/${pk}`)} />;
}

function ItemDetailRoute() {
  const { pk } = useParams();
  return <ItemDetailPage pk={pk!} />;
}

export function AppRoutes() {
  return (
    <Routes>
      <Route path="/" element={<CatalogRoute />} />
      <Route path="/items/:pk" element={<ItemDetailRoute />} />
    </Routes>
  );
}
```

- [ ] **Step 6: Rewrite `shell/src/App.tsx`**

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { useMemo } from "react";
import { loadConfig } from "./config";
import { AuthProvider } from "./auth/AuthProvider";
import { useAuth } from "./auth/useAuth";
import { RequireAuth } from "./auth/RequireAuth";
import { createItemClient } from "./api/itemClient";
import { ItemClientProvider } from "./api/ItemClientProvider";
import { AppLayout } from "./shell/AppLayout";
import { AppRoutes } from "./shell/routes";

const config = loadConfig(import.meta.env as unknown as Record<string, string | undefined>);
const queryClient = new QueryClient();

function AuthedApp() {
  const { getAccessToken } = useAuth();
  const client = useMemo(
    () =>
      createItemClient({
        geonodeUrl: config.geonodeUrl,
        builderUrl: config.builderUrl,
        getToken: getAccessToken,
      }),
    [getAccessToken],
  );
  return (
    <ItemClientProvider client={client}>
      <BrowserRouter>
        <AppLayout>
          <AppRoutes />
        </AppLayout>
      </BrowserRouter>
    </ItemClientProvider>
  );
}

export default function App() {
  return (
    <AuthProvider config={config}>
      <QueryClientProvider client={queryClient}>
        <RequireAuth>
          <AuthedApp />
        </RequireAuth>
      </QueryClientProvider>
    </AuthProvider>
  );
}
```

Note: `App.test.tsx` from Task 1 asserted a `GeoStudio` heading on the bare app; that assertion is now served by the `AppLayout` brand text, but the layout requires auth + router context. Update `shell/src/App.test.tsx` to render `AppLayout` directly instead (the bare-app smoke test is superseded):

```tsx
import { render, screen } from "@testing-library/react";
import { vi } from "vitest";
import type { AuthState } from "./auth/useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "alice",
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("./auth/useAuth", () => ({ useAuth: () => authState }));
const { AppLayout } = await import("./shell/AppLayout");

test("shell layout shows the GeoStudio brand", () => {
  render(
    <AppLayout>
      <div>x</div>
    </AppLayout>,
  );
  expect(screen.getByText("GeoStudio")).toBeInTheDocument();
});
```

Wrap the `AppLayout` render in a router in this test if `Link` requires it: import `MemoryRouter` from `react-router-dom` and wrap `<AppLayout>` with `<MemoryRouter>`.

- [ ] **Step 7: Update `shell/src/main.tsx`**

`main.tsx` already imports and renders `App`; no change needed beyond Task 1. Verify it still reads:

```tsx
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
```

- [ ] **Step 8: Run the full suite and build**

Run: `npm test` → expect all tests PASS. Then `npm run build` → success.

- [ ] **Step 9: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/src/shell shell/src/App.tsx shell/src/App.test.tsx
git commit -m "feat(shell): compose app shell with layout, router and providers"
```

---

### Task 10: Playwright E2E (mock auth)

**Files:**
- Create: `shell/playwright.config.ts`
- Create: `shell/.env.e2e`
- Create: `shell/e2e/catalog.spec.ts`
- Create: `shell/e2e/mocks.ts`
- Modify: `shell/package.json` (add `@playwright/test`, `e2e` script)
- Modify: `shell/src/auth/AuthProvider.tsx` (mock-mode authenticated `useAuth`)
- Modify: `shell/src/auth/useAuth.ts` (honor mock mode)

**Interfaces:**
- Consumes: the app served by `vite preview` with `VITE_AUTH_MODE=mock`.
- Produces: an E2E spec that loads the app (auto-authenticated via mock mode), sees catalog items (GeoNode requests fulfilled by Playwright route mocks), searches, opens an item, and sees the detail page.

- [ ] **Step 1: Make mock auth produce an authenticated state**

The `RequireAuth` guard and `AppLayout` call `useAuth()`. In mock mode there is no `react-oidc-context` provider, so `useOidcAuth()` would throw. Make `useAuth` branch on a module flag set by `AuthProvider` mock mode.

Replace `shell/src/auth/useAuth.ts` with:

```ts
import { useAuth as useOidcAuth } from "react-oidc-context";

export type AuthState = {
  isLoading: boolean;
  isAuthenticated: boolean;
  username: string | null;
  getAccessToken: () => string | undefined;
  signIn: () => void;
  signOut: () => void;
};

let mockMode = false;
export function enableMockAuth() {
  mockMode = true;
}

const MOCK_STATE: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "mockuser",
  getAccessToken: () => "mock-token",
  signIn: () => {},
  signOut: () => {},
};

export function useAuth(): AuthState {
  if (mockMode) return MOCK_STATE;
  // eslint-disable-next-line react-hooks/rules-of-hooks
  const oidc = useOidcAuth();
  return {
    isLoading: oidc.isLoading,
    isAuthenticated: oidc.isAuthenticated,
    username: (oidc.user?.profile.preferred_username as string) ?? null,
    getAccessToken: () => oidc.user?.access_token,
    signIn: () => void oidc.signinRedirect(),
    signOut: () => void oidc.signoutRedirect(),
  };
}
```

In `shell/src/auth/AuthProvider.tsx`, call `enableMockAuth()` when in mock mode. Change the mock branch to:

```tsx
  if (config.authMode === "mock") {
    enableMockAuth();
    return <MockAuthContext.Provider value={true}>{children}</MockAuthContext.Provider>;
  }
```

and add `import { enableMockAuth } from "./useAuth";` at the top.

- [ ] **Step 2: Verify existing unit tests still pass**

Run: `npm test -- src/auth/RequireAuth.test.tsx src/shell/AppLayout.test.tsx`
Expected: PASS (the unit tests mock `./useAuth` entirely, so `mockMode` is irrelevant there).

- [ ] **Step 3: Add Playwright and env**

Add `"@playwright/test": "^1.47.0"` to `devDependencies` and a script `"e2e": "playwright test"` to `shell/package.json`. Run `npm install` then `npx playwright install chromium`.

Create `shell/.env.e2e`:

```
VITE_AUTH_MODE=mock
VITE_GEONODE_URL=https://geonode.test
VITE_BUILDER_URL=https://builder.test
```

- [ ] **Step 4: Create `shell/playwright.config.ts`**

```ts
import { defineConfig } from "@playwright/test";

export default defineConfig({
  testDir: "./e2e",
  use: { baseURL: "http://localhost:4173" },
  webServer: {
    command: "npm run build && npm run preview -- --port 4173",
    url: "http://localhost:4173",
    reuseExistingServer: false,
    env: {
      VITE_AUTH_MODE: "mock",
      VITE_GEONODE_URL: "https://geonode.test",
      VITE_BUILDER_URL: "https://builder.test",
    },
  },
});
```

- [ ] **Step 5: Create `shell/e2e/mocks.ts`**

```ts
import type { Page } from "@playwright/test";

export async function mockGeoNode(page: Page) {
  await page.route("**/api/v2/resources*", async (route) => {
    await route.fulfill({
      json: {
        total: 2,
        page: 1,
        page_size: 12,
        resources: [
          { pk: "1", resource_type: "app", title: "Alpha", abstract: "A",
            owner: { username: "alice" }, thumbnail_url: null, date: "2026-01-01" },
          { pk: "2", resource_type: "dashboard", title: "Beta", abstract: "B",
            owner: { username: "alice" }, thumbnail_url: null, date: "2026-01-01" },
        ],
      },
    });
  });
  await page.route("**/api/v2/resources/1", async (route) => {
    await route.fulfill({
      json: {
        resource: { pk: "1", resource_type: "app", title: "Alpha", abstract: "A",
          owner: { username: "alice" }, thumbnail_url: null, date: "2026-01-01" },
      },
    });
  });
}
```

- [ ] **Step 6: Create `shell/e2e/catalog.spec.ts`**

```ts
import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("login (mock) → list → open item", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  await expect(page.getByText("GeoStudio")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();

  await page.getByRole("button", { name: /ouvrir/i }).first().click();
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  await expect(page.getByRole("button", { name: /éditeur/i })).toBeDisabled();
});
```

- [ ] **Step 7: Run the E2E**

Run (from `shell/`): `npm run e2e`
Expected: 1 test PASS. (If chromium is unavailable in the environment, report that the deterministic unit suite passes and the E2E could not run here.)

- [ ] **Step 8: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/playwright.config.ts shell/.env.e2e shell/e2e shell/src/auth/useAuth.ts shell/src/auth/AuthProvider.tsx
git commit -m "test(shell): add Playwright E2E with mock-auth catalog flow"
```

---

### Task 11: Containerization + compose integration

**Files:**
- Create: `shell/Dockerfile`
- Create: `shell/nginx.conf`
- Create: `shell/.dockerignore`
- Modify: `docker-compose.yml` (add `shell` service)
- Test: manual (commands below)

**Interfaces:**
- Consumes: the existing compose network `gis-net`.
- Produces: a `shell` container serving the built static SPA on port 8300 via nginx, with SPA history fallback.

- [ ] **Step 1: Create `shell/nginx.conf`**

```nginx
server {
  listen 8300;
  root /usr/share/nginx/html;
  index index.html;
  location / {
    try_files $uri $uri/ /index.html;
  }
}
```

- [ ] **Step 2: Create `shell/Dockerfile`**

```dockerfile
FROM node:20-slim AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Build-time public config; override at build with --build-arg as needed.
ARG VITE_GEONODE_URL=http://localhost:8080
ARG VITE_BUILDER_URL=http://localhost:8200
ARG VITE_OIDC_AUTHORITY=http://localhost:8180/realms/gis-platform
ARG VITE_OIDC_CLIENT_ID=shell
ARG VITE_OIDC_REDIRECT_URI=http://localhost:8300/
ENV VITE_GEONODE_URL=$VITE_GEONODE_URL \
    VITE_BUILDER_URL=$VITE_BUILDER_URL \
    VITE_OIDC_AUTHORITY=$VITE_OIDC_AUTHORITY \
    VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID \
    VITE_OIDC_REDIRECT_URI=$VITE_OIDC_REDIRECT_URI
RUN npm run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8300
```

- [ ] **Step 3: Create `shell/.dockerignore`**

```
node_modules/
dist/
coverage/
playwright-report/
test-results/
.env
```

- [ ] **Step 4: Add the compose service**

Add under `services:` in repo-root `docker-compose.yml` (match existing indentation):

```yaml
  shell:
    build: ./shell
    ports:
      - "8300:8300"
    networks: [gis-net]
    restart: unless-stopped
```

- [ ] **Step 5: Build and validate**

Run from repo root:
```bash
docker compose config >/dev/null && echo "compose OK"
docker compose build shell
docker compose up -d shell && sleep 3
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8300/
docker compose down
```
Expected: `compose OK`, build succeeds, HTTP `200`. (If the base images cannot be pulled in this environment, report that `docker compose config` passed and the build/run could not complete due to registry availability.)

- [ ] **Step 6: Commit**

```bash
git add shell/Dockerfile shell/nginx.conf shell/.dockerignore docker-compose.yml
git commit -m "feat(shell): add Dockerfile, nginx and docker-compose service"
```

---

## Self-Review

**Spec coverage (against SP-0b.1 phase scope — auth + shell + item-client read + catalog + open):**
- Vite/TS/Tailwind/shadcn foundation → Tasks 1, 6. ✅
- `config` via `VITE_*` → Task 2. ✅
- `item-client` façade (read + getMe), Bearer injection, GeoNode mapping → Task 3. ✅
- TanStack Query hooks + context → Task 4. ✅
- Auth (react-oidc-context, in-memory token store, RequireAuth, mock mode) → Tasks 5, 10. ✅
- App shell layout + routing + provider composition → Task 9. ✅
- Catalog: grid, search, filter, pagination, loading/error/empty → Task 7. ✅
- Open item → item detail page → Tasks 8, 9. ✅
- E2E login→list→open → Task 10. ✅
- Deployment integration (compose) → Task 11. ✅
- Out of phase (0b.2/0b.3): create/rename/delete/metadata/thumbnails/sharing/groups — correctly excluded.

**Constraint coverage:** no token in localStorage (Task 5 in-memory store; Task 10 mock token in memory) ✅; all network via item-client ✅; URLs from env (Task 2; Task 9 `App` loads config) ✅; clean MSW (`onUnhandledRequest: "error"`, Task 3) ✅.

**Placeholder scan:** every code step contains complete code; no TBD/TODO. ✅

**Type consistency:** `AppConfig` (Task 2) consumed by `AuthProvider`/`App` (Tasks 5, 9). `Item`/`ItemPage`/`Me`/`ItemClient`/`ListItemsParams` (Task 3) consumed identically by hooks (Task 4), `ItemCard` (Task 6), pages (Tasks 7, 8). `AuthState` (Task 5) consumed by `RequireAuth`, `AppLayout`, and tests (Tasks 5, 9). `createItemClient({ geonodeUrl, builderUrl, getToken })` signature identical across Tasks 3, 4, 7, 8, 9. ✅

## Notes for SP-0b.2 / SP-0b.3

- 0b.2 will add `createConfigItem`/`updateItem`/`deleteItem` to `ItemClient` (calling Builder Service `POST /configs` + GeoNode), plus mutation hooks with optimistic update/rollback, and the create/rename/delete/metadata UI.
- 0b.3 will add `setSharing`/`listGroups` and the ShareDialog.
- Keep `ItemClient` and the `Item` shape stable as the contract; extend, don't break.

---

## Deferred follow-ups (from final whole-branch review)

Non-blocking for SP-0b.1; triaged for later sub-projects / a hardening pass:

- **Deploy config (before any non-local deploy):** the compose `shell` service has no `build.args`, so the image bakes the Dockerfile's `http://localhost:*` VITE_* defaults — only usable for local/dev. Add `build.args` reading `${VITE_*}`. Also wire the `shell` service through the Traefik ingress (labels) like sibling services instead of publishing `8300:8300` directly.
- **Resilience:** add an ErrorBoundary; `loadConfig` runs at module top-level so a missing env var yields a blank screen — surface a friendly error.
- **nginx:** enable `gzip` for the static SPA.
- **Router:** pass `future={{ v7_startTransition, v7_relativeSplatPath }}` to silence React Router v6 deprecation warnings.
- **E2E:** assert `toHaveURL(/\/items\/1/)` after navigation; dedupe env between `playwright.config.ts` and `.env.e2e`.
- **Wiring:** `getMe`/`useMe` are implemented + tested but unused (AppLayout reads username from the OIDC profile) — consume in a later sub-project or drop.
- **Cosmetic:** `useMemo([getAccessToken])` rebuilds the client each render (harmless); unreachable `?? "map"` in `toItem`; unstable `signIn`/`signOut` refs; devDependencies ordering.
