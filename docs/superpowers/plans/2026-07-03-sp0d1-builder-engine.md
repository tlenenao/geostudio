# GeoStudio SP-0d.1 — Moteur & canvas du builder — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the no-code loop end to end — open an app, drag static widgets (Text/Image/Button) onto a responsive grid, edit their props, save, and view the published result through a single config-driven renderer.

**Architecture:** One rendering engine `AppRenderer(config, mode)` (edit/preview/runtime) renders a `BuilderConfig`'s grid layout via `GridCanvas` + `WidgetHost` (per-widget error isolation) using a widget registry. The builder page holds a local draft, saves through the item-client (`saveAppConfig` → builder `PUT /configs/by-item/{id}`, added in SP-0c-e). The published app renders read-only at `/apps/:pk`. Home-grown grid (CSS grid + pure geometry helpers; real drag validated in E2E). Backend gains one additive field: `LayoutItem.id`.

**Tech Stack:** Python 3.12+/FastAPI/pytest (backend); React 19 + TS + Vite 6 + Vitest 3 + Testing Library + MSW + Playwright (frontend).

## Global Constraints

- One rendering engine for edit/preview/runtime — no divergence.
- Persistence via Builder Service `kind="app"|"dashboard"`; schema extensions ADDITIVE (existing configs stay valid). Save uses the existing `PUT /configs/by-item/{id}`.
- Front: ALL network via `item-client`; no service URL hard-coded; `Item`/`ItemClient`/`BuilderConfig` extended without breaking.
- A widget in error must never break the whole app render (`WidgetHost` isolation).
- Heavy libs mocked in unit; real interaction validated in E2E.
- No token in localStorage. MSW `onUnhandledRequest:"error"`.
- pytest `filterwarnings=["error"]` with the two authorized ignores; in-memory sqlite fixtures use `engine.dispose()` + `StaticPool`.
- Commit messages end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on branch `dev`.
- Builder `BuilderConfig` for app/dashboard = `{ version, kind, theme{}, dataSources[], layout{type:"grid",breakpoints{},items[{widget,x,y,w,h,props}]}, messages[] }`; `ConfigRead` nests it under `config` (`config.layout`, `config.kind`).

---

### Task 1: Backend — additive `LayoutItem.id`

**Files:**
- Modify: `builder-service/app/schemas.py`
- Test: `builder-service/tests/test_schemas.py` (append)

**Interfaces:**
- Consumes: existing `LayoutItem`.
- Produces: `LayoutItem.id: str | None = None` — accepted and round-tripped; existing configs without item ids remain valid.

- [ ] **Step 1: Write the failing test**

Append to `builder-service/tests/test_schemas.py`:

```python
from app.schemas import LayoutItem


def test_layout_item_accepts_optional_id():
    item = LayoutItem(id="w1", widget="text", x=0, y=0, w=4, h=2, props={"text": "Hi"})
    assert item.id == "w1"
    dumped = item.model_dump()
    assert dumped["id"] == "w1"


def test_layout_item_id_defaults_to_none():
    item = LayoutItem(widget="text", x=0, y=0, w=4, h=2)
    assert item.id is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd builder-service && uv run pytest tests/test_schemas.py -k layout_item -v`
Expected: FAIL — `LayoutItem` rejects `id` / has no `id` attribute.

- [ ] **Step 3: Add the field**

Edit `builder-service/app/schemas.py`, in `class LayoutItem` add `id` as the first field:

```python
class LayoutItem(BaseModel):
    id: str | None = None
    widget: str
    x: int
    y: int
    w: int
    h: int
    props: dict = Field(default_factory=dict)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd builder-service && uv run pytest tests/test_schemas.py -k layout_item -v`
Expected: PASS (both).

- [ ] **Step 5: Full backend suite**

Run: `cd builder-service && uv run pytest`
Expected: all pass, no warnings-as-errors.

- [ ] **Step 6: Commit**

```bash
git add builder-service/app/schemas.py builder-service/tests/test_schemas.py
git commit -m "feat(builder): add optional LayoutItem.id for widget identity

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Frontend types + widget registry + Text/Image/Button widgets

**Files:**
- Modify: `shell/src/api/types.ts` (app config + widget types)
- Create: `shell/src/builder/registry.ts`, `shell/src/builder/widgets/index.tsx`
- Test: `shell/src/builder/registry.test.tsx`

**Interfaces:**
- Produces:
  - `WidgetItem = { id: string; widget: string; x: number; y: number; w: number; h: number; props: Record<string, unknown> }`
  - `AppLayout = { type: "grid"; breakpoints: Record<string, unknown>; items: WidgetItem[] }`
  - `AppConfig = { kind: "app" | "dashboard"; theme: Record<string, unknown>; dataSources: unknown[]; messages: unknown[]; layout: AppLayout }`
  - `RenderMode = "edit" | "preview" | "runtime"`
  - Registry: `registerWidget(def)`, `getWidget(type)`, `listWidgets()`, and a `WidgetDefinition` type.
  - `registerBuiltinWidgets()` registers `text`, `image`, `button`.

- [ ] **Step 1: Add the app/widget types**

Edit `shell/src/api/types.ts`, append:

```ts
export type RenderMode = "edit" | "preview" | "runtime";

export type WidgetItem = {
  id: string;
  widget: string;
  x: number;
  y: number;
  w: number;
  h: number;
  props: Record<string, unknown>;
};

export type AppLayout = {
  type: "grid";
  breakpoints: Record<string, unknown>;
  items: WidgetItem[];
};

export type AppConfig = {
  kind: "app" | "dashboard";
  theme: Record<string, unknown>;
  dataSources: unknown[];
  messages: unknown[];
  layout: AppLayout;
};
```

Add to the `ItemClient` interface (after `saveMapConfig`):

```ts
  getAppConfig(pk: string): Promise<AppConfig>;
  saveAppConfig(pk: string, config: AppConfig): Promise<void>;
```

- [ ] **Step 2: Write the failing registry test**

Create `shell/src/builder/registry.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { registerWidget, getWidget, listWidgets, _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import type { WidgetContext } from "./registry";

const ctx = { mode: "runtime" } as WidgetContext;

beforeEach(() => _resetRegistry());

test("registers and retrieves a widget definition", () => {
  registerWidget({
    type: "demo",
    label: "Demo",
    defaultProps: { a: 1 },
    defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />,
    Component: () => <div>demo</div>,
  });
  expect(getWidget("demo")?.label).toBe("Demo");
  expect(listWidgets().map((w) => w.type)).toEqual(["demo"]);
});

test("builtin widgets render their props", () => {
  registerBuiltinWidgets();
  const kinds = listWidgets().map((w) => w.type);
  expect(kinds).toEqual(expect.arrayContaining(["text", "image", "button"]));

  const Text = getWidget("text")!.Component;
  render(<Text props={{ text: "Bonjour" }} ctx={ctx} />);
  expect(screen.getByText("Bonjour")).toBeInTheDocument();

  const Button = getWidget("button")!.Component;
  render(<Button props={{ label: "Cliquer" }} ctx={ctx} />);
  expect(screen.getByRole("button", { name: "Cliquer" })).toBeInTheDocument();

  const Image = getWidget("image")!.Component;
  render(<Image props={{ src: "http://x/y.png", alt: "Y" }} ctx={ctx} />);
  expect(screen.getByRole("img", { name: "Y" })).toHaveAttribute("src", "http://x/y.png");
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/registry.test.tsx`
Expected: FAIL — modules missing.

- [ ] **Step 4: Implement the registry**

Create `shell/src/builder/registry.ts`:

```ts
import type { ReactNode } from "react";
import type { RenderMode } from "../api/types";

export type WidgetContext = {
  mode: RenderMode;
  navigate?: (pageId: string) => void;
};

export type WidgetDefinition<P extends Record<string, unknown> = Record<string, unknown>> = {
  type: string;
  label: string;
  icon?: ReactNode;
  defaultProps: P;
  defaultSize: { w: number; h: number };
  PropsPanel: (p: { props: P; onChange: (props: P) => void }) => JSX.Element;
  Component: (p: { props: P; ctx: WidgetContext }) => JSX.Element;
};

const registry = new Map<string, WidgetDefinition>();

export function registerWidget(def: WidgetDefinition): void {
  registry.set(def.type, def);
}
export function getWidget(type: string): WidgetDefinition | undefined {
  return registry.get(type);
}
export function listWidgets(): WidgetDefinition[] {
  return [...registry.values()];
}
export function _resetRegistry(): void {
  registry.clear();
}
```

- [ ] **Step 5: Implement the three builtin widgets**

Create `shell/src/builder/widgets/index.tsx`:

```tsx
import { registerWidget } from "../registry";

export function registerBuiltinWidgets(): void {
  registerWidget({
    type: "text",
    label: "Texte",
    defaultProps: { text: "Nouveau texte" },
    defaultSize: { w: 4, h: 2 },
    PropsPanel: ({ props, onChange }) => (
      <label className="flex flex-col gap-1 text-sm">
        Texte
        <textarea
          aria-label="Texte du widget"
          className="rounded-md border border-slate-300 p-2 text-sm"
          value={String(props.text ?? "")}
          onChange={(e) => onChange({ ...props, text: e.target.value })}
        />
      </label>
    ),
    Component: ({ props }) => <p className="whitespace-pre-wrap">{String(props.text ?? "")}</p>,
  });

  registerWidget({
    type: "image",
    label: "Image",
    defaultProps: { src: "", alt: "" },
    defaultSize: { w: 4, h: 4 },
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          URL
          <input
            aria-label="URL de l'image"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.src ?? "")}
            onChange={(e) => onChange({ ...props, src: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          Texte alternatif
          <input
            aria-label="Texte alternatif"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.alt ?? "")}
            onChange={(e) => onChange({ ...props, alt: e.target.value })}
          />
        </label>
      </div>
    ),
    Component: ({ props }) =>
      props.src ? (
        <img className="h-full w-full object-cover" src={String(props.src)} alt={String(props.alt ?? "")} />
      ) : (
        <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-slate-400">
          Image
        </div>
      ),
  });

  registerWidget({
    type: "button",
    label: "Bouton",
    defaultProps: { label: "Bouton", href: "" },
    defaultSize: { w: 2, h: 1 },
    PropsPanel: ({ props, onChange }) => (
      <div className="flex flex-col gap-2 text-sm">
        <label className="flex flex-col gap-1">
          Libellé
          <input
            aria-label="Libellé du bouton"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.label ?? "")}
            onChange={(e) => onChange({ ...props, label: e.target.value })}
          />
        </label>
        <label className="flex flex-col gap-1">
          Lien
          <input
            aria-label="Lien du bouton"
            className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.href ?? "")}
            onChange={(e) => onChange({ ...props, href: e.target.value })}
          />
        </label>
      </div>
    ),
    Component: ({ props }) => (
      <button
        type="button"
        className="rounded-md bg-slate-800 px-3 py-1.5 text-sm text-white"
        onClick={() => {
          const href = String(props.href ?? "");
          if (href) window.open(href, "_blank", "noopener");
        }}
      >
        {String(props.label ?? "Bouton")}
      </button>
    ),
  });
}
```

- [ ] **Step 6: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/registry.test.tsx`
Expected: PASS.

- [ ] **Step 7: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/api/types.ts shell/src/builder/registry.ts shell/src/builder/widgets/index.tsx shell/src/builder/registry.test.tsx
git commit -m "feat(shell): add widget registry + Text/Image/Button widgets

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: item-client `getAppConfig`/`saveAppConfig` + hooks

**Files:**
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/hooks.ts`
- Test: `shell/src/api/itemClient.test.ts`, `shell/src/api/hooks.test.tsx`

**Interfaces:**
- Consumes: `builderUrl`, `GET`/`PUT /configs/by-item/{id}`, `AppConfig`.
- Produces:
  - `getAppConfig(pk): Promise<AppConfig>` — reads `config` (kind/theme/dataSources/messages/layout) from by-item GET.
  - `saveAppConfig(pk, config): Promise<void>` — PUTs `{version:1, kind, theme, dataSources, messages, layout}` to by-item.
  - `useAppConfig(pk, opts?)`, `useSaveApp(pk)`.

- [ ] **Step 1: Write the failing MSW tests (item-client)**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("getAppConfig reads the app config (kind/theme/layout)", async () => {
  server.use(
    http.get("https://builder.test/configs/by-item/5", () =>
      HttpResponse.json({
        id: "cfg-5", itemId: "5", kind: "app",
        config: {
          kind: "app", theme: { primary: "#123" }, dataSources: [], messages: [],
          layout: { type: "grid", breakpoints: {}, items: [
            { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
          ] },
        },
      }),
    ),
  );
  const cfg = await makeClient().getAppConfig("5");
  expect(cfg.kind).toBe("app");
  expect(cfg.layout.items[0]).toMatchObject({ id: "w1", widget: "text" });
});

test("getAppConfig throws when the config has no layout", async () => {
  server.use(
    http.get("https://builder.test/configs/by-item/5", () =>
      HttpResponse.json({ id: "cfg-5", itemId: "5", kind: "map", config: { kind: "map", layout: null } }),
    ),
  );
  await expect(makeClient().getAppConfig("5")).rejects.toThrow();
});

test("saveAppConfig PUTs the app config by item", async () => {
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
  });
  expect(body.kind).toBe("app");
  expect(body.layout.type).toBe("grid");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — methods not implemented.

- [ ] **Step 3: Implement the two methods**

Edit `shell/src/api/itemClient.ts`. Add `AppConfig` to the type import. Add these methods after `saveMapConfig`:

```ts
    async getAppConfig(pk: string): Promise<AppConfig> {
      const token = getToken();
      const res = await fetch(`${builderUrl}/configs/by-item/${pk}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} GET /configs/by-item/${pk}`);
      const data = (await res.json()) as {
        config?: {
          kind?: "app" | "dashboard";
          theme?: Record<string, unknown>;
          dataSources?: unknown[];
          messages?: unknown[];
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
        layout: c.layout,
      };
    },

    async saveAppConfig(pk: string, config: AppConfig): Promise<void> {
      const token = getToken();
      const res = await fetch(`${builderUrl}/configs/by-item/${pk}`, {
        method: "PUT",
        headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) },
        body: JSON.stringify({
          version: 1,
          kind: config.kind,
          theme: config.theme,
          dataSources: config.dataSources,
          messages: config.messages,
          layout: config.layout,
        }),
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} PUT /configs/by-item/${pk}`);
    },
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS.

- [ ] **Step 5: Write the failing hook tests**

Append to `shell/src/api/hooks.test.tsx` (reuse the existing `makeWrapper(client)` helper from SP-0c-e Task 3):

```tsx
test("useAppConfig loads an app config", async () => {
  const cfg = { kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [] } };
  const client = { getAppConfig: vi.fn().mockResolvedValue(cfg) } as unknown as ItemClient;
  const { result } = renderHook(() => useAppConfig("5"), { wrapper: makeWrapper(client) });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toEqual(cfg);
});

test("useSaveApp saves an app config", async () => {
  const client = { saveAppConfig: vi.fn().mockResolvedValue(undefined) } as unknown as ItemClient;
  const { result } = renderHook(() => useSaveApp("5"), { wrapper: makeWrapper(client) });
  const cfg = { kind: "app" as const, theme: {}, dataSources: [], messages: [],
    layout: { type: "grid" as const, breakpoints: {}, items: [] } };
  await result.current.mutateAsync(cfg);
  expect(client.saveAppConfig).toHaveBeenCalledWith("5", cfg);
});
```

Add `useAppConfig`, `useSaveApp` to the hook imports at the top of the test file.

- [ ] **Step 6: Implement the hooks**

Edit `shell/src/api/hooks.ts`. Add `AppConfig` to the `./types` import, then add:

```ts
export function useAppConfig(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClient();
  return useQuery({
    queryKey: ["app", pk],
    queryFn: () => client.getAppConfig(pk),
    enabled: options?.enabled ?? true,
  });
}

export function useSaveApp(pk: string) {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: AppConfig) => client.saveAppConfig(pk, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["app", pk] });
    },
  });
}
```

- [ ] **Step 7: Run hook tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/api/hooks.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/api/hooks.ts shell/src/api/hooks.test.tsx
git commit -m "feat(shell): add getAppConfig/saveAppConfig + useAppConfig/useSaveApp

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `GridCanvas` — geometry helpers + component

**Files:**
- Create: `shell/src/builder/grid.ts`, `shell/src/builder/GridCanvas.tsx`
- Test: `shell/src/builder/grid.test.ts`, `shell/src/builder/GridCanvas.test.tsx`

**Interfaces:**
- Produces:
  - `grid.ts`: `GRID_COLS = 12`; `moveItem(item, dxCells, dyCells): WidgetItem` (clamps to `[0, GRID_COLS-w]` in x, `y>=0`); `resizeItem(item, dwCells, dhCells): WidgetItem` (min 1×1, `w<=GRID_COLS-x`); `styleFor(item): CSSProperties` (`gridColumn`/`gridRow`).
  - `GridCanvas({ items, editable, selectedId, onSelect, onMoveItem, renderItem })` — CSS grid; click selects; a drag handle calls `onMoveItem(id, dxCells, dyCells)` (real drag validated in E2E; unit tests drive `onMoveItem` through the handle's keyboard fallback).

- [ ] **Step 1: Write the failing geometry tests**

Create `shell/src/builder/grid.test.ts`:

```ts
import { expect, test } from "vitest";
import { GRID_COLS, moveItem, resizeItem, styleFor } from "./grid";
import type { WidgetItem } from "../api/types";

const base: WidgetItem = { id: "a", widget: "text", x: 2, y: 2, w: 4, h: 2, props: {} };

test("moveItem shifts by cells and clamps to the grid", () => {
  expect(moveItem(base, 1, 1)).toMatchObject({ x: 3, y: 3 });
  expect(moveItem(base, -5, -5)).toMatchObject({ x: 0, y: 0 });
  expect(moveItem(base, 100, 0).x).toBe(GRID_COLS - base.w);
});

test("resizeItem changes size with min 1 and right-edge clamp", () => {
  expect(resizeItem(base, 2, 1)).toMatchObject({ w: 6, h: 3 });
  expect(resizeItem(base, -10, -10)).toMatchObject({ w: 1, h: 1 });
  expect(resizeItem({ ...base, x: 10 }, 100, 0).w).toBe(GRID_COLS - 10);
});

test("styleFor maps to CSS grid placement", () => {
  expect(styleFor(base)).toMatchObject({
    gridColumn: "3 / span 4",
    gridRow: "3 / span 2",
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/grid.test.ts`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement the geometry helpers**

Create `shell/src/builder/grid.ts`:

```ts
import type { CSSProperties } from "react";
import type { WidgetItem } from "../api/types";

export const GRID_COLS = 12;

export function moveItem(item: WidgetItem, dxCells: number, dyCells: number): WidgetItem {
  const x = Math.max(0, Math.min(GRID_COLS - item.w, item.x + dxCells));
  const y = Math.max(0, item.y + dyCells);
  return { ...item, x, y };
}

export function resizeItem(item: WidgetItem, dwCells: number, dhCells: number): WidgetItem {
  const w = Math.max(1, Math.min(GRID_COLS - item.x, item.w + dwCells));
  const h = Math.max(1, item.h + dhCells);
  return { ...item, w, h };
}

export function styleFor(item: WidgetItem): CSSProperties {
  return {
    gridColumn: `${item.x + 1} / span ${item.w}`,
    gridRow: `${item.y + 1} / span ${item.h}`,
  };
}
```

- [ ] **Step 4: Write the failing GridCanvas test**

Create `shell/src/builder/GridCanvas.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { WidgetItem } from "../api/types";
import { GridCanvas } from "./GridCanvas";

const items: WidgetItem[] = [
  { id: "a", widget: "text", x: 0, y: 0, w: 4, h: 2, props: {} },
  { id: "b", widget: "image", x: 4, y: 0, w: 4, h: 2, props: {} },
];

function renderCanvas(over: Partial<React.ComponentProps<typeof GridCanvas>> = {}) {
  return render(
    <GridCanvas
      items={items}
      editable
      selectedId={null}
      onSelect={over.onSelect ?? vi.fn()}
      onMoveItem={over.onMoveItem ?? vi.fn()}
      renderItem={(item) => <div>widget-{item.id}</div>}
      {...over}
    />,
  );
}

test("renders each item via renderItem", () => {
  renderCanvas();
  expect(screen.getByText("widget-a")).toBeInTheDocument();
  expect(screen.getByText("widget-b")).toBeInTheDocument();
});

test("selecting an item calls onSelect with its id", async () => {
  const onSelect = vi.fn();
  renderCanvas({ onSelect });
  await userEvent.click(screen.getByRole("button", { name: "Sélectionner widget-a" }));
  expect(onSelect).toHaveBeenCalledWith("a");
});

test("the move handle nudges the item by one cell", async () => {
  const onMoveItem = vi.fn();
  renderCanvas({ selectedId: "a", onMoveItem });
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-a à droite" }));
  expect(onMoveItem).toHaveBeenCalledWith("a", 1, 0);
});
```

- [ ] **Step 5: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/GridCanvas.test.tsx`
Expected: FAIL — component missing.

- [ ] **Step 6: Implement `GridCanvas`**

Create `shell/src/builder/GridCanvas.tsx`:

```tsx
import type { ReactNode } from "react";
import type { WidgetItem } from "../api/types";
import { GRID_COLS, styleFor } from "./grid";

export function GridCanvas({
  items,
  editable,
  selectedId,
  onSelect,
  onMoveItem,
  renderItem,
}: {
  items: WidgetItem[];
  editable: boolean;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onMoveItem: (id: string, dxCells: number, dyCells: number) => void;
  renderItem: (item: WidgetItem) => ReactNode;
}) {
  return (
    <div
      className="grid h-full w-full gap-1 bg-slate-50"
      style={{ gridTemplateColumns: `repeat(${GRID_COLS}, 1fr)`, gridAutoRows: "40px" }}
      onClick={() => editable && onSelect(null)}
    >
      {items.map((item) => {
        const selected = editable && item.id === selectedId;
        return (
          <div
            key={item.id}
            style={styleFor(item)}
            className={`relative overflow-hidden rounded ${selected ? "outline outline-2 outline-blue-500" : ""}`}
          >
            {editable && (
              <button
                type="button"
                aria-label={`Sélectionner widget-${item.id}`}
                className="absolute inset-0 z-10 cursor-pointer"
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(item.id);
                }}
              />
            )}
            <div className="pointer-events-none h-full w-full p-1">{renderItem(item)}</div>
            {selected && (
              <div className="absolute right-0 top-0 z-20 flex gap-0.5">
                <button type="button" aria-label={`Déplacer widget-${item.id} à gauche`}
                  className="bg-blue-500 px-1 text-xs text-white" onClick={(e) => { e.stopPropagation(); onMoveItem(item.id, -1, 0); }}>←</button>
                <button type="button" aria-label={`Déplacer widget-${item.id} à droite`}
                  className="bg-blue-500 px-1 text-xs text-white" onClick={(e) => { e.stopPropagation(); onMoveItem(item.id, 1, 0); }}>→</button>
                <button type="button" aria-label={`Déplacer widget-${item.id} en bas`}
                  className="bg-blue-500 px-1 text-xs text-white" onClick={(e) => { e.stopPropagation(); onMoveItem(item.id, 0, 1); }}>↓</button>
                <button type="button" aria-label={`Déplacer widget-${item.id} en haut`}
                  className="bg-blue-500 px-1 text-xs text-white" onClick={(e) => { e.stopPropagation(); onMoveItem(item.id, 0, -1); }}>↑</button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 7: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/grid.test.ts src/builder/GridCanvas.test.tsx`
Expected: PASS.

- [ ] **Step 8: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/grid.ts shell/src/builder/grid.test.ts shell/src/builder/GridCanvas.tsx shell/src/builder/GridCanvas.test.tsx
git commit -m "feat(shell): add GridCanvas + grid geometry helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: `WidgetHost` (isolation) + `AppRenderer` (3 modes)

**Files:**
- Create: `shell/src/builder/WidgetHost.tsx`, `shell/src/builder/AppRenderer.tsx`
- Test: `shell/src/builder/WidgetHost.test.tsx`, `shell/src/builder/AppRenderer.test.tsx`

**Interfaces:**
- Consumes: `getWidget`, `GridCanvas`, `moveItem`, `AppConfig`/`WidgetItem`/`RenderMode`.
- Produces:
  - `WidgetHost({ item, mode })` — renders the registered widget in an error boundary; unknown/failed widget → local fallback, never throws up.
  - `AppRenderer({ config, mode, onChange?, selectedId?, onSelect? })` — renders `config.layout.items` via `GridCanvas`(editable = mode==="edit") + `WidgetHost`; in edit, `onMoveItem` maps to `moveItem` and calls `onChange` with the new config.

- [ ] **Step 1: Write the failing WidgetHost test**

Create `shell/src/builder/WidgetHost.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { registerWidget, _resetRegistry } from "./registry";
import { WidgetHost } from "./WidgetHost";
import type { WidgetItem } from "../api/types";

beforeEach(() => _resetRegistry());
afterEach(() => vi.restoreAllMocks());

const item = (widget: string, props = {}): WidgetItem => ({ id: "x", widget, x: 0, y: 0, w: 2, h: 2, props });

test("renders the registered widget", () => {
  registerWidget({ type: "ok", label: "Ok", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: ({ props }) => <div>ok-{String(props.n)}</div> });
  render(<WidgetHost item={item("ok", { n: 7 })} mode="runtime" />);
  expect(screen.getByText("ok-7")).toBeInTheDocument();
});

test("shows a fallback for an unknown widget type", () => {
  render(<WidgetHost item={item("nope")} mode="runtime" />);
  expect(screen.getByText(/widget inconnu/i)).toBeInTheDocument();
});

test("isolates a widget that throws during render", () => {
  vi.spyOn(console, "error").mockImplementation(() => {});
  registerWidget({ type: "boom", label: "Boom", defaultProps: {}, defaultSize: { w: 2, h: 2 },
    PropsPanel: () => <div />, Component: () => { throw new Error("boom"); } });
  render(<WidgetHost item={item("boom")} mode="runtime" />);
  expect(screen.getByText(/erreur du widget/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx`
Expected: FAIL — component missing.

- [ ] **Step 3: Implement `WidgetHost` (with an error boundary)**

Create `shell/src/builder/WidgetHost.tsx`:

```tsx
import { Component, type ReactNode } from "react";
import type { RenderMode, WidgetItem } from "../api/types";
import { getWidget } from "./registry";

class WidgetErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() {
    return { failed: true };
  }
  componentDidCatch(err: unknown) {
    console.error("WidgetHost: widget crashed", err);
  }
  render() {
    if (this.state.failed) {
      return <div className="flex h-full items-center justify-center bg-red-50 text-xs text-red-600">Erreur du widget</div>;
    }
    return this.props.children;
  }
}

export function WidgetHost({ item, mode }: { item: WidgetItem; mode: RenderMode }) {
  const def = getWidget(item.widget);
  if (!def) {
    return <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-slate-400">Widget inconnu : {item.widget}</div>;
  }
  const Widget = def.Component;
  return (
    <WidgetErrorBoundary>
      <Widget props={item.props} ctx={{ mode }} />
    </WidgetErrorBoundary>
  );
}
```

- [ ] **Step 4: Write the failing AppRenderer test**

Create `shell/src/builder/AppRenderer.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { AppRenderer } from "./AppRenderer";
import type { AppConfig } from "../api/types";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

const config: AppConfig = {
  kind: "app", theme: {}, dataSources: [], messages: [],
  layout: { type: "grid", breakpoints: {}, items: [
    { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Salut" } },
  ] },
};

test("runtime mode renders widgets without edit chrome", () => {
  render(<AppRenderer config={config} mode="runtime" />);
  expect(screen.getByText("Salut")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Sélectionner/ })).toBeNull();
});

test("edit mode moving a widget calls onChange with the new position", async () => {
  const onChange = vi.fn();
  render(<AppRenderer config={config} mode="edit" selectedId="t1" onSelect={vi.fn()} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-t1 à droite" }));
  const next = onChange.mock.calls[0][0] as AppConfig;
  expect(next.layout.items[0]).toMatchObject({ x: 1 });
});
```

- [ ] **Step 5: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: FAIL — component missing.

- [ ] **Step 6: Implement `AppRenderer`**

Create `shell/src/builder/AppRenderer.tsx`:

```tsx
import type { AppConfig, RenderMode } from "../api/types";
import { GridCanvas } from "./GridCanvas";
import { WidgetHost } from "./WidgetHost";
import { moveItem } from "./grid";

export function AppRenderer({
  config,
  mode,
  onChange,
  selectedId = null,
  onSelect,
}: {
  config: AppConfig;
  mode: RenderMode;
  onChange?: (config: AppConfig) => void;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
}) {
  const editable = mode === "edit";

  function handleMove(id: string, dx: number, dy: number) {
    if (!onChange) return;
    onChange({
      ...config,
      layout: {
        ...config.layout,
        items: config.layout.items.map((it) => (it.id === id ? moveItem(it, dx, dy) : it)),
      },
    });
  }

  return (
    <GridCanvas
      items={config.layout.items}
      editable={editable}
      selectedId={selectedId}
      onSelect={(id) => onSelect?.(id)}
      onMoveItem={handleMove}
      renderItem={(item) => <WidgetHost item={item} mode={mode} />}
    />
  );
}
```

- [ ] **Step 7: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/WidgetHost.test.tsx src/builder/AppRenderer.test.tsx`
Expected: PASS.

- [ ] **Step 8: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/WidgetHost.tsx shell/src/builder/WidgetHost.test.tsx shell/src/builder/AppRenderer.tsx shell/src/builder/AppRenderer.test.tsx
git commit -m "feat(shell): add WidgetHost isolation + AppRenderer engine (3 modes)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: `WidgetPalette` + `PropsPanel`

**Files:**
- Create: `shell/src/builder/WidgetPalette.tsx`, `shell/src/builder/PropsPanel.tsx`
- Test: `shell/src/builder/WidgetPalette.test.tsx`, `shell/src/builder/PropsPanel.test.tsx`

**Interfaces:**
- Consumes: `listWidgets`, `getWidget`, `WidgetItem`.
- Produces:
  - `WidgetPalette({ onAdd })` — lists `listWidgets()`; clicking one calls `onAdd(type)`.
  - `PropsPanel({ item, onChange })` — renders the selected widget's `PropsPanel` bound to `item.props`; `onChange(nextProps)`.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/WidgetPalette.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { WidgetPalette } from "./WidgetPalette";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

test("lists widgets and emits the type on click", async () => {
  const onAdd = vi.fn();
  render(<WidgetPalette onAdd={onAdd} />);
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  expect(onAdd).toHaveBeenCalledWith("text");
});
```

Create `shell/src/builder/PropsPanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { PropsPanel } from "./PropsPanel";
import type { WidgetItem } from "../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const item: WidgetItem = { id: "t", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } };

test("edits the selected widget's props", async () => {
  const onChange = vi.fn();
  render(<PropsPanel item={item} onChange={onChange} />);
  const area = screen.getByLabelText("Texte du widget");
  await userEvent.type(area, "!");
  expect(onChange).toHaveBeenCalled();
  const last = onChange.mock.calls.at(-1)![0];
  expect(String(last.text).startsWith("Hi")).toBe(true);
});

test("shows a placeholder when nothing is selected", () => {
  render(<PropsPanel item={null} onChange={vi.fn()} />);
  expect(screen.getByText(/aucun widget/i)).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd shell && npx vitest run src/builder/WidgetPalette.test.tsx src/builder/PropsPanel.test.tsx`
Expected: FAIL — components missing.

- [ ] **Step 3: Implement `WidgetPalette`**

Create `shell/src/builder/WidgetPalette.tsx`:

```tsx
import { listWidgets } from "./registry";

export function WidgetPalette({ onAdd }: { onAdd: (type: string) => void }) {
  return (
    <ul className="flex flex-col gap-1">
      {listWidgets().map((def) => (
        <li key={def.type}>
          <button
            type="button"
            className="w-full rounded-md border border-slate-200 px-2 py-1.5 text-left text-sm hover:bg-slate-100"
            onClick={() => onAdd(def.type)}
          >
            {def.label}
          </button>
        </li>
      ))}
    </ul>
  );
}
```

- [ ] **Step 4: Implement `PropsPanel`**

Create `shell/src/builder/PropsPanel.tsx`:

```tsx
import type { WidgetItem } from "../api/types";
import { getWidget } from "./registry";

export function PropsPanel({
  item,
  onChange,
}: {
  item: WidgetItem | null;
  onChange: (props: Record<string, unknown>) => void;
}) {
  if (!item) {
    return <p className="text-xs text-slate-400">Aucun widget sélectionné.</p>;
  }
  const def = getWidget(item.widget);
  if (!def) {
    return <p className="text-xs text-slate-400">Widget inconnu : {item.widget}</p>;
  }
  const Panel = def.PropsPanel;
  return <Panel props={item.props} onChange={(p) => onChange(p)} />;
}
```

- [ ] **Step 5: Run to verify they pass**

Run: `cd shell && npx vitest run src/builder/WidgetPalette.test.tsx src/builder/PropsPanel.test.tsx`
Expected: PASS.

- [ ] **Step 6: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/WidgetPalette.tsx shell/src/builder/WidgetPalette.test.tsx shell/src/builder/PropsPanel.tsx shell/src/builder/PropsPanel.test.tsx
git commit -m "feat(shell): add WidgetPalette and PropsPanel

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: `AppBuilderPage` + routing + open-from-catalog

**Files:**
- Create: `shell/src/pages/AppBuilderPage.tsx`, `shell/src/pages/AppRuntimePage.tsx`
- Test: `shell/src/pages/AppBuilderPage.test.tsx`
- Modify: `shell/src/builder/widgets/index.tsx` (idempotent registration guard), `shell/src/shell/routes.tsx`, `shell/src/shell/NewItemButton.tsx`
- Test: `shell/src/shell/routes.test.tsx` (extend)

**Interfaces:**
- Consumes: `useAppConfig`/`useSaveApp`, `AppRenderer`, `WidgetPalette`, `PropsPanel`, `registerBuiltinWidgets`, `getWidget`, `Button`, `AppConfig`/`WidgetItem`.
- Produces:
  - `AppBuilderPage({ pk })` — registers builtins once; loads config → draft; palette adds a widget (fresh id via `crypto.randomUUID()`, `defaultProps`/`defaultSize`, placed at y=0); `AppRenderer(edit)` with selection; `PropsPanel` edits selected props; toolbar mode toggle (edit/preview) + **Enregistrer** (`useSaveApp`); save error alert.
  - `AppRuntimePage({ pk })` — registers builtins; loads config; `AppRenderer(runtime)`; loading/error states.
  - Routes `/apps/:pk/edit` and `/apps/:pk`; catalog/detail route `app`/`dashboard` items to `/apps/:pk/edit`; `NewItemButton` navigates app/dashboard creation to `/apps/:pk/edit`.

- [ ] **Step 1: Make builtin registration idempotent**

Edit `shell/src/builder/widgets/index.tsx` — guard so repeated calls don't matter (pages call it on mount):

```tsx
import { getWidget, registerWidget } from "../registry";

export function registerBuiltinWidgets(): void {
  if (getWidget("text")) return;
  // ...existing three registerWidget(...) calls unchanged...
}
```

- [ ] **Step 2: Write the failing AppBuilderPage test**

Create `shell/src/pages/AppBuilderPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { AppConfig, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppBuilderPage } from "./AppBuilderPage";

const config: AppConfig = {
  kind: "app", theme: {}, dataSources: [], messages: [],
  layout: { type: "grid", breakpoints: {}, items: [] },
};

function renderPage(client: Partial<ItemClient>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <AppBuilderPage pk="5" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("adds a widget from the palette and saves the config", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config), saveAppConfig });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.layout.items).toHaveLength(1);
  expect(saved.layout.items[0].widget).toBe("text");
});

test("shows an error when loading fails", async () => {
  renderPage({ getAppConfig: vi.fn().mockRejectedValue(new Error("x")) });
  expect(await screen.findByRole("alert")).toHaveTextContent(/introuvable/i);
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: FAIL — page missing.

- [ ] **Step 4: Implement `AppBuilderPage`**

Create `shell/src/pages/AppBuilderPage.tsx`:

```tsx
import { useEffect, useMemo, useState } from "react";
import { useAppConfig, useSaveApp } from "../api/hooks";
import type { AppConfig, RenderMode, WidgetItem } from "../api/types";
import { AppRenderer } from "../builder/AppRenderer";
import { WidgetPalette } from "../builder/WidgetPalette";
import { PropsPanel } from "../builder/PropsPanel";
import { registerBuiltinWidgets } from "../builder/widgets";
import { getWidget } from "../builder/registry";
import { Button } from "../ui/button";

registerBuiltinWidgets();

export function AppBuilderPage({ pk }: { pk: string }) {
  const query = useAppConfig(pk);
  const save = useSaveApp(pk);
  const [draft, setDraft] = useState<AppConfig | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [mode, setMode] = useState<RenderMode>("edit");

  useEffect(() => {
    if (query.data) setDraft(query.data);
  }, [query.data]);

  const selected = useMemo(
    () => draft?.layout.items.find((i) => i.id === selectedId) ?? null,
    [draft, selectedId],
  );

  if (query.isLoading || (!draft && !query.isError)) return <p role="status">Chargement…</p>;
  if (query.isError || !draft)
    return <p role="alert" className="text-sm text-red-600">Application introuvable.</p>;

  function addWidget(type: string) {
    const def = getWidget(type);
    if (!def || !draft) return;
    const item: WidgetItem = {
      id: crypto.randomUUID(),
      widget: type,
      x: 0,
      y: 0,
      w: def.defaultSize.w,
      h: def.defaultSize.h,
      props: { ...def.defaultProps },
    };
    setDraft({ ...draft, layout: { ...draft.layout, items: [...draft.layout.items, item] } });
    setSelectedId(item.id);
  }

  function updateSelectedProps(props: Record<string, unknown>) {
    if (!draft || !selectedId) return;
    setDraft({
      ...draft,
      layout: {
        ...draft.layout,
        items: draft.layout.items.map((i) => (i.id === selectedId ? { ...i, props } : i)),
      },
    });
  }

  return (
    <div className="flex h-full flex-col">
      <div className="flex items-center gap-2 border-b p-2">
        <Button size="sm" variant={mode === "edit" ? "default" : "outline"} onClick={() => setMode("edit")}>Édition</Button>
        <Button size="sm" variant={mode === "preview" ? "default" : "outline"} onClick={() => setMode("preview")}>Aperçu</Button>
        <div className="flex-1" />
        <Button size="sm" disabled={save.isPending} onClick={() => save.mutate(draft)}>Enregistrer</Button>
        {save.isError && <span role="alert" className="text-sm text-red-600">Échec de l'enregistrement.</span>}
      </div>
      <div className="flex flex-1 overflow-hidden">
        {mode === "edit" && (
          <aside className="w-48 overflow-auto border-r p-2">
            <p className="mb-1 text-xs font-medium text-slate-500">Widgets</p>
            <WidgetPalette onAdd={addWidget} />
          </aside>
        )}
        <main className="flex-1 overflow-auto p-2">
          <AppRenderer
            config={draft}
            mode={mode}
            onChange={setDraft}
            selectedId={selectedId}
            onSelect={setSelectedId}
          />
        </main>
        {mode === "edit" && (
          <aside className="w-64 overflow-auto border-l p-2">
            <p className="mb-1 text-xs font-medium text-slate-500">Propriétés</p>
            <PropsPanel item={selected} onChange={updateSelectedProps} />
          </aside>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 5: Implement `AppRuntimePage`**

Create `shell/src/pages/AppRuntimePage.tsx`:

```tsx
import { useAppConfig } from "../api/hooks";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";

registerBuiltinWidgets();

export function AppRuntimePage({ pk }: { pk: string }) {
  const query = useAppConfig(pk);
  if (query.isLoading) return <p role="status">Chargement…</p>;
  if (query.isError || !query.data)
    return <p role="alert" className="text-sm text-red-600">Application introuvable.</p>;
  return (
    <div className="h-full w-full">
      <AppRenderer config={query.data} mode="runtime" />
    </div>
  );
}
```

- [ ] **Step 6: Run the AppBuilderPage test**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: PASS.

- [ ] **Step 7: Wire routing + open-from-catalog + NewItemButton**

Edit `shell/src/shell/routes.tsx` — import the pages, route `app`/`dashboard` to the editor, and add both routes:

```tsx
import { AppBuilderPage } from "../pages/AppBuilderPage";
import { AppRuntimePage } from "../pages/AppRuntimePage";
```

In `CatalogRoute`, extend the open logic to route apps/dashboards to the builder (maps still to `/maps/:pk`):

```tsx
      onOpenItem={(pk, type) =>
        navigate(type === "map" ? `/maps/${pk}` : `/apps/${pk}/edit`)
      }
```

Add the routes and an `AppBuilderRoute`/`AppRuntimeRoute`:

```tsx
function AppBuilderRoute() {
  const { pk } = useParams();
  return <AppBuilderPage pk={pk!} />;
}
function AppRuntimeRoute() {
  const { pk } = useParams();
  return <AppRuntimePage pk={pk!} />;
}
```
```tsx
      <Route path="/apps/:pk/edit" element={<AppBuilderRoute />} />
      <Route path="/apps/:pk" element={<AppRuntimeRoute />} />
```

Update `ItemDetailRoute` so the editor button opens the app builder for app/dashboard (keep the map path). Since `ItemDetailPage` already has `onOpenEditor` (SP-0c-e), the route decides the target by item type — pass a handler that navigates to `/apps/:pk/edit` for non-map, `/maps/:pk` for map. Because the route does not know the type, keep it simple: `ItemDetailPage` receives `onOpenEditor` that navigates to `/apps/${pk}/edit`, and `ItemDetailPage` already enables the button only when `resourceType === "map"` — CHANGE that condition to also enable for `app`/`dashboard`, and make the route pass a type-aware navigation. Concretely, in `ItemDetailRoute`:

```tsx
function ItemDetailRoute() {
  const { pk } = useParams();
  const navigate = useNavigate();
  return (
    <ItemDetailPage
      pk={pk!}
      onDeleted={() => navigate("/")}
      onOpenEditor={(type) => navigate(type === "map" ? `/maps/${pk}` : `/apps/${pk}/edit`)}
    />
  );
}
```

Edit `shell/src/pages/ItemDetailPage.tsx`: widen `onOpenEditor` to receive the type and enable the button for `map`, `app`, and `dashboard`:

```tsx
export function ItemDetailPage({ pk, onDeleted, onOpenEditor }: { pk: string; onDeleted?: () => void; onOpenEditor?: (type: string) => void }) {
```
```tsx
      {["map", "app", "dashboard"].includes(item.resourceType) ? (
        <Button className="w-fit" onClick={() => onOpenEditor?.(item.resourceType)}>Ouvrir dans l'éditeur</Button>
      ) : (
        <Button className="w-fit" disabled title="Éditeur indisponible pour ce type">
          Ouvrir dans l'éditeur
        </Button>
      )}
```

Edit `shell/src/shell/NewItemButton.tsx` — for app/dashboard, navigate to the builder:

```tsx
      navigate(kind === "map" ? `/maps/${item.pk}` : `/apps/${item.pk}/edit`);
```

- [ ] **Step 8: Update routes.test for the new wiring**

Edit `shell/src/shell/routes.test.tsx`: mock the new pages to avoid loading heavy deps in jsdom (mirror the existing `MapEditorPage` mock), and add/adjust assertions that `/apps/:pk/edit` renders the builder and `/apps/:pk` renders the runtime. If existing tests asserted the old `onOpenItem` app→`/items/:pk` behavior, update them to the new `/apps/:pk/edit` target.

```tsx
vi.mock("../pages/AppBuilderPage", () => ({ AppBuilderPage: ({ pk }: { pk: string }) => <div>app-builder-{pk}</div> }));
vi.mock("../pages/AppRuntimePage", () => ({ AppRuntimePage: ({ pk }: { pk: string }) => <div>app-runtime-{pk}</div> }));
```

- [ ] **Step 9: Run the full suite + build**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass. Update any existing catalog/detail test that assumed the old app navigation target.

- [ ] **Step 10: Commit**

```bash
git add shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx shell/src/pages/AppRuntimePage.tsx shell/src/pages/ItemDetailPage.tsx shell/src/builder/widgets/index.tsx shell/src/shell/routes.tsx shell/src/shell/routes.test.tsx shell/src/shell/NewItemButton.tsx
git commit -m "feat(shell): add AppBuilderPage + runtime route; open apps in the builder

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: E2E — create app → add widget → save → runtime

**Files:**
- Modify: `shell/e2e/mocks.ts`
- Create: `shell/e2e/app-builder.spec.ts`

**Interfaces:**
- Consumes: `mockGeoNode(page)` harness, `.env.e2e`.
- Produces: an E2E that creates an App, adds a Text widget, edits its text, saves, opens the runtime, and asserts the text renders.

- [ ] **Step 1: Extend the E2E mocks**

Edit `shell/e2e/mocks.ts`. The existing `POST **/configs` app branch returns `itemId:"9"`. Add/extend so the builder flow works for item `9`:
- Ensure `POST **/configs` app branch returns `{ id:"cfg-9", kind:"app", itemId:"9" }` (already does).
- Extend the `**/configs/by-item/**` handler: for `GET` on item `9`, return an app `ConfigRead`:
  `{ id:"cfg-9", itemId:"9", kind:"app", config: { kind:"app", theme:{}, dataSources:[], messages:[], layout:{ type:"grid", breakpoints:{}, items:[] } } }`.
  For `PUT` on item `9`, echo `{ id:"cfg-9", itemId:"9", kind:"app", config: body }`. (Keep the existing item-`77` map branches — branch on the URL's trailing id.)

- [ ] **Step 2: Write the E2E**

Create `shell/e2e/app-builder.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("create an App → add a Text widget → save → runtime shows it", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();

  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add a Text widget from the palette and edit its text.
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Bonjour le monde");
  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Open the runtime and verify the saved text renders.
  await page.goto("/apps/9");
  await expect(page.getByText("Bonjour le monde")).toBeVisible();
});
```

NOTE: the runtime reads the saved config from `GET /configs/by-item/9`. For the assertion to pass offline, extend the mock so that after a `PUT` the subsequent `GET` returns the updated config. Implement this in `mocks.ts` by storing the last PUT body per item id in a closure map and returning it from `GET` (fall back to the empty default when none). Add that stateful behavior in Step 1.

- [ ] **Step 3: Run the new E2E**

Run: `cd shell && npx playwright test app-builder`
Expected: PASS — lands on `/apps/9/edit`, saves, runtime shows "Bonjour le monde".

- [ ] **Step 4: Run the full E2E suite**

Run: `cd shell && npx playwright test`
Expected: all specs pass (catalog + map-editor + app-builder).

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/mocks.ts shell/e2e/app-builder.spec.ts
git commit -m "test(shell): E2E app builder create→add widget→save→runtime

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage (§13 SP-0d.1):** registry + 3 static widgets → Task 2; `AppRenderer` 3 modes → Task 5; `GridCanvas` (grid, select, move) → Task 4; `WidgetHost` isolation → Task 5; `WidgetPalette`/`PropsPanel` → Task 6; `BuilderToolbar`(mode+save) + `AppBuilderPage` @ `/apps/:pk/edit` → Task 7; runtime route `/apps/:pk` → Task 7; `LayoutItem.id` → Task 1; `getAppConfig`/`saveAppConfig` (by-item, PUT from SP-0c-e) → Task 3; open app/dashboard from catalog/detail → Task 7; E2E edit→save→runtime → Task 8. Real drag/resize deferred to E2E (unit covers geometry + keyboard-nudge move), per §9 decision; full drag is a hardening item for a later sub-phase.
- **Placeholder scan:** none — every step carries complete code. Task 8's stateful mock (store-last-PUT) is described precisely (closure map keyed by item id) rather than transcribed because it edits an existing file; the behavior is fully specified.
- **Type consistency:** `WidgetItem`/`AppConfig`/`AppLayout`/`RenderMode` identical across types.ts, registry, GridCanvas, AppRenderer, pages, item-client, hooks; `getWidget`/`listWidgets`/`registerWidget`/`_resetRegistry` stable; `getAppConfig`/`saveAppConfig`/`useAppConfig`/`useSaveApp` signatures match interface/impl/hook/tests; `onOpenEditor(type)` widening is coordinated across ItemDetailPage + routes; `moveItem` used identically in grid tests and AppRenderer.
- **Additive-only:** backend adds `LayoutItem.id` (optional, default None) — existing configs valid; save reuses the SP-0c-e `PUT /configs/by-item/{id}`; no endpoint added.
