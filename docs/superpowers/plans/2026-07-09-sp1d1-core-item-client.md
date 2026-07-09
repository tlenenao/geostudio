# SP-1d.1 — CoreItemClient & bascule des variables d'env Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the shell talk to the cœur exclusively — no more GeoNode calls anywhere in `ItemClient`. `VITE_CORE_URL` replaces `VITE_GEONODE_URL`+`VITE_BUILDER_URL`; `createItemClient` (same exported name, `ItemClient` interface unchanged) is rewritten to hit the cœur's typed endpoints (`/items`, `/items/{id}/sharing`, `/groups`, `/me`, `/configs*`) instead of GeoNode's REST API. This is the first of three independent SP-1d sub-plans — GeoNode/Superset/Redis removal from `docker-compose.yml` and the Keycloak realm/`oidc` wiring are separate plans; this one only changes shell code and the shell's own env-var contract.

**Architecture:** `itemClient.ts` keeps its single exported factory `createItemClient(opts): ItemClient` (only its `opts` shape and internal implementation change — `geonodeUrl`+`builderUrl` become one `coreUrl`). Six of its fourteen `ItemClient` methods (`createConfigItem`, `createMapItem`, `getMapConfig`, `saveMapConfig`, `getAppConfig`, `saveAppConfig`) already hit this exact same service today under the `builderUrl` name — those are a pure base-URL rename, no shape changes. Eight methods (`listItems`, `getItem`, `getMe`, `updateItem`, `uploadThumbnail`, `deleteItem`, `listGroups`, `getSharing`, `setSharing`) currently hit GeoNode's REST API and are rewritten against the generated `core-schema.d.ts` types, which turn out to be near-identical in shape to the shell's own `Item`/`UpdatePatch`/`Sharing`/`Group` types (the cœur's `owner` is already a flat string, `ItemUpdatePatch` is already camelCase, `Sharing`/`GroupShare` already match `{public, groups:[{groupId,role}]}` exactly) — so most of these become direct pass-throughs instead of GeoNode's snake_case/nested-object remapping. `listLayerSources`/`queryDataSource`/`featuresUrl` are untouched (Martin/pg_featureserv direct, orthogonal to this migration). A new shared `request<T>()` helper replaces ~10 near-identical inline `fetch()` blocks now that every call targets one host. A fourth task rewrites the Playwright e2e network mock (`mockGeoNode` → `mockCore`), since it intercepts GeoNode-shaped paths today and must intercept the cœur's paths instead.

**Tech Stack:** TypeScript, Vitest, MSW (`msw`) for HTTP mocking — matches the existing `itemClient.test.ts` convention exactly, no new dependency.

## Global Constraints

- `ItemClient` (`shell/src/api/types.ts`) does **not change** — same method signatures, same `Item`/`ListItemsParams`/`Sharing`/`Group`/`Me`/`UpdatePatch` types. This plan only replaces `createItemClient`'s internals and its `opts` parameter shape.
- "Coupure nette" (arbitrage already decided in the SP-1d spec, §2): GeoNode-calling code is *replaced*, not kept behind a flag. No `VITE_ITEM_BACKEND=geonode|core` toggle.
- `listItems`'s `scope=mine`/`scope=shared` no longer need client-side filtering by `params.me` — the cœur's `GET /items?scope=...` already does correct, paginated, server-side visibility filtering (SP-1c). `params.me` stays in the `ListItemsParams` type (interface unchanged) but `CoreItemClient` simply never reads it. Do not remove it from the type or from `CatalogPage.tsx`'s call site — that page-level cleanup is out of scope here (harmless unused param, not a correctness bug).
- `uploadThumbnail` switches from GeoNode's `PUT .../set_thumbnail` to the cœur's `POST /items/{id}/thumbnail` (the cœur has no PUT verb on that path — see `core-schema.d.ts`). This is a real verb change, not a rename.
- `createConfigItem`/`createMapItem`: the cœur's `POST /configs` (`CreateConfigRequest{title, config}`) has **no `owner` field** — the cœur derives ownership from the authenticated user server-side (SP-1b). Stop sending `owner` in the request body. The `ItemClient.createConfigItem`/`createMapItem` interface still takes `owner: string` as an input param (unchanged interface) — keep accepting it and echo it back into the constructed `Item` return value exactly as today (the caller already passes the current user's own username here, so this remains accurate without a network round-trip).
- Auth: reuse `useAuth().getAccessToken()` unconditionally as `Authorization: Bearer <token>` on every cœur request, mock or oidc — this already works today (`mock-token` in mock mode, a real JWT in oidc mode) and needs no special-casing.
- Test convention: MSW (`msw`), not manual `fetch` mocking — mirrors the existing `shell/src/test/msw/handlers.ts` + `server.use()` override pattern used by `itemClient.test.ts` and ~14 other test files that share the same global default handlers.
- No existing `StubItemClient`/shared fake — every other test file either calls the real `createItemClient(...)` against MSW, or passes an inline `Partial<ItemClient>` literal. Neither pattern needs touching by this plan; only `handlers.ts`'s *default* GeoNode-shaped handlers need replacing with cœur-shaped ones, since those are shared globally.
- Interfaces this plan consumes (already merged, on `dev`): the cœur's OpenAPI-generated `shell/src/api/generated/core-schema.d.ts` — paths `/items`, `/items/{item_id}`, `/items/{item_id}/thumbnail`, `/items/{item_id}/sharing`, `/groups`, `/me`, `/configs`, `/configs/by-item/{item_id}`; schemas `ItemRead{pk,resourceType,title,abstract,owner,thumbnailUrl,date,configId,isPublished}`, `ItemPage{items,total,page,pageSize}`, `ItemUpdatePatch{title?,abstract?,keywords?,isPublished?}`, `Sharing{public,groups:GroupShare[]}`, `GroupShare{groupId,role:"viewer"|"editor"}`, `GroupRead{id,name}`, `MeResponse{id,username,firstName,lastName,email,tenantId}`, `ConfigRead{id,itemId,kind,version,config}`.

---

### Task 1: `VITE_CORE_URL` replaces `VITE_GEONODE_URL`/`VITE_BUILDER_URL`

**Files:**
- Modify: `shell/src/config.ts`
- Modify: `shell/src/config.test.ts`
- Modify: `shell/.env.e2e`
- Modify: `shell/playwright.config.ts`
- Modify: `shell/Dockerfile`

**Interfaces:**
- Consumes: nothing new.
- Produces: `AppConfig.coreUrl: string` (replaces `geonodeUrl`/`builderUrl`), env var `VITE_CORE_URL` (replaces `VITE_GEONODE_URL`+`VITE_BUILDER_URL`, required in every auth mode, same as its predecessors).

- [ ] **Step 1: Write the failing tests**

Rewrite `shell/src/config.test.ts`:
```ts
import { loadConfig } from "./config";

const base = {
  VITE_CORE_URL: "https://core.test",
  VITE_OIDC_AUTHORITY: "https://kc.test/realms/gis",
  VITE_OIDC_CLIENT_ID: "shell",
  VITE_OIDC_REDIRECT_URI: "https://app.test/callback",
};

test("loads a full oidc config", () => {
  const cfg = loadConfig(base);
  expect(cfg.coreUrl).toBe("https://core.test");
  expect(cfg.authMode).toBe("oidc");
  expect(cfg.oidcClientId).toBe("shell");
});

test("throws listing all missing required vars in oidc mode", () => {
  expect(() => loadConfig({})).toThrow(/VITE_CORE_URL/);
  expect(() => loadConfig({})).toThrow(/VITE_OIDC_AUTHORITY/);
});

test("mock mode does not require oidc vars", () => {
  const cfg = loadConfig({
    VITE_CORE_URL: "https://core.test",
    VITE_AUTH_MODE: "mock",
  });
  expect(cfg.authMode).toBe("mock");
  expect(cfg.oidcAuthority).toBe("");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npm test -- config.test.ts`
Expected: FAIL — `cfg.coreUrl` is `undefined` (property doesn't exist yet), `VITE_CORE_URL` isn't in the required-vars list yet.

- [ ] **Step 3: Rewrite `config.ts`**

```ts
export type AppConfig = {
  coreUrl: string;
  martinUrl: string;
  featureservUrl: string;
  oidcAuthority: string;
  oidcClientId: string;
  oidcRedirectUri: string;
  authMode: "oidc" | "mock";
};

export function loadConfig(env: Record<string, string | undefined>): AppConfig {
  const authMode = env.VITE_AUTH_MODE === "mock" ? "mock" : "oidc";

  const required: Record<string, string | undefined> = {
    VITE_CORE_URL: env.VITE_CORE_URL,
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
    coreUrl: env.VITE_CORE_URL!,
    martinUrl: env.VITE_MARTIN_URL ?? "",
    featureservUrl: env.VITE_FEATURESERV_URL ?? "",
    oidcAuthority: env.VITE_OIDC_AUTHORITY ?? "",
    oidcClientId: env.VITE_OIDC_CLIENT_ID ?? "",
    oidcRedirectUri: env.VITE_OIDC_REDIRECT_URI ?? "",
    authMode,
  };
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npm test -- config.test.ts`
Expected: PASS.

- [ ] **Step 5: Update `.env.e2e` and `playwright.config.ts`**

`shell/.env.e2e`:
```
VITE_AUTH_MODE=mock
VITE_CORE_URL=https://core.test
VITE_MARTIN_URL=https://martin.test
VITE_FEATURESERV_URL=https://featureserv.test
```

In `shell/playwright.config.ts`, change the `webServer.env` block:
```ts
    env: {
      VITE_AUTH_MODE: "mock",
      VITE_CORE_URL: "https://core.test",
      VITE_MARTIN_URL: "https://martin.test",
      VITE_FEATURESERV_URL: "https://featureserv.test",
    },
```

- [ ] **Step 6: Update the Docker build args**

`shell/Dockerfile` currently has build-time `ARG`/`ENV` pairs for `VITE_GEONODE_URL`/`VITE_BUILDER_URL` (defaults `http://localhost:8080`/`http://localhost:8200`) — these are how Vite env vars get baked into the production build (Vite embeds `import.meta.env.VITE_*` at build time, not runtime, unlike the dev server). Change:
```dockerfile
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
```
to:
```dockerfile
ARG VITE_CORE_URL=http://localhost:8200
ARG VITE_OIDC_AUTHORITY=http://localhost:8180/realms/gis-platform
ARG VITE_OIDC_CLIENT_ID=shell
ARG VITE_OIDC_REDIRECT_URI=http://localhost:8300/
ENV VITE_CORE_URL=$VITE_CORE_URL \
    VITE_OIDC_AUTHORITY=$VITE_OIDC_AUTHORITY \
    VITE_OIDC_CLIENT_ID=$VITE_OIDC_CLIENT_ID \
    VITE_OIDC_REDIRECT_URI=$VITE_OIDC_REDIRECT_URI
```
(Leave the stale `gis-platform` realm name in the `VITE_OIDC_AUTHORITY` default as-is here — the Keycloak/oidc sub-plan owns fixing it to `geostudio`, since that's a realm-naming concern, not an env-var-contract concern.)

- [ ] **Step 7: Commit**

```bash
git add shell/src/config.ts shell/src/config.test.ts shell/.env.e2e shell/playwright.config.ts shell/Dockerfile
git commit -m "feat(shell): VITE_CORE_URL replaces VITE_GEONODE_URL/VITE_BUILDER_URL"
```

---

### Task 2: Rewrite `createItemClient` against the cœur, and its test suite's default MSW handlers

**Files:**
- Modify: `shell/src/test/msw/handlers.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: `shell/src/api/generated/core-schema.d.ts`'s `ItemRead`/`ItemPage`/`ItemUpdatePatch`/`Sharing`/`GroupShare`/`GroupRead`/`MeResponse`/`ConfigRead` shapes (read-only reference, not imported as runtime types — this file already builds its own request/response shapes by hand, matching the existing convention of not importing `components["schemas"][...]` directly).
- Produces: `createItemClient(opts: {coreUrl: string; martinUrl?: string; featureservUrl?: string; getToken: () => string | undefined}): ItemClient` — same exported name, new `opts` shape (no more `geonodeUrl`/`builderUrl`).

- [ ] **Step 1: Write the failing default MSW handlers for a `core.test` host**

Rewrite `shell/src/test/msw/handlers.ts` in full:
```ts
import { http, HttpResponse } from "msw";

const CORE = "https://core.test";

function item(pk: string, type = "app", title = `Item ${pk}`) {
  return {
    pk,
    resourceType: type,
    title,
    abstract: `Abstract ${pk}`,
    owner: "alice",
    thumbnailUrl: `${CORE}/items/${pk}/thumbnail`,
    date: "2026-01-01T00:00:00Z",
    configId: null,
    isPublished: false,
  };
}

export const handlers = [
  http.get(`${CORE}/items`, () => HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 })),
  http.get(`${CORE}/items/:pk`, ({ params }) => {
    if (params.pk === "404") return new HttpResponse(null, { status: 404 });
    return HttpResponse.json(item(String(params.pk)));
  }),
  http.get(`${CORE}/me`, () =>
    HttpResponse.json({
      id: "u1", username: "alice", firstName: "Alice", lastName: "Martin",
      email: "alice@example.com", tenantId: "t1",
    }),
  ),
  http.post(`${CORE}/configs`, async ({ request }) => {
    const body = (await request.json()) as { title: string; config: { kind: string } };
    return HttpResponse.json(
      { id: "cfg-1", itemId: "99", kind: body.config.kind, version: 1, config: body.config },
      { status: 201 },
    );
  }),
  http.patch(`${CORE}/items/:pk`, async ({ params, request }) => {
    const patch = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({ ...item(String(params.pk)), ...patch });
  }),
  http.post(`${CORE}/items/:pk/thumbnail`, () => new HttpResponse(null, { status: 204 })),
  http.delete(`${CORE}/configs/by-item/:pk`, () => new HttpResponse(null, { status: 204 })),
  http.get(`${CORE}/groups`, () =>
    HttpResponse.json([
      { id: "10", name: "Équipe A" },
      { id: "11", name: "Équipe B" },
    ]),
  ),
  http.get(`${CORE}/items/:pk/sharing`, () =>
    HttpResponse.json({ public: true, groups: [{ groupId: "10", role: "editor" }] }),
  ),
  http.put(`${CORE}/items/:pk/sharing`, () => new HttpResponse(null, { status: 204 })),
];
```

- [ ] **Step 2: Run the existing test suite to see it fail broadly**

Run: `cd shell && npm test -- itemClient.test.ts`
Expected: FAIL — every test still references `geonodeUrl`/`builderUrl` and the old GeoNode-shaped assertions; this confirms the handlers change alone doesn't fix anything yet (the client implementation is next).

- [ ] **Step 3: Rewrite `itemClient.ts`**

Replace the file's `toItem`/`GeoNodeResource` type and the `createItemClient` function (keep `toFrontLayer`/`RawMapLayer`/`buildFeaturesUrl`/`STAT_KEYS`/`StatMeasure`/`reduceValues`/`measureLabel`/`aggregateRecords` exactly as they are — those are Martin/pg_featureserv concerns, untouched by this plan):

```ts
export function createItemClient(opts: {
  coreUrl: string;
  martinUrl?: string;
  featureservUrl?: string;
  getToken: () => string | undefined;
}): ItemClient {
  const { coreUrl, martinUrl, featureservUrl, getToken } = opts;

  async function request<T>(method: string, path: string, body?: unknown): Promise<T> {
    const token = getToken();
    const headers: Record<string, string> = {};
    if (token) headers.Authorization = `Bearer ${token}`;
    if (body !== undefined) headers["Content-Type"] = "application/json";
    const res = await fetch(`${coreUrl}${path}`, {
      method,
      headers,
      body: body !== undefined ? JSON.stringify(body) : undefined,
    });
    if (!res.ok) {
      throw new Error(`Request failed: ${res.status} ${method} ${path}`);
    }
    if (res.status === 204) return undefined as T;
    return (await res.json()) as T;
  }

  async function fetchMartinSources(): Promise<LayerSource[]> {
    if (!martinUrl) return [];
    const res = await fetch(`${martinUrl}/catalog`);
    if (!res.ok) throw new Error(`Request failed: ${res.status} /catalog`);
    const data = (await res.json()) as {
      tiles?: Record<string, { description?: string }>;
    };
    return Object.entries(data.tiles ?? {}).map(([id, meta]) => ({
      id,
      title: meta.description ?? id,
      service: "martin" as const,
      kind: "vector" as const,
      tilesUrl: `${martinUrl}/${id}/{z}/{x}/{y}`,
      sourceLayer: id,
    }));
  }

  async function fetchFeatureservSources(): Promise<LayerSource[]> {
    if (!featureservUrl) return [];
    const res = await fetch(`${featureservUrl}/collections.json`);
    if (!res.ok) throw new Error(`Request failed: ${res.status} /collections.json`);
    const data = (await res.json()) as {
      collections?: { id: string; title?: string }[];
    };
    return (data.collections ?? []).map((c) => ({
      id: c.id,
      title: c.title ?? c.id,
      service: "featureserv" as const,
      kind: "feature" as const,
      url: `${featureservUrl}/collections/${c.id}/items.json`,
    }));
  }

  return {
    async listItems(params: ListItemsParams = {}): Promise<ItemPage> {
      const q = new URLSearchParams();
      if (params.q) q.set("q", params.q);
      if (params.type) q.set("type", params.type);
      if (params.scope) q.set("scope", params.scope);
      q.set("page", String(params.page ?? 1));
      q.set("pageSize", String(params.pageSize ?? 12));
      return request<ItemPage>("GET", `/items?${q.toString()}`);
    },

    async getItem(pk: string): Promise<Item> {
      return request<Item>("GET", `/items/${pk}`);
    },

    async getMe(): Promise<Me> {
      const data = await request<{ username: string; firstName: string; lastName: string }>("GET", `/me`);
      return { username: data.username, firstName: data.firstName, lastName: data.lastName };
    },

    async createConfigItem(input: { kind: CreateKind; title: string; owner: string; templateId?: string }): Promise<Item> {
      const template = input.templateId ? getTemplate(input.templateId) : undefined;
      const config = {
        version: 1,
        kind: input.kind,
        theme: template?.theme ?? {},
        dataSources: [],
        layout: template?.layout ?? { type: "grid", breakpoints: {}, items: [] },
        messages: [],
      };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, { title: input.title, config },
      );
      if (!data.itemId) {
        throw new Error("createConfigItem: core returned no itemId");
      }
      return {
        pk: String(data.itemId),
        resourceType: data.kind as ResourceType,
        title: input.title,
        abstract: "",
        owner: input.owner,
        thumbnailUrl: null,
        date: "",
        configId: String(data.id),
        isPublished: false,
      };
    },

    async updateItem(pk: string, patch: UpdatePatch): Promise<Item> {
      return request<Item>("PATCH", `/items/${pk}`, patch);
    },

    async uploadThumbnail(pk: string, file: File): Promise<void> {
      const token = getToken();
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${coreUrl}/items/${pk}/thumbnail`, {
        method: "POST",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status} POST thumbnail`);
      }
    },

    async deleteItem(pk: string): Promise<void> {
      const token = getToken();
      const res = await fetch(`${coreUrl}/configs/by-item/${pk}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok && res.status !== 404) {
        throw new Error(`Request failed: ${res.status} DELETE /configs/by-item/${pk}`);
      }
    },

    async listGroups(): Promise<Group[]> {
      const data = await request<{ id: string; name: string }[]>("GET", `/groups`);
      return data.map((g) => ({ id: g.id, title: g.name }));
    },

    async getSharing(pk: string): Promise<Sharing> {
      return request<Sharing>("GET", `/items/${pk}/sharing`);
    },

    async setSharing(pk: string, sharing: Sharing): Promise<void> {
      await request<void>("PUT", `/items/${pk}/sharing`, sharing);
    },

    async listLayerSources(): Promise<LayerSource[]> {
      const results = await Promise.allSettled([
        fetchMartinSources(),
        fetchFeatureservSources(),
      ]);
      const fulfilled = results.filter(
        (r): r is PromiseFulfilledResult<LayerSource[]> => r.status === "fulfilled",
      );
      if (fulfilled.length === 0) {
        throw new Error("listLayerSources: all layer services failed");
      }
      return fulfilled.flatMap((r) => r.value);
    },

    async createMapItem(input: { title: string; owner: string }): Promise<Item> {
      const map: MapConfig = {
        basemap: { style: DEFAULT_BASEMAP.style },
        view: { center: [2.4, 46.6], zoom: 5 },
        layers: [],
      };
      const config = { version: 1, kind: "map", map };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createMapItem: core returned no itemId");
      return {
        pk: String(data.itemId), resourceType: "map", title: input.title, abstract: "",
        owner: input.owner, thumbnailUrl: null, date: "", configId: String(data.id),
        isPublished: false,
      };
    },

    async getMapConfig(pk: string): Promise<MapConfig> {
      // ConfigRead nests the builder config under "config"; the map is config.map.
      const data = await request<{
        config?: { map?: { basemap: { style: string }; view: { center: [number, number]; zoom: number }; layers: RawMapLayer[] } | null };
      }>("GET", `/configs/by-item/${pk}`);
      const map = data.config?.map;
      if (!map) throw new Error("getMapConfig: config has no map payload");
      return {
        basemap: map.basemap,
        view: map.view,
        layers: (map.layers ?? []).map(toFrontLayer),
      };
    },

    async saveMapConfig(pk: string, config: MapConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, { version: 1, kind: "map", map: config });
    },

    async getAppConfig(pk: string): Promise<AppConfig> {
      const data = await request<{
        config?: {
          kind?: "app" | "dashboard";
          theme?: Theme;
          dataSources?: DataSource[];
          messages?: ActionMessage[];
          pages?: Page[];
          variables?: Variable[];
          layout?: AppConfig["layout"] | null;
        };
      }>("GET", `/configs/by-item/${pk}`);
      const c = data.config;
      if (!c?.layout) throw new Error("getAppConfig: config has no layout");
      return {
        kind: c.kind ?? "app",
        theme: c.theme ?? {},
        dataSources: c.dataSources ?? [],
        messages: c.messages ?? [],
        pages: c.pages,
        variables: c.variables,
        layout: c.layout,
      };
    },

    async saveAppConfig(pk: string, config: AppConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, {
        version: 1,
        kind: config.kind,
        theme: config.theme,
        dataSources: config.dataSources,
        messages: config.messages,
        pages: config.pages,
        variables: config.variables,
        layout: config.layout,
      });
    },

    featuresUrl(source: DataSource): string {
      return buildFeaturesUrl(featureservUrl, source);
    },

    async queryDataSource(source: DataSource): Promise<DataRecord[]> {
      if (source.type === "static") {
        return (source.query.records as DataRecord[] | undefined) ?? [];
      }
      const token = getToken();
      const res = await fetch(buildFeaturesUrl(featureservUrl, source), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} features ${source.layer}`);
      const data = (await res.json()) as {
        features?: { id?: string | number; properties?: Record<string, unknown>; geometry?: unknown }[];
      };
      const records = (data.features ?? []).map((f, i) => ({
        id: f.id ?? i,
        properties: f.properties ?? {},
        geometry: f.geometry,
      }));
      return source.type === "statistics" ? aggregateRecords(records, source.query) : records;
    },
  };
}
```

Remove the now-unused `GeoNodeResource` type and `toItem` function entirely (no longer referenced — `ItemRead` from the cœur already matches `Item` field-for-field).

- [ ] **Step 4: Rewrite `itemClient.test.ts`**

Replace the file's `makeClient` helper and every GeoNode-oriented test with cœur-oriented equivalents. Full replacement of the items/sharing/groups/me test section (keep the `listLayerSources`/`queryDataSource`/`featuresUrl` tests — Martin/pg_featureserv, untouched by this plan — as they are, just update `makeClient`'s call signature):

```ts
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "./itemClient";

function makeClient(token: string | undefined = "test-token") {
  return createItemClient({
    coreUrl: "https://core.test",
    martinUrl: "https://martin.test",
    featureservUrl: "https://featureserv.test",
    getToken: () => token,
  });
}

test("listItems sends the bearer token and scope", async () => {
  let auth: string | null = null;
  let url: string | null = null;
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      auth = request.headers.get("authorization");
      url = request.url;
      return HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 });
    }),
  );
  await makeClient("abc").listItems({ scope: "shared" });
  expect(auth).toBe("Bearer abc");
  expect(url).toContain("scope=shared");
});

test("getItem returns the item as-is (core owner is already a flat string)", async () => {
  const item = await makeClient().getItem("7");
  expect(item.pk).toBe("7");
  expect(item.owner).toBe("alice");
});

test("getItem missing returns 404 and throws", async () => {
  await expect(makeClient().getItem("404")).rejects.toThrow(/404/);
});

test("getMe maps camelCase fields, dropping id/email/tenantId", async () => {
  const me = await makeClient().getMe();
  expect(me).toEqual({ username: "alice", firstName: "Alice", lastName: "Martin" });
});

test("createConfigItem does not send owner in the request body", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", itemId: "99", kind: "app", version: 1, config: {} }, { status: 201 });
    }),
  );
  const item = await makeClient().createConfigItem({ kind: "app", title: "My App", owner: "alice" });
  expect(body).not.toHaveProperty("owner");
  expect(item.owner).toBe("alice");
  expect(item.pk).toBe("99");
});

test("updateItem sends the patch camelCase, unchanged", async () => {
  let body: unknown;
  server.use(
    http.patch("https://core.test/items/:pk", async ({ params, request }) => {
      body = await request.json();
      return HttpResponse.json({
        pk: String(params.pk), resourceType: "app", title: "Renamed", abstract: "", owner: "alice",
        thumbnailUrl: null, date: "", configId: null, isPublished: true,
      });
    }),
  );
  const item = await makeClient().updateItem("7", { title: "Renamed", isPublished: true });
  expect(body).toEqual({ title: "Renamed", isPublished: true });
  expect(item.title).toBe("Renamed");
});

test("uploadThumbnail POSTs multipart form data", async () => {
  let method: string | null = null;
  server.use(
    http.post("https://core.test/items/:pk/thumbnail", ({ request }) => {
      method = request.method;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient().uploadThumbnail("7", new File(["x"], "thumb.png", { type: "image/png" }));
  expect(method).toBe("POST");
});

test("deleteItem tolerates a 404 as success", async () => {
  server.use(http.delete("https://core.test/configs/by-item/:pk", () => new HttpResponse(null, { status: 404 })));
  await expect(makeClient().deleteItem("nope")).resolves.toBeUndefined();
});

test("listGroups maps name to title", async () => {
  const groups = await makeClient().listGroups();
  expect(groups).toEqual([{ id: "10", title: "Équipe A" }, { id: "11", title: "Équipe B" }]);
});

test("getSharing passes through the core's Sharing shape directly", async () => {
  const sharing = await makeClient().getSharing("7");
  expect(sharing).toEqual({ public: true, groups: [{ groupId: "10", role: "editor" }] });
});

test("setSharing PUTs the sharing object as-is", async () => {
  let body: unknown;
  server.use(
    http.put("https://core.test/items/:pk/sharing", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient().setSharing("7", { public: false, groups: [{ groupId: "10", role: "viewer" }] });
  expect(body).toEqual({ public: false, groups: [{ groupId: "10", role: "viewer" }] });
});
```

Keep the file's existing `listLayerSources`/`queryDataSource`/`featuresUrl` tests below this, updating only their `makeClient()` calls (if any pass `geonodeUrl`/`builderUrl`) to the new `coreUrl` shape.

- [ ] **Step 5: Run the full itemClient test file**

Run: `cd shell && npm test -- itemClient.test.ts`
Expected: PASS — all rewritten tests green.

- [ ] **Step 6: Run the full shell test suite**

Run: `cd shell && npm test`
Expected: PASS. This is the critical check — `handlers.ts`'s default handlers are shared globally by ~14 other test files (hooks tests, page tests, widget tests). If any of them assumed a GeoNode-shaped default response (e.g. checked for `owner.username` nesting, or `group_profiles`), they will fail here and need their local assertions updated to match the new cœur-shaped defaults — fix each failure by adjusting that test's expectations to the new (simpler, flatter) shapes, not by reverting `handlers.ts`.

- [ ] **Step 7: Commit**

```bash
git add shell/src/test/msw/handlers.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): CoreItemClient — itemClient.ts talks to the cœur, not GeoNode"
```

(If Step 6 required fixes in other test files, include those files in this commit too — they're part of making this task's change land green.)

---

### Task 3: Wire `App.tsx` to the new config/client shape

**Files:**
- Modify: `shell/src/App.tsx`

**Interfaces:**
- Consumes: `config.coreUrl` (Task 1), `createItemClient({coreUrl, martinUrl, featureservUrl, getToken})` (Task 2).
- Produces: the running app now calls the cœur exclusively for every `ItemClient` operation.

- [ ] **Step 1: Update `App.tsx`'s `createItemClient` call**

In `shell/src/App.tsx`, change:
```tsx
      createItemClient({
        geonodeUrl: config.geonodeUrl,
        builderUrl: config.builderUrl,
        martinUrl: config.martinUrl,
        featureservUrl: config.featureservUrl,
        getToken: getAccessToken,
      }),
```
to:
```tsx
      createItemClient({
        coreUrl: config.coreUrl,
        martinUrl: config.martinUrl,
        featureservUrl: config.featureservUrl,
        getToken: getAccessToken,
      }),
```

- [ ] **Step 2: Type-check and build**

Run: `cd shell && npm run build`
Expected: PASS (`tsc --noEmit` + `vite build`) — no remaining references to `geonodeUrl`/`builderUrl` anywhere (a leftover reference would be a compile error, since `AppConfig`'s shape changed in Task 1).

- [ ] **Step 3: Run the full shell test suite once more**

Run: `cd shell && npm test`
Expected: PASS (156+ files, same count as before this plan — no test added or removed, only rewired).

- [ ] **Step 4: Grep for any remaining GeoNode/builder references in shell app code (not e2e — that's Task 4)**

Run: `cd shell && grep -rn "VITE_GEONODE_URL\|VITE_BUILDER_URL\|geonodeUrl\|builderUrl" src/ *.config.ts 2>/dev/null`
Expected: no output (empty).

- [ ] **Step 5: Commit**

```bash
git add shell/src/App.tsx
git commit -m "feat(shell): wire App.tsx to CoreItemClient"
```

---

### Task 4: Rewrite the e2e network mock (`mockGeoNode` → `mockCore`) and verify all 13 Playwright specs

**Files:**
- Modify: `shell/e2e/mocks.ts`
- Modify: `shell/e2e/actions.spec.ts`, `shell/e2e/widget-sdk.spec.ts`, `shell/e2e/templates.spec.ts`, `shell/e2e/theme.spec.ts`, `shell/e2e/responsive.spec.ts`, `shell/e2e/variables.spec.ts`, `shell/e2e/data-widget.spec.ts`, `shell/e2e/app-builder.spec.ts`, `shell/e2e/map-editor.spec.ts`, `shell/e2e/pages-navigation.spec.ts`, `shell/e2e/publication.spec.ts`, `shell/e2e/chart.spec.ts`, `shell/e2e/catalog.spec.ts` (all 13 — each only needs its `import`/call-site renamed, no other change)

**Interfaces:**
- Consumes: nothing new.
- Produces: `mockCore(page: Page): Promise<void>` (renamed from `mockGeoNode`), intercepting the cœur's paths (`/items*`, `/items/{id}`, `/me`, `/configs`, `/configs/by-item/**`) instead of GeoNode's (`/api/v2/resources*`, `/api/v2/users/me`). The Martin/pg_featureserv routes (`/catalog`, `/collections.json`, `/collections/villes/items.json`, `/collections/parcs/items.json`) are untouched — they never talked to GeoNode or the cœur.

`shell/e2e/mocks.ts` uses Playwright's `page.route()` with glob path patterns (`**/items*`, matched against the URL path regardless of host) — this is why most of the file needs no change at all: `/configs` and `/configs/by-item/**` already match the cœur's real paths verbatim (the "builder" backend these routes model was always the cœur under a different env-var name), and the Martin/featureserv routes are orthogonal. Only the GeoNode-specific routes (`/api/v2/resources*`, `/api/v2/users/me`) need rewriting to the cœur's actual paths and response shapes.

- [ ] **Step 1: Read the current file's route table**

Read `shell/e2e/mocks.ts` in full (already quoted in this plan's research — 183 lines) before editing, to confirm nothing drifted since this plan was written.

- [ ] **Step 2: Rewrite the `ALL` fixture and the GeoNode-specific routes**

In `shell/e2e/mocks.ts`, change the `ALL` fixture to the cœur's flat `ItemRead` shape:
```ts
const ALL = [
  { pk: "1", resourceType: "app", title: "Alpha", abstract: "A", owner: "alice", thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: false },
  { pk: "2", resourceType: "dashboard", title: "Beta", abstract: "B", owner: "alice", thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: false },
];
```

Rename the exported function `mockGeoNode` → `mockCore` (keep everything else in the function body as-is except the routes below).

Replace the `**/api/v2/resources*` route:
```ts
  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    const scope = url.searchParams.get("scope");
    const visible = ALL.filter((r) => !deleted.has(r.pk));
    // Fixture reality: every item in ALL is owned by "alice"; the mock auth
    // user is "mockuser" (see useAuth.ts's MOCK_STATE) — so scope=mine is
    // always empty for this fixture, matching the pre-migration mock's
    // behavior for the "mockuser" case.
    const items = scope === "mine" ? [] : visible;
    await route.fulfill({ json: { items, total: items.length, page: 1, pageSize: 12 } });
  });
```

Replace the `**/api/v2/users/me` route:
```ts
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: { id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User", email: null, tenantId: "t-mock" },
    });
  });
```

Replace the `**/api/v2/resources/1` route:
```ts
  await page.route("**/items/1", async (route) => {
    await route.fulfill({ json: ALL[0] });
  });
```

Replace the `**/api/v2/resources/9` route:
```ts
  await page.route("**/items/9", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = await route.request().postDataJSON();
      if (typeof body.isPublished === "boolean") published = body.isPublished;
    }
    await route.fulfill({
      json: {
        pk: "9", resourceType: "app", title: "Créée", abstract: "", owner: "mockuser",
        thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: published,
      },
    });
  });
```

Leave the `**/configs` POST route, the `**/configs/by-item/**` route, and the Martin/`**/catalog`/`**/collections.json`/`**/collections/villes/items.json`/`**/collections/parcs/items.json` routes completely unchanged — they already model the cœur's real paths/shapes.

- [ ] **Step 3: Rename the import and call site in all 13 spec files**

For each of the 13 files listed above, change:
```ts
import { mockGeoNode } from "./mocks";
```
to:
```ts
import { mockCore } from "./mocks";
```
and every call site:
```ts
await mockGeoNode(page);
```
to:
```ts
await mockCore(page);
```

This is a pure rename — no other line in any of these 13 files changes.

- [ ] **Step 4: Run the full e2e suite**

Run: `cd shell && npm run e2e`
Expected: PASS — all 13 specs green. Playwright's `webServer` builds and previews the shell with `VITE_CORE_URL=https://core.test` (set in Task 1); since every network call is intercepted by `mockCore`'s `page.route()` handlers (Playwright-level interception, not a real HTTP call), the shell never actually needs `https://core.test` to be a reachable host — this mirrors exactly how `mockGeoNode` worked before this plan (the old `https://geonode.test`/`https://builder.test` hosts were never real either).

If any spec fails, check first whether it's exercising a scope/path this task's route rewrite didn't anticipate (e.g. a spec using `scope=shared` or `scope=public` explicitly) — read that spec's exact expectation and adjust the `**/items*` route handler's scope logic accordingly, rather than special-casing outside `mocks.ts`.

- [ ] **Step 5: Grep for any remaining GeoNode reference anywhere in the shell**

Run: `cd shell && grep -rln "GeoNode\|geonode" e2e/ src/ 2>/dev/null`
Expected: no output. This closes the SP-1d spec's acceptance criterion "aucune référence à ... GeoNode ne subsiste" for everything under `shell/` (the cœur-side `core/app/geonode.py` and the compose/README references are the separate GeoNode-removal sub-plan's job).

- [ ] **Step 6: Commit**

```bash
git add shell/e2e/mocks.ts shell/e2e/*.spec.ts
git commit -m "test(e2e): rewrite mockGeoNode as mockCore against the cœur's paths"
```
