# GeoStudio SP-0d.5b — Pages, navigation et routage par page Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to invoke this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a builder app have multiple pages — a `PageManager` adds/renames/removes/reorders pages, a **Navigation** widget renders a clickable menu of them, and the runtime deep-links each page at `/apps/:pk/:pageId`, all through the one existing `AppRenderer` engine.

**Architecture:** `AppConfig.pages?: Page[]` is additive; when absent, the existing top-level `layout` IS the sole implicit page (`"page-1"`). A pure module `pages.ts` (`getPages`/`getPageLayout`/`setPageLayout`) is the single place that resolves "what does page X look like" and "write a new layout for page X", keeping the top-level `layout` mirroring `pages[0]` (the field the backend still requires for `app`/`dashboard`). `AppRenderer` gains an optional `pageId`/`onNavigate` pair — controlled by the editor's page selector or the runtime route, uncontrolled (internal state) otherwise — and threads the resolved `pages` list plus a `navigate` callback into every widget's `WidgetContext` (the `navigate` field already exists there, unused, from an earlier phase). The Navigation widget is the first consumer: it lists `ctx.pages` and calls `ctx.navigate(pageId)` on click. `AppRuntimePage` turns that callback into a real route push (`/apps/:pk/:pageId`); the editor turns it into local state, so pages behave identically in edit/preview/runtime — the same single-engine guarantee every other 0d.5 slice relies on.

**Tech Stack:** React 19 + TS + Vite 6 + Vitest 3 + Testing Library + Playwright; react-router-dom ^6.26 (optional path segments, supported since v6.5). FastAPI + Pydantic (builder-service). No new dependency.

## Global Constraints

- Additive/back-compatible: `AppConfig.pages?: Page[]` is optional (mirrors the `WidgetItem.layouts?` precedent from SP-0d.5a) — a config that never touches `pages` keeps working exactly as before, both statically (no existing `AppConfig` test literal needs a new field) and at runtime (`getPages` synthesizes a single implicit page named `"Page 1"` with the fixed id `"page-1"` from the existing `layout`).
- The top-level `layout` field always mirrors `pages[0].layout` once `pages` is populated — this is what lets the backend keep requiring `layout` for `app`/`dashboard` configs (`builder-service/app/schemas.py`'s `_require_kind_payload` validator) with **no change** to that validator.
- One rendering engine: `AppRenderer` resolves and renders the active page identically in `edit`/`preview`/`runtime`; navigation always flows through the same `pageId`/`onNavigate` pair, whether the caller is the editor's page selector or the runtime route.
- Front: no new service URL, no new dependency; pure logic lives in small `builder/*.ts` modules (mirrors `grid.ts`, `theme.ts`); panel components own their own add/remove/rename/reorder logic directly (mirrors `DataSourcePanel.tsx`, `PageManager` follows the same shape).
- Commits end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on branch `dev`. Run front-end commands from `shell/` (`cd shell && ...`), backend commands from `builder-service/`.

**Scope note:** A generic ActionBus `page.navigate` action (wiring an *arbitrary* emitter such as a Bouton to "go to page X") is **not** built here — every existing emitter's payload (Button's `{widgetId}`, List's clicked record, Filtre's `{field:value}`) has no natural `pageId`, and inventing a per-widget "target page" configuration field is a separate, unscoped feature. The Navigation widget covers the primary use case directly via `ctx.navigate`, which is the mechanism this plan delivers end-to-end.

---

### Task 1: Backend — `Page`/`pages[]` round-trip

**Files:**
- Modify: `builder-service/app/schemas.py`
- Test: `builder-service/tests/test_schemas.py`

**Interfaces:**
- Produces: `class Page(BaseModel): id: str; name: str; layout: Layout`; `BuilderConfig.pages: list[Page] = Field(default_factory=list)` — additive, defaults to an empty list, no change to `_require_kind_payload` (the top-level `layout` stays required for `app`/`dashboard` exactly as today).

- [ ] **Step 1: Write the failing tests**

Append to `builder-service/tests/test_schemas.py`:

```python
def test_pages_round_trip():
    payload = _valid_payload("app")
    payload["pages"] = [
        {"id": "p1", "name": "Accueil", "layout": payload["layout"]},
        {"id": "p2", "name": "Détails", "layout": {"type": "grid", "breakpoints": {}, "items": []}},
    ]
    config = BuilderConfig.model_validate(payload)
    assert len(config.pages) == 2
    assert config.pages[0].name == "Accueil"
    dumped = config.model_dump(by_alias=True)
    assert dumped["pages"][1]["name"] == "Détails"


def test_pages_optional_defaults_empty():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.pages == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd builder-service && python -m pytest tests/test_schemas.py -q`
Expected: FAIL — `pages` is stripped (unknown field) / `AttributeError`.

- [ ] **Step 3: Add the `Page` model + `BuilderConfig.pages`**

Edit `builder-service/app/schemas.py`. Add a `Page` class right after `class Layout(BaseModel): ...` (before `class Message(BaseModel): ...`):

```python
class Page(BaseModel):
    id: str
    name: str
    layout: Layout
```

In `class BuilderConfig(BaseModel):`, add the field after `messages`:

```python
    messages: list[Message] = Field(default_factory=list)
    pages: list[Page] = Field(default_factory=list)
    map: MapConfig | None = None
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd builder-service && python -m pytest tests/test_schemas.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite, then commit**

Run: `cd builder-service && python -m pytest -q`
Expected: all pass.

```bash
git add builder-service/app/schemas.py builder-service/tests/test_schemas.py
git commit -m "feat(builder-service): persist app pages (additive, round-trips)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Front types + item-client passthrough + pure `pages.ts` helpers

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts` (extend)
- Create: `shell/src/builder/pages.ts`
- Test: `shell/src/builder/pages.test.ts`

**Interfaces:**
- Produces:
  - `Page = { id: string; name: string; layout: AppLayout }`
  - `AppConfig.pages?: Page[]` (new, optional)
  - `getPages(config: AppConfig): Page[]` — returns `config.pages` when non-empty, else a single implicit page `[{ id: "page-1", name: "Page 1", layout: config.layout }]`.
  - `getPageLayout(config: AppConfig, pageId: string): AppLayout` — resolves the matching page's layout, falling back to `config.layout` if `pageId` matches nothing.
  - `setPageLayout(config: AppConfig, pageId: string, layout: AppLayout): AppConfig` — writes the new layout for `pageId`; on an implicit-page config (no explicit `pages` yet) only `layout` changes; on an explicit-pages config, the matching page's `layout` is replaced and the top-level `layout` is re-synced to `pages[0].layout`.

- [ ] **Step 1: Add the `Page` type and widen `AppConfig`**

Edit `shell/src/api/types.ts`. Add near `AppLayout`:

```ts
export type Page = {
  id: string;
  name: string;
  layout: AppLayout;
};
```

Add `pages?: Page[];` to `AppConfig`, after `layout: AppLayout;`:

```ts
export type AppConfig = {
  kind: "app" | "dashboard";
  theme: Theme;
  dataSources: DataSource[];
  messages: ActionMessage[];
  layout: AppLayout;
  pages?: Page[];
};
```

- [ ] **Step 2: Write the failing item-client tests**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("getAppConfig passes through the pages array when present", async () => {
  server.use(
    http.get("https://builder.test/configs/by-item/5", () =>
      HttpResponse.json({
        id: "cfg-5", itemId: "5", kind: "app",
        config: {
          kind: "app", theme: {}, dataSources: [], messages: [],
          layout: { type: "grid", breakpoints: {}, items: [] },
          pages: [
            { id: "p1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [] } },
          ],
        },
      }),
    ),
  );
  const cfg = await makeClient().getAppConfig("5");
  expect(cfg.pages).toEqual([
    { id: "p1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [] } },
  ]);
});

test("saveAppConfig PUTs the pages array when present", async () => {
  let body: any;
  server.use(
    http.put("https://builder.test/configs/by-item/5", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-5", itemId: "5", kind: "app", config: body });
    }),
  );
  await makeClient().saveAppConfig("5", {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] },
    pages: [{ id: "p1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [] } }],
  });
  expect(body.pages).toHaveLength(1);
  expect(body.pages[0].name).toBe("Accueil");
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `pages` is dropped by both `getAppConfig` and `saveAppConfig`.

- [ ] **Step 4: Thread `pages` through `getAppConfig`/`saveAppConfig`**

Edit `shell/src/api/itemClient.ts`. Add `Page` to the type import from `./types`. In `getAppConfig`, add `pages?: Page[];` to the local raw-response shape (after `messages?: ActionMessage[];`), and add `pages: c.pages,` to the returned object (after `messages: c.messages ?? [],`):

```ts
      const data = (await res.json()) as {
        config?: {
          kind?: "app" | "dashboard";
          theme?: Theme;
          dataSources?: DataSource[];
          messages?: ActionMessage[];
          pages?: Page[];
          layout?: AppConfig["layout"] | null;
        };
      };
      const c = data.config;
      if (!c?.layout) throw new Error("getAppConfig: config has no layout");
      return {
        kind: c.kind ?? "app",
        theme: c.theme ?? {},
        dataSources: c.dataSources ?? [],
        messages: c.messages ?? [],
        pages: c.pages,
        layout: c.layout,
      };
```

In `saveAppConfig`, add `pages: config.pages,` to the PUT body (after `messages: config.messages,`):

```ts
        body: JSON.stringify({
          version: 1,
          kind: config.kind,
          theme: config.theme,
          dataSources: config.dataSources,
          messages: config.messages,
          pages: config.pages,
          layout: config.layout,
        }),
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (existing `getAppConfig`/`saveAppConfig` tests, which never set `pages`, still pass — `config.pages` is `undefined`, `JSON.stringify` drops the key, the backend's `Field(default_factory=list)` fills `[]`).

- [ ] **Step 6: Write the failing `pages.ts` tests**

Create `shell/src/builder/pages.test.ts`:

```ts
import { expect, test } from "vitest";
import { getPages, getPageLayout, setPageLayout } from "./pages";
import type { AppConfig, AppLayout } from "../api/types";

const layout: AppLayout = { type: "grid", breakpoints: {}, items: [{ id: "a1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: {} }] };
const baseConfig: AppConfig = { kind: "app", theme: {}, dataSources: [], messages: [], layout };

test("getPages returns a single implicit page when config.pages is absent", () => {
  expect(getPages(baseConfig)).toEqual([{ id: "page-1", name: "Page 1", layout }]);
});

test("getPages returns the explicit pages array when present", () => {
  const pages = [{ id: "p1", name: "Accueil", layout }, { id: "p2", name: "Détails", layout }];
  expect(getPages({ ...baseConfig, pages })).toBe(pages);
});

test("getPageLayout resolves the matching page's layout", () => {
  const otherLayout: AppLayout = { type: "grid", breakpoints: {}, items: [] };
  const pages = [{ id: "p1", name: "Accueil", layout }, { id: "p2", name: "Détails", layout: otherLayout }];
  expect(getPageLayout({ ...baseConfig, pages }, "p2")).toBe(otherLayout);
});

test("getPageLayout falls back to the base layout for an unknown pageId", () => {
  expect(getPageLayout(baseConfig, "nope")).toBe(layout);
});

test("setPageLayout on an implicit-page config only updates the top-level layout", () => {
  const newLayout: AppLayout = { type: "grid", breakpoints: {}, items: [] };
  const next = setPageLayout(baseConfig, "page-1", newLayout);
  expect(next.layout).toBe(newLayout);
  expect(next.pages).toBeUndefined();
});

test("setPageLayout on an explicit-pages config updates only the matching page and mirrors pages[0] into layout", () => {
  const otherLayout: AppLayout = { type: "grid", breakpoints: {}, items: [] };
  const pages = [{ id: "p1", name: "Accueil", layout }, { id: "p2", name: "Détails", layout: otherLayout }];
  const cfg = { ...baseConfig, pages };
  const newLayout: AppLayout = { type: "grid", breakpoints: {}, items: [{ id: "z", widget: "text", x: 1, y: 1, w: 1, h: 1, props: {} }] };
  const next = setPageLayout(cfg, "p2", newLayout);
  expect(next.pages![1].layout).toBe(newLayout);
  expect(next.pages![0].layout).toBe(layout); // untouched
  expect(next.layout).toBe(layout); // mirrors pages[0], unchanged since p1 wasn't edited
});
```

- [ ] **Step 7: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/pages.test.ts`
Expected: FAIL — module `./pages` does not exist.

- [ ] **Step 8: Implement `pages.ts`**

Create `shell/src/builder/pages.ts`:

```ts
import type { AppConfig, AppLayout, Page } from "../api/types";

const IMPLICIT_PAGE_ID = "page-1";

// A config always has at least one page. If `config.pages` is absent/empty,
// the top-level `layout` IS that single implicit page.
export function getPages(config: AppConfig): Page[] {
  if (config.pages && config.pages.length > 0) return config.pages;
  return [{ id: IMPLICIT_PAGE_ID, name: "Page 1", layout: config.layout }];
}

export function getPageLayout(config: AppConfig, pageId: string): AppLayout {
  return getPages(config).find((p) => p.id === pageId)?.layout ?? config.layout;
}

// Writes a new layout for one page. If the config has no explicit `pages` yet,
// the result stays a legacy single-page config (only `layout` changes) — an
// explicit `pages` array only appears once a second page is added (PageManager).
// Once `pages` exists, its first entry always mirrors the top-level `layout`
// (the field the backend still requires for app/dashboard configs).
export function setPageLayout(config: AppConfig, pageId: string, layout: AppLayout): AppConfig {
  if (!config.pages || config.pages.length === 0) {
    return { ...config, layout };
  }
  const pages = config.pages.map((p) => (p.id === pageId ? { ...p, layout } : p));
  return { ...config, pages, layout: pages[0].layout };
}
```

- [ ] **Step 9: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/pages.test.ts`
Expected: PASS (6/6).

- [ ] **Step 10: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/builder/pages.ts shell/src/builder/pages.test.ts
git commit -m "feat(shell): Page type + pages.ts pure helpers (getPages/getPageLayout/setPageLayout)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `AppRenderer` becomes page-aware; threads `pages`/`navigate` into widget context

**Files:**
- Modify: `shell/src/builder/AppRenderer.tsx`
- Modify: `shell/src/builder/WidgetHost.tsx`
- Modify: `shell/src/builder/registry.ts`
- Test: `shell/src/builder/AppRenderer.test.tsx` (extend)

**Interfaces:**
- Consumes: `getPages`, `getPageLayout`, `setPageLayout` (Task 2).
- Produces:
  - `AppRenderer` gains optional props `pageId?: string` and `onNavigate?: (pageId: string) => void`. Renders the active page's items (`getPageLayout(config, activePageId).items`); edits (`handleMove`) write through `setPageLayout`. When `pageId` is uncontrolled, an internal state defaults to the first page and is updated by a `page.navigate`-style call from a widget.
  - `WidgetContext` gains `pages?: Page[]` (import `Page` from `../api/types`); the already-existing `navigate?: (pageId: string) => void` field is now actually populated.
  - `WidgetHost` gains optional props `pages?: Page[]` (default `[]`) and `navigate?: (pageId: string) => void`, both forwarded into `ctx`.

- [ ] **Step 1: Widen `WidgetContext`**

Edit `shell/src/builder/registry.ts`. Add `Page` to the type import from `../api/types`, and add a field to `WidgetContext` (it already declares `navigate?`):

```ts
export type WidgetContext = {
  mode: RenderMode;
  navigate?: (pageId: string) => void;
  pages?: Page[];
  data?: DataSourceState;
  bus?: ActionBus;
  widgetId?: string;
};
```

- [ ] **Step 2: Thread `pages`/`navigate` through `WidgetHost`**

Edit `shell/src/builder/WidgetHost.tsx`. Add `Page` to the type import from `../api/types`, and widen the component signature:

```ts
import type { Page, RenderMode, WidgetItem } from "../api/types";
```

```tsx
export function WidgetHost({
  item,
  mode,
  pages = [],
  navigate,
}: {
  item: WidgetItem;
  mode: RenderMode;
  pages?: Page[];
  navigate?: (pageId: string) => void;
}) {
  const states = useDataStates();
  const bus = useActionBus();
  const dsId = item.props.dataSourceId as string | undefined;
  const data = dsId ? states[dsId] : undefined;
  const def = getWidget(item.widget);
  if (!def) {
    return <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-slate-400">Widget inconnu : {item.widget}</div>;
  }
  const Widget = def.Component;
  return (
    <WidgetErrorBoundary>
      <Widget props={item.props} ctx={{ mode, data, bus: bus ?? undefined, widgetId: item.id, pages, navigate }} />
    </WidgetErrorBoundary>
  );
}
```

- [ ] **Step 3: Write the failing `AppRenderer` tests**

Append to `shell/src/builder/AppRenderer.test.tsx` (already imports `registerWidget`? No — add it to the `./registry` import; the file already imports `render`, `screen`, `userEvent`, `AppConfig`, `Wrapper`, `vi`):

```tsx
import { _resetRegistry, registerWidget } from "./registry";

test("renders only the active page's items when pages exist", () => {
  const cfg: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "a1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: { text: "Accueil" } },
    ] },
    pages: [
      { id: "p1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [
        { id: "a1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: { text: "Accueil" } },
      ] } },
      { id: "p2", name: "Détails", layout: { type: "grid", breakpoints: {}, items: [
        { id: "b1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: { text: "Détails" } },
      ] } },
    ],
  };
  render(<AppRenderer config={cfg} mode="runtime" pageId="p2" />, { wrapper: Wrapper });
  expect(screen.getByText("Détails")).toBeInTheDocument();
  expect(screen.queryByText("Accueil")).toBeNull();
});

test("edits write to the active page's layout, mirroring pages[0] into the top-level layout", async () => {
  let latest: AppConfig | null = null;
  const cfg: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "a1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
    ] },
    pages: [
      { id: "p1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [
        { id: "a1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
      ] } },
    ],
  };
  render(
    <AppRenderer config={cfg} mode="edit" pageId="p1" selectedId="a1" onSelect={() => {}} onChange={(c) => { latest = c; }} />,
    { wrapper: Wrapper },
  );
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-a1 à droite" }));
  expect(latest!.pages![0].layout.items[0].x).toBe(1);
  expect(latest!.layout.items[0].x).toBe(1); // mirrored
});

test("threads the resolved pages and a navigate callback into widget context", async () => {
  _resetRegistry();
  registerWidget({
    type: "nav-probe",
    label: "Probe",
    defaultProps: {},
    defaultSize: { w: 2, h: 1 },
    PropsPanel: () => null,
    Component: ({ ctx }) => (
      <div>
        <p>pages:{(ctx.pages ?? []).map((p) => p.name).join(",")}</p>
        <button onClick={() => ctx.navigate?.("p2")}>go</button>
      </div>
    ),
  });
  const cfg: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "n1", widget: "nav-probe", x: 0, y: 0, w: 2, h: 1, props: {} },
    ] },
    pages: [
      { id: "p1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [
        { id: "n1", widget: "nav-probe", x: 0, y: 0, w: 2, h: 1, props: {} },
      ] } },
      { id: "p2", name: "Détails", layout: { type: "grid", breakpoints: {}, items: [] } },
    ],
  };
  const onNavigate = vi.fn();
  render(<AppRenderer config={cfg} mode="runtime" pageId="p1" onNavigate={onNavigate} />, { wrapper: Wrapper });
  expect(screen.getByText("pages:Accueil,Détails")).toBeInTheDocument();
  await userEvent.click(screen.getByText("go"));
  expect(onNavigate).toHaveBeenCalledWith("p2");
});
```

- [ ] **Step 4: Run to verify they fail**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: FAIL — `AppRenderer` ignores `pages`/`pageId`/`onNavigate`; `ctx.pages`/`ctx.navigate` are never populated.

- [ ] **Step 5: Make `AppRenderer` page-aware**

Replace `shell/src/builder/AppRenderer.tsx` with:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import type { AppConfig, RenderMode } from "../api/types";
import { GridCanvas } from "./GridCanvas";
import { WidgetHost } from "./WidgetHost";
import { moveItemAt, breakpointForWidth, type Breakpoint } from "./grid";
import { getPages, getPageLayout, setPageLayout } from "./pages";
import { DataProvider } from "./DataContext";
import { ActionBus } from "./ActionBus";
import { ActionBusProvider } from "./ActionBusContext";
import { themeToCssVars } from "./theme";

export function AppRenderer({
  config,
  mode,
  onChange,
  selectedId = null,
  onSelect,
  breakpoint,
  pageId,
  onNavigate,
}: {
  config: AppConfig;
  mode: RenderMode;
  onChange?: (config: AppConfig) => void;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  breakpoint?: Breakpoint;
  pageId?: string;
  onNavigate?: (pageId: string) => void;
}) {
  const editable = mode === "edit";
  const bus = useMemo(() => new ActionBus(), []);
  useEffect(() => {
    bus.configure(config.messages);
  }, [bus, config.messages]);

  // When no breakpoint is controlled (runtime/preview without a switcher),
  // auto-detect from the container width. jsdom has no ResizeObserver → keep lg.
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoBp, setAutoBp] = useState<Breakpoint>("lg");
  useEffect(() => {
    if (breakpoint) return;
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const update = () => setAutoBp(breakpointForWidth(el.clientWidth));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [breakpoint]);
  const bp = breakpoint ?? autoBp;

  // When no pageId is controlled, fall back to internal state defaulting to
  // the first page. A widget-triggered navigation (e.g. the Navigation widget)
  // calls handleNavigate, which either bubbles to the controlling parent
  // (editor page selector, runtime route) or updates this local fallback.
  const pages = getPages(config);
  const [internalPageId, setInternalPageId] = useState<string | null>(null);
  const activePageId = pageId ?? internalPageId ?? pages[0].id;
  const activeLayout = getPageLayout(config, activePageId);

  function handleNavigate(nextPageId: string) {
    if (onNavigate) onNavigate(nextPageId);
    else setInternalPageId(nextPageId);
  }

  function handleMove(id: string, dx: number, dy: number) {
    if (!onChange) return;
    const items = activeLayout.items.map((it) => (it.id === id ? moveItemAt(it, bp, dx, dy) : it));
    onChange(setPageLayout(config, activePageId, { ...activeLayout, items }));
  }

  return (
    <div ref={containerRef} className="h-full w-full" style={themeToCssVars(config.theme)}>
      <ActionBusProvider bus={bus}>
        <DataProvider sources={config.dataSources}>
          <GridCanvas
            items={activeLayout.items}
            breakpoint={bp}
            editable={editable}
            selectedId={selectedId}
            onSelect={(id) => onSelect?.(id)}
            onMoveItem={handleMove}
            renderItem={(item) => <WidgetHost item={item} mode={mode} pages={pages} navigate={handleNavigate} />}
          />
        </DataProvider>
      </ActionBusProvider>
    </div>
  );
}
```

- [ ] **Step 6: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds. (Existing tests pass no `pages`/`pageId` — `getPages` synthesizes the implicit `"page-1"` page from `config.layout`, so `activeLayout.items === config.layout.items` and `handleMove`'s `setPageLayout` on an implicit-page config only rewrites `layout`, exactly matching the pre-existing behavior.)

```bash
git add shell/src/builder/AppRenderer.tsx shell/src/builder/AppRenderer.test.tsx shell/src/builder/WidgetHost.tsx shell/src/builder/registry.ts
git commit -m "feat(shell): AppRenderer resolves the active page and threads pages/navigate into widget context

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `PageManager` + `AppBuilderPage` integration

**Files:**
- Create: `shell/src/builder/PageManager.tsx`
- Test: `shell/src/builder/PageManager.test.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Test: `shell/src/pages/AppBuilderPage.test.tsx` (extend)

**Interfaces:**
- Consumes: `getPages`, `getPageLayout`, `setPageLayout` (Task 2); `AppRenderer`'s `pageId`/`onNavigate` props (Task 3).
- Produces:
  - `PageManager({ pages: Page[], activePageId: string, onChange: (pages: Page[]) => void, onSelectPage: (pageId: string) => void })` — add (always keeps ≥1 page), rename, remove, reorder (move up/down). All controls are `id`-keyed (`aria-label={`... la page ${p.id}`}`), never `name`-keyed, so a rename mid-test doesn't shift any other control's accessible name.
  - `AppBuilderPage` tracks `activePageId` state, renders `PageManager` in the left rail, and rewires `addWidget`/`updateSelectedProps`/`selected`/`ActionsPanel`'s `items` to operate on the active page's layout via `pages.ts`; passes `pageId`/`onNavigate` to `AppRenderer`.

- [ ] **Step 1: Write the failing `PageManager` tests**

Create `shell/src/builder/PageManager.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { Page } from "../api/types";
import { PageManager } from "./PageManager";

const emptyLayout = { type: "grid" as const, breakpoints: {}, items: [] };

test("adds a page and selects it", async () => {
  const onChange = vi.fn();
  const onSelectPage = vi.fn();
  const pages: Page[] = [{ id: "p1", name: "Page 1", layout: emptyLayout }];
  render(<PageManager pages={pages} activePageId="p1" onChange={onChange} onSelectPage={onSelectPage} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une page" }));
  const next = onChange.mock.calls[0][0] as Page[];
  expect(next).toHaveLength(2);
  expect(onSelectPage).toHaveBeenCalledWith(next[1].id);
});

test("removes a page and falls back to the first remaining page if it was active", async () => {
  const onChange = vi.fn();
  const onSelectPage = vi.fn();
  const pages: Page[] = [
    { id: "p1", name: "Accueil", layout: emptyLayout },
    { id: "p2", name: "Détails", layout: emptyLayout },
  ];
  render(<PageManager pages={pages} activePageId="p2" onChange={onChange} onSelectPage={onSelectPage} />);
  await userEvent.click(screen.getByRole("button", { name: "Retirer la page p2" }));
  expect(onChange).toHaveBeenCalledWith([pages[0]]);
  expect(onSelectPage).toHaveBeenCalledWith("p1");
});

test("cannot remove the last remaining page", () => {
  const pages: Page[] = [{ id: "p1", name: "Accueil", layout: emptyLayout }];
  render(<PageManager pages={pages} activePageId="p1" onChange={vi.fn()} onSelectPage={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Retirer la page p1" })).toBeDisabled();
});

test("renames a page", async () => {
  const onChange = vi.fn();
  const pages: Page[] = [{ id: "p1", name: "", layout: emptyLayout }];
  render(<PageManager pages={pages} activePageId="p1" onChange={onChange} onSelectPage={vi.fn()} />);
  await userEvent.type(screen.getByLabelText("Renommer la page p1"), "A");
  const next = onChange.mock.calls.at(-1)![0] as Page[];
  expect(next[0].name).toBe("A");
});

test("reorders pages with the move buttons", async () => {
  const onChange = vi.fn();
  const pages: Page[] = [
    { id: "p1", name: "A", layout: emptyLayout },
    { id: "p2", name: "B", layout: emptyLayout },
  ];
  render(<PageManager pages={pages} activePageId="p1" onChange={onChange} onSelectPage={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Descendre la page p1" }));
  const next = onChange.mock.calls[0][0] as Page[];
  expect(next.map((p) => p.id)).toEqual(["p2", "p1"]);
});

test("selecting a page calls onSelectPage", async () => {
  const onSelectPage = vi.fn();
  const pages: Page[] = [{ id: "p1", name: "Accueil", layout: emptyLayout }];
  render(<PageManager pages={pages} activePageId="p1" onChange={vi.fn()} onSelectPage={onSelectPage} />);
  await userEvent.click(screen.getByRole("button", { name: "Ouvrir la page p1" }));
  expect(onSelectPage).toHaveBeenCalledWith("p1");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/PageManager.test.tsx`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `PageManager`**

Create `shell/src/builder/PageManager.tsx`:

```tsx
import type { Page } from "../api/types";

export function PageManager({
  pages,
  activePageId,
  onChange,
  onSelectPage,
}: {
  pages: Page[];
  activePageId: string;
  onChange: (pages: Page[]) => void;
  onSelectPage: (pageId: string) => void;
}) {
  function addPage() {
    const newPage: Page = {
      id: crypto.randomUUID(),
      name: `Page ${pages.length + 1}`,
      layout: { type: "grid", breakpoints: {}, items: [] },
    };
    onChange([...pages, newPage]);
    onSelectPage(newPage.id);
  }
  function remove(id: string) {
    if (pages.length <= 1) return;
    const next = pages.filter((p) => p.id !== id);
    onChange(next);
    if (activePageId === id) onSelectPage(next[0].id);
  }
  function rename(id: string, name: string) {
    onChange(pages.map((p) => (p.id === id ? { ...p, name } : p)));
  }
  function move(id: string, dir: -1 | 1) {
    const i = pages.findIndex((p) => p.id === id);
    const j = i + dir;
    if (j < 0 || j >= pages.length) return;
    const next = [...pages];
    [next[i], next[j]] = [next[j], next[i]];
    onChange(next);
  }
  return (
    <ul className="flex flex-col gap-1">
      {pages.map((p, i) => (
        <li
          key={p.id}
          className={`flex items-center gap-1 rounded border p-1 text-xs ${p.id === activePageId ? "border-blue-500" : "border-slate-200"}`}
        >
          <button type="button" aria-label={`Ouvrir la page ${p.id}`} className="flex-1 truncate text-left" onClick={() => onSelectPage(p.id)}>
            {p.name}
          </button>
          <input
            aria-label={`Renommer la page ${p.id}`}
            className="w-16 rounded border border-slate-300 px-1"
            value={p.name}
            onChange={(e) => rename(p.id, e.target.value)}
          />
          <button type="button" aria-label={`Monter la page ${p.id}`} disabled={i === 0} className="disabled:opacity-30" onClick={() => move(p.id, -1)}>↑</button>
          <button type="button" aria-label={`Descendre la page ${p.id}`} disabled={i === pages.length - 1} className="disabled:opacity-30" onClick={() => move(p.id, 1)}>↓</button>
          <button type="button" aria-label={`Retirer la page ${p.id}`} disabled={pages.length <= 1} className="text-red-600 disabled:opacity-30" onClick={() => remove(p.id)}>✕</button>
        </li>
      ))}
      <li>
        <button type="button" className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-100" onClick={addPage}>
          Ajouter une page
        </button>
      </li>
    </ul>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/PageManager.test.tsx`
Expected: PASS (6/6).

- [ ] **Step 5: Rewire `AppBuilderPage` to the active page**

Replace `shell/src/pages/AppBuilderPage.tsx` with:

```tsx
import { useEffect, useMemo, useState } from "react";
import { useAppConfig, useSaveApp } from "../api/hooks";
import type { AppConfig, RenderMode, WidgetItem } from "../api/types";
import { ActionsPanel } from "../builder/ActionsPanel";
import { AppRenderer } from "../builder/AppRenderer";
import { DataSourcePanel } from "../builder/DataSourcePanel";
import { PageManager } from "../builder/PageManager";
import { WidgetPalette } from "../builder/WidgetPalette";
import { PropsPanel } from "../builder/PropsPanel";
import { registerBuiltinWidgets } from "../builder/widgets";
import { getWidget } from "../builder/registry";
import { BREAKPOINTS, type Breakpoint } from "../builder/grid";
import { getPages, getPageLayout, setPageLayout } from "../builder/pages";
import { Button } from "../ui/button";

registerBuiltinWidgets();

export function AppBuilderPage({ pk }: { pk: string }) {
  const query = useAppConfig(pk);
  const save = useSaveApp(pk);
  const [draft, setDraft] = useState<AppConfig | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<RenderMode>("edit");
  const [breakpoint, setBreakpoint] = useState<Breakpoint>("lg");
  const [activePageId, setActivePageId] = useState<string | null>(null);

  useEffect(() => {
    // Seed the draft once on first load. Re-seeding on every query.data change
    // (e.g. the refetch after a save) would clobber in-flight local edits.
    if (query.data) setDraft((d) => d ?? query.data);
  }, [query.data]);

  const pages = useMemo(() => (draft ? getPages(draft) : []), [draft]);
  const activePage = activePageId ?? pages[0]?.id ?? null;
  const activeLayout = useMemo(
    () => (draft && activePage ? getPageLayout(draft, activePage) : null),
    [draft, activePage],
  );

  const selected = useMemo(
    () => activeLayout?.items.find((i) => i.id === selectedId) ?? null,
    [activeLayout, selectedId],
  );

  if (query.isLoading || (!draft && !query.isError)) return <p role="status">Chargement…</p>;
  if (query.isError || !draft || !activeLayout || !activePage)
    return <p role="alert" className="text-sm text-red-600">Application introuvable.</p>;

  function addWidget(type: string) {
    const def = getWidget(type);
    if (!def || !draft || !activeLayout || !activePage) return;
    const item: WidgetItem = {
      id: crypto.randomUUID(),
      widget: type,
      x: 0,
      y: 0,
      w: def.defaultSize.w,
      h: def.defaultSize.h,
      props: { ...def.defaultProps },
    };
    setDraft(setPageLayout(draft, activePage, { ...activeLayout, items: [...activeLayout.items, item] }));
    setSelectedId(item.id);
  }

  function updateSelectedProps(props: Record<string, unknown>) {
    if (!draft || !selectedId || !activeLayout || !activePage) return;
    setDraft(setPageLayout(draft, activePage, {
      ...activeLayout,
      items: activeLayout.items.map((i) => (i.id === selectedId ? { ...i, props } : i)),
    }));
  }

  const setSources = (dataSources: typeof draft.dataSources) =>
    setDraft((d) => (d ? { ...d, dataSources } : d));

  const setMessages = (messages: typeof draft.messages) =>
    setDraft((d) => (d ? { ...d, messages } : d));

  const setPages = (nextPages: typeof pages) =>
    setDraft((d) => (d ? { ...d, pages: nextPages, layout: nextPages[0]?.layout ?? d.layout } : d));

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b p-2">
        <Button size="sm" variant={mode === "edit" ? "default" : "outline"} onClick={() => setMode("edit")}>Édition</Button>
        <Button size="sm" variant={mode === "preview" ? "default" : "outline"} onClick={() => setMode("preview")}>Aperçu</Button>
        <div className="ml-2 flex items-center gap-1">
          {BREAKPOINTS.map((bp) => (
            <Button
              key={bp}
              size="sm"
              variant={breakpoint === bp ? "default" : "outline"}
              aria-label={`Éditer en ${bp}`}
              onClick={() => setBreakpoint(bp)}
            >
              {bp}
            </Button>
          ))}
        </div>
        <div className="flex-1" />
        <Button size="sm" disabled={save.isPending} onClick={() => save.mutate(draft)}>Enregistrer</Button>
        {save.isError && <span role="alert" className="text-sm text-red-600">Échec de l'enregistrement.</span>}
      </div>
      <div className="flex flex-1 overflow-hidden">
        {mode === "edit" && (
          <aside className="w-48 overflow-auto border-r p-2">
            <p className="mb-1 text-xs font-medium text-slate-500">Widgets</p>
            <WidgetPalette onAdd={addWidget} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Pages</p>
            <PageManager pages={pages} activePageId={activePage} onChange={setPages} onSelectPage={setActivePageId} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Sources de données</p>
            <DataSourcePanel sources={draft.dataSources} onChange={setSources} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Actions</p>
            <ActionsPanel items={activeLayout.items} messages={draft.messages} onChange={setMessages} />
          </aside>
        )}
        <main className="flex-1 overflow-auto p-2">
          <AppRenderer
            config={draft}
            mode={mode}
            onChange={setDraft}
            selectedId={selectedId}
            onSelect={setSelectedId}
            breakpoint={breakpoint}
            pageId={activePage}
            onNavigate={setActivePageId}
          />
        </main>
        {mode === "edit" && (
          <aside className="w-64 overflow-auto border-l p-2">
            <p className="mb-1 text-xs font-medium text-slate-500">Propriétés</p>
            <PropsPanel item={selected} dataSources={draft.dataSources} onChange={updateSelectedProps} />
          </aside>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 6: Extend the `AppBuilderPage` test**

Append to `shell/src/pages/AppBuilderPage.test.tsx` (reuses the existing `renderPage`, `config`, `userEvent`, `waitFor`, `screen`):

```tsx
test("adds a second page and can switch back to editing the first", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await screen.findByRole("button", { name: "Ajouter une page" });
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une page" }));
  await userEvent.click(screen.getByRole("button", { name: "Ouvrir la page page-1" }));
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.pages).toHaveLength(2);
  expect(saved.pages![0].id).toBe("page-1");
  expect(saved.pages![0].layout.items).toHaveLength(1); // Texte landed on page 1
  expect(saved.pages![1].layout.items).toHaveLength(0); // page 2 untouched
});
```

- [ ] **Step 7: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/PageManager.test.tsx src/pages/AppBuilderPage.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds. (Existing `AppBuilderPage` tests never touch `PageManager` — `pages` resolves to the single implicit `"page-1"` page, `activeLayout` is `draft.layout`, so `addWidget`/`updateSelectedProps`/`ActionsPanel` behave exactly as before.)

```bash
git add shell/src/builder/PageManager.tsx shell/src/builder/PageManager.test.tsx shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
git commit -m "feat(shell): add PageManager and rewire the app builder to the active page

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Runtime route `/apps/:pk/:pageId?` + `AppRuntimePage` navigation

**Files:**
- Modify: `shell/src/shell/routes.tsx`
- Modify: `shell/src/pages/AppRuntimePage.tsx`
- Test: `shell/src/shell/routes.test.tsx` (extend)

**Interfaces:**
- Consumes: `AppRenderer`'s `pageId`/`onNavigate` props (Task 3).
- Produces: `AppRuntimePage({ pk: string, pageId?: string })` — passes `pageId` straight to `AppRenderer`; its `onNavigate` pushes `/apps/${pk}/${nextPageId}` via `useNavigate()`. Route `/apps/:pk/:pageId?` (optional trailing segment, supported by react-router-dom ^6.5+) replaces the bare `/apps/:pk` runtime route; `/apps/:pk` with no `pageId` still renders (defaults to the first page inside `AppRenderer`, per Task 3).

- [ ] **Step 1: Write the failing route tests**

Edit `shell/src/shell/routes.test.tsx`. Widen the `AppRuntimePage` mock to also show `pageId`:

```tsx
vi.mock("../pages/AppRuntimePage", () => ({
  AppRuntimePage: ({ pk, pageId }: { pk: string; pageId?: string }) => <div>app-runtime-{pk}-{pageId ?? "none"}</div>,
}));
```

Update the existing assertion in `"renders the app runtime route at /apps/:pk"` from `"app-runtime-42"` to `"app-runtime-42-none"`:

```tsx
test("renders the app runtime route at /apps/:pk", () => {
  wrap(<AppRoutes />, "/apps/42");
  expect(screen.getByText("app-runtime-42-none")).toBeInTheDocument();
});
```

Append a new test:

```tsx
test("renders the app runtime route with a pageId at /apps/:pk/:pageId", () => {
  wrap(<AppRoutes />, "/apps/42/xyz");
  expect(screen.getByText("app-runtime-42-xyz")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx`
Expected: FAIL — `AppRuntimeRoute` doesn't read/forward `pageId`; the new route doesn't exist yet.

- [ ] **Step 3: Add the optional `pageId` route param**

Edit `shell/src/shell/routes.tsx`. Change `AppRuntimeRoute` and the route path:

```tsx
function AppRuntimeRoute() {
  const { pk, pageId } = useParams();
  return <AppRuntimePage pk={pk!} pageId={pageId} />;
}
```

```tsx
      <Route path="/apps/:pk/:pageId?" element={<AppRuntimeRoute />} />
```

(This replaces the existing `<Route path="/apps/:pk" element={<AppRuntimeRoute />} />` line. The more specific `<Route path="/apps/:pk/edit" .../>` stays declared first and keeps matching `/apps/:pk/edit` — react-router ranks a static segment above a dynamic/optional one regardless of declaration order; the existing `"renders the app builder route at /apps/:pk/edit"` test guards against a regression here.)

- [ ] **Step 4: Run to verify the route tests pass**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx`
Expected: PASS (all 5 tests, including the untouched `/apps/:pk/edit` one).

- [ ] **Step 5: Wire `AppRuntimePage` to accept and push `pageId`**

Replace `shell/src/pages/AppRuntimePage.tsx` with:

```tsx
import { useNavigate } from "react-router-dom";
import { useAppConfig } from "../api/hooks";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";

registerBuiltinWidgets();

export function AppRuntimePage({ pk, pageId }: { pk: string; pageId?: string }) {
  const query = useAppConfig(pk);
  const navigate = useNavigate();
  if (query.isLoading) return <p role="status">Chargement…</p>;
  if (query.isError || !query.data)
    return <p role="alert" className="text-sm text-red-600">Application introuvable.</p>;
  return (
    <div className="h-full w-full">
      <AppRenderer
        config={query.data}
        mode="runtime"
        pageId={pageId}
        onNavigate={(nextPageId) => navigate(`/apps/${pk}/${nextPageId}`)}
      />
    </div>
  );
}
```

- [ ] **Step 6: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/shell/routes.tsx shell/src/shell/routes.test.tsx shell/src/pages/AppRuntimePage.tsx
git commit -m "feat(shell): runtime route /apps/:pk/:pageId? navigates between pages

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Widget Navigation/Menu

**Files:**
- Create: `shell/src/builder/widgets/navigation.tsx`
- Modify: `shell/src/builder/widgets/index.tsx`
- Test: `shell/src/builder/widgets/navigation.test.tsx`

**Interfaces:**
- Consumes: `registerWidget`, `WidgetContext.pages`/`.navigate` (Task 3).
- Produces: `registerNavigationWidget()` registering `nav` (label "Navigation"); props `{ direction: "horizontal" | "vertical" }`; renders one button per `ctx.pages` entry, labeled with the page's `name` (no `aria-label` override — the visible name IS the accessible name, matching the Bouton widget's own precedent, and letting tests/E2E target a page button by its human-readable name even though ids are opaque UUIDs). Clicking a button calls `ctx.navigate(page.id)`. Called from `registerBuiltinWidgets()`.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/widgets/navigation.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import type { Page } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const emptyLayout = { type: "grid" as const, breakpoints: {}, items: [] };
const pages: Page[] = [
  { id: "p1", name: "Accueil", layout: emptyLayout },
  { id: "p2", name: "Détails", layout: emptyLayout },
];

test("renders one button per page and calls ctx.navigate with its id on click", async () => {
  const Nav = getWidget("nav")!.Component;
  const navigate = vi.fn();
  render(<Nav props={{}} ctx={{ mode: "runtime", pages, navigate } as WidgetContext} />);
  await userEvent.click(screen.getByRole("button", { name: "Détails" }));
  expect(navigate).toHaveBeenCalledWith("p2");
});

test("shows a placeholder when there are no pages", () => {
  const Nav = getWidget("nav")!.Component;
  render(<Nav props={{}} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText(/aucune page/i)).toBeInTheDocument();
});

test("supports a vertical orientation prop", () => {
  const Nav = getWidget("nav")!.Component;
  const { container } = render(
    <Nav props={{ direction: "vertical" }} ctx={{ mode: "runtime", pages, navigate: vi.fn() } as WidgetContext} />,
  );
  expect(container.querySelector("nav")).toHaveClass("flex-col");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/navigation.test.tsx`
Expected: FAIL — `nav` not registered.

- [ ] **Step 3: Implement the Navigation widget**

Create `shell/src/builder/widgets/navigation.tsx`:

```tsx
import { registerWidget } from "../registry";

export function registerNavigationWidget(): void {
  registerWidget({
    type: "nav",
    label: "Navigation",
    defaultProps: { direction: "horizontal" },
    defaultSize: { w: 4, h: 1 },
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">Orientation
          <select
            aria-label="Orientation du menu"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.direction ?? "horizontal")}
            onChange={(e) => onChange({ ...props, direction: e.target.value })}
          >
            <option value="horizontal">Horizontale</option>
            <option value="vertical">Verticale</option>
          </select>
        </label>
        <p className="text-[10px] text-slate-400">Affiche automatiquement toutes les pages de l'application.</p>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const pages = ctx.pages ?? [];
      const vertical = props.direction === "vertical";
      if (pages.length === 0) return <p className="text-xs text-slate-400">Aucune page.</p>;
      return (
        <nav className={`flex gap-1 ${vertical ? "flex-col" : "flex-row flex-wrap"}`}>
          {pages.map((p) => (
            <button
              key={p.id}
              type="button"
              className="rounded-[var(--gs-radius)] border border-[var(--gs-color-border)] px-2 py-1 text-sm text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
              onClick={() => ctx.navigate?.(p.id)}
            >
              {p.name}
            </button>
          ))}
        </nav>
      );
    },
  });
}
```

- [ ] **Step 4: Register the Navigation widget**

Edit `shell/src/builder/widgets/index.tsx`. Add the import:

```tsx
import { registerNavigationWidget } from "./navigation";
```

Call it at the end of `registerBuiltinWidgets()`, after `registerChartWidget();`:

```tsx
  registerDataWidgets();
  registerIndicatorWidget();
  registerMapWidget();
  registerFilterWidget();
  registerChartWidget();
  registerNavigationWidget();
```

- [ ] **Step 5: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/widgets/navigation.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/widgets/navigation.tsx shell/src/builder/widgets/navigation.test.tsx shell/src/builder/widgets/index.tsx
git commit -m "feat(shell): add Navigation/Menu widget consuming ctx.pages + ctx.navigate

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: E2E — add a page and a Navigation widget, navigate in the runtime

**Files:**
- Create: `shell/e2e/pages-navigation.spec.ts`

**Interfaces:**
- Consumes: the stateful by-item mock store + `mockGeoNode` (existing — the generic PUT-echo already round-trips any new field, including `pages`, with no mock change needed), the `PageManager`'s deterministic `"page-1"` implicit-page id, the Navigation widget (Task 6).
- Produces: an E2E that creates an app, adds a second page via `PageManager`, adds a Navigation widget to the first page, saves, opens the runtime, and clicks the Navigation widget's "Page 2" button to confirm the URL navigates to a per-page route.

- [ ] **Step 1: Write the E2E**

Create `shell/e2e/pages-navigation.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("adding a page and a Navigation widget lets the runtime navigate between pages", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App pages");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add a second page (this materializes the implicit first page as "page-1")
  // then switch back to editing the first page.
  await page.getByRole("button", { name: "Ajouter une page" }).click();
  await page.getByRole("button", { name: "Ouvrir la page page-1" }).click();

  // Add a Navigation widget to page 1.
  await page.getByRole("button", { name: "Navigation" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime: page 1 shows a Navigation menu; clicking "Page 2" navigates the URL.
  await page.goto("/apps/9");
  await expect(page.getByRole("button", { name: "Page 2" })).toBeVisible();
  await page.getByRole("button", { name: "Page 2" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/[^/]+$/);
});
```

- [ ] **Step 2: Run the new E2E**

Run: `cd shell && npx playwright test pages-navigation`
Expected: PASS — the URL becomes `/apps/9/<uuid>` after clicking "Page 2".

- [ ] **Step 3: Run the full E2E suite**

Run: `cd shell && npx playwright test`
Expected: all specs pass (catalog + map-editor + app-builder + data-widget + actions + chart + responsive + theme + pages-navigation).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/pages-navigation.spec.ts
git commit -m "test(shell): E2E add a page + Navigation widget, navigate in the runtime

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage (design 0d.5 §5b « Pages, navigation, routage ») :** `pages[]` additive backend + front type → Tasks 1–2. `PageManager` (ajouter/renommer/supprimer/ordonner) → Task 4. Widget **Navigation/Menu** + routage de pages → Tasks 3, 5, 6. Action de navigation reportée de SP-0d.3 → delivered as `ctx.navigate` (direct, per-widget mechanism) rather than a generic bus action — an explicit, documented scope decision (see the plan's Scope note), since no existing emitter's payload carries a `pageId`. End-to-end proof (add page → add Nav → save → runtime → click → URL changes) → Task 7.
- **Placeholder scan:** none — every step carries complete code or an exact edit against a quoted anchor.
- **Type consistency:** `Page = { id, name, layout: AppLayout }` defined once in `api/types.ts`, consumed identically by `pages.ts` (`getPages`/`getPageLayout`/`setPageLayout`), `AppRenderer` (`pages`, `activePageId`, `activeLayout`), `WidgetContext.pages`, `PageManager`, `AppBuilderPage`, and the Navigation widget. `AppRenderer`'s new `pageId?`/`onNavigate?` props are threaded identically by `AppBuilderPage` (local `activePageId` state) and `AppRuntimePage` (route param + `useNavigate`). The deterministic implicit-page id `"page-1"` (from `pages.ts`) is relied upon consistently by the `AppBuilderPage` test and the E2E.
- **Backward compatibility:** `AppConfig.pages?` is optional, mirroring the `WidgetItem.layouts?` precedent from SP-0d.5a — no existing `AppConfig` test literal anywhere in the codebase needs a new field. `getPages`/`setPageLayout` treat an absent/empty `pages` as a legacy single implicit page, so every existing `AppRenderer`/`AppBuilderPage` test (which never sets `pages`) renders and edits exactly as before — verified explicitly in Task 3's and Task 4's "Expected" notes. `WidgetHost`'s new `pages`/`navigate` props are optional with a safe default (`pages = []`), so the pre-existing `WidgetHost.test.tsx` (which never passes them) is unaffected. Backend `pages` defaults to `[]` via `Field(default_factory=list)`, no validator change.
- **Façade discipline:** no new network access; `pages` flows through the existing `getAppConfig`/`saveAppConfig` façade methods, extended the same way `theme`/`messages`/`dataSources` were in earlier phases.
- **Engine unity:** `AppRenderer` resolves the active page and threads `ctx.pages`/`ctx.navigate` identically in `edit`/`preview`/`runtime`; only the *source of truth* for `pageId`/`onNavigate` differs (editor state vs. route), matching the exact pattern already established for `breakpoint` in SP-0d.5a.
