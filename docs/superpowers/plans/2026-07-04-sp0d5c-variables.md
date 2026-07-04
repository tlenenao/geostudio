# GeoStudio SP-0d.5c — Variables (état partagé) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to invoke this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an app hold named, shared string variables that actions can write (`variable.set`, wired through the existing `ActionsPanel`) and any widget can read via a `{{var:nom}}` binding — proving the loop with the Texte widget, the same way `{{champ}}` already reads from a bound data source.

**Architecture:** `AppConfig.variables?: Variable[]` is additive. A `VariablesContext` (mirrors `DataContext`'s `DataProvider`/`useDataStates`/`useSetFilter` shape) holds the *live* values in React state, seeded from each variable's `initialValue`; `AppRenderer` wraps its tree in a `VariablesProvider` and, for each variable, mounts a tiny bridge component that registers a `variable.set` bus action keyed by that variable's stable id (`var:<id>`) — so the existing `from`/`event`/`to`/`action` wiring model in `ActionsPanel`/`ActionBus` needs no schema change, only a new kind of `to` target. `WidgetContext` gains `variables?: Record<string, string>` (current values, read-only from a widget's point of view — writing only ever happens through the bus). The Texte widget is the first (and, for this slice, only) consumer: its existing `interpolate()` gains a second, independent token pass for `{{var:nom}}`, run whether or not a data source is bound — the existing `{{champ}}` pass is untouched.

**Tech Stack:** React 19 + TS + Vite 6 + Vitest 3 + Testing Library + Playwright; FastAPI + Pydantic (builder-service). No new dependency.

## Global Constraints

- Additive/back-compatible: `AppConfig.variables?: Variable[]` is optional, mirroring the `AppConfig.pages?: Page[]` precedent from SP-0d.5b — a config that never touches `variables` keeps working exactly as before, both statically (no existing `AppConfig` test literal needs a new field) and at runtime (`config.variables ?? []` resolves to no variables anywhere this plan reads it).
- One rendering engine: variables are seeded and wired identically in `edit`/`preview`/`runtime` — no mode-specific code.
- Front: no new service URL, no new dependency; pure/stateful logic lives in a small `builder/*` module (`VariablesContext.tsx`, mirroring `DataContext.tsx`); panel components own their own add/remove/rename logic directly (mirrors `DataSourcePanel.tsx`/`PageManager.tsx`).
- Commits end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on branch `dev`. Run front-end commands from `shell/` (`cd shell && ...`), backend commands from `builder-service/`.

**Scope note:** Renaming a variable does **not** migrate its live runtime value to the new name — the old name's value (if any was set via the bus during the current session) simply becomes unreachable, and the renamed variable re-seeds from `initialValue` under its new name. This mirrors how `{{champ}}` already breaks if a data source's field is renamed, and is not solved here (documented, not silently dropped). Reading a variable is scoped to the Texte widget only, per this slice's confirmed scope — extending `{{var:nom}}` (or a props-panel picker) to other widgets is the same kind of mechanical, additive follow-up SP-0d.5d documented for theme tokens.

---

### Task 1: Backend — `Variable`/`variables[]` round-trip

**Files:**
- Modify: `builder-service/app/schemas.py`
- Test: `builder-service/tests/test_schemas.py`

**Interfaces:**
- Produces: `class Variable(BaseModel): id: str; name: str; initialValue: str`; `BuilderConfig.variables: list[Variable] = Field(default_factory=list)` — additive, defaults to an empty list, no change to `_require_kind_payload`.

- [ ] **Step 1: Write the failing tests**

Append to `builder-service/tests/test_schemas.py`:

```python
def test_variables_round_trip():
    payload = _valid_payload("app")
    payload["variables"] = [
        {"id": "v1", "name": "message", "initialValue": "salut"},
    ]
    config = BuilderConfig.model_validate(payload)
    assert len(config.variables) == 1
    assert config.variables[0].name == "message"
    dumped = config.model_dump(by_alias=True)
    assert dumped["variables"][0]["initialValue"] == "salut"


def test_variables_optional_defaults_empty():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.variables == []
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd builder-service && python -m pytest tests/test_schemas.py -q`
Expected: FAIL — `variables` is stripped (unknown field) / `AttributeError`.

- [ ] **Step 3: Add the `Variable` model + `BuilderConfig.variables`**

Edit `builder-service/app/schemas.py`. Add a `Variable` class right after `class Page(BaseModel): ...` (before `class Message(BaseModel): ...`):

```python
class Variable(BaseModel):
    id: str
    name: str
    initialValue: str
```

In `class BuilderConfig(BaseModel):`, add the field after `pages`:

```python
    pages: list[Page] = Field(default_factory=list)
    variables: list[Variable] = Field(default_factory=list)
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
git commit -m "feat(builder-service): persist app variables (additive, round-trips)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Front `Variable` type + item-client passthrough + `VariablesContext`

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts` (extend)
- Create: `shell/src/builder/VariablesContext.tsx`
- Test: `shell/src/builder/VariablesContext.test.tsx`

**Interfaces:**
- Produces:
  - `Variable = { id: string; name: string; initialValue: string }`
  - `AppConfig.variables?: Variable[]` (new, optional)
  - `VariablesProvider({ variables: Variable[], children })` — seeds live state from each variable's `initialValue`, and picks up any variable added later (by name) without resetting values already changed at runtime.
  - `useVariables(): Record<string, string>` — the current values, keyed by variable name.
  - `useSetVariable(): (name: string, value: string) => void`.

- [ ] **Step 1: Add the `Variable` type and widen `AppConfig`**

Edit `shell/src/api/types.ts`. Add near `Page`:

```ts
export type Variable = {
  id: string;
  name: string;
  initialValue: string;
};
```

Add `variables?: Variable[];` to `AppConfig`, after `pages?: Page[];`:

```ts
export type AppConfig = {
  kind: "app" | "dashboard";
  theme: Theme;
  dataSources: DataSource[];
  messages: ActionMessage[];
  layout: AppLayout;
  pages?: Page[];
  variables?: Variable[];
};
```

- [ ] **Step 2: Write the failing item-client tests**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("getAppConfig passes through the variables array when present", async () => {
  server.use(
    http.get("https://builder.test/configs/by-item/5", () =>
      HttpResponse.json({
        id: "cfg-5", itemId: "5", kind: "app",
        config: {
          kind: "app", theme: {}, dataSources: [], messages: [],
          layout: { type: "grid", breakpoints: {}, items: [] },
          variables: [{ id: "v1", name: "message", initialValue: "salut" }],
        },
      }),
    ),
  );
  const cfg = await makeClient().getAppConfig("5");
  expect(cfg.variables).toEqual([{ id: "v1", name: "message", initialValue: "salut" }]);
});

test("saveAppConfig PUTs the variables array when present", async () => {
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
    variables: [{ id: "v1", name: "message", initialValue: "salut" }],
  });
  expect(body.variables).toHaveLength(1);
  expect(body.variables[0].name).toBe("message");
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `variables` is dropped by both `getAppConfig` and `saveAppConfig`.

- [ ] **Step 4: Thread `variables` through `getAppConfig`/`saveAppConfig`**

Edit `shell/src/api/itemClient.ts`. Add `Variable` to the type import from `./types`. In `getAppConfig`, add `variables?: Variable[];` to the local raw-response shape (after `pages?: Page[];`), and add `variables: c.variables,` to the returned object (after `pages: c.pages,`):

```ts
      const data = (await res.json()) as {
        config?: {
          kind?: "app" | "dashboard";
          theme?: Theme;
          dataSources?: DataSource[];
          messages?: ActionMessage[];
          pages?: Page[];
          variables?: Variable[];
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
        variables: c.variables,
        layout: c.layout,
      };
```

In `saveAppConfig`, add `variables: config.variables,` to the PUT body (after `pages: config.pages,`):

```ts
        body: JSON.stringify({
          version: 1,
          kind: config.kind,
          theme: config.theme,
          dataSources: config.dataSources,
          messages: config.messages,
          pages: config.pages,
          variables: config.variables,
          layout: config.layout,
        }),
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (existing `getAppConfig`/`saveAppConfig` tests, which never set `variables`, still pass — `config.variables` is `undefined`, `JSON.stringify` drops the key, the backend's `Field(default_factory=list)` fills `[]`).

- [ ] **Step 6: Write the failing `VariablesContext` tests**

Create `shell/src/builder/VariablesContext.test.tsx`:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import type { Variable } from "../api/types";
import { VariablesProvider, useVariables, useSetVariable } from "./VariablesContext";

function Probe() {
  const values = useVariables();
  const setVariable = useSetVariable();
  return (
    <div>
      <p>message:{values.message ?? "unset"}</p>
      <p>count:{values.count ?? "unset"}</p>
      <button onClick={() => setVariable("message", "hello")}>set</button>
    </div>
  );
}

test("seeds values from each variable's initialValue", () => {
  const variables: Variable[] = [{ id: "v1", name: "message", initialValue: "salut" }];
  render(<VariablesProvider variables={variables}><Probe /></VariablesProvider>);
  expect(screen.getByText("message:salut")).toBeInTheDocument();
});

test("useSetVariable updates the value read by useVariables", async () => {
  const variables: Variable[] = [{ id: "v1", name: "message", initialValue: "" }];
  render(<VariablesProvider variables={variables}><Probe /></VariablesProvider>);
  await userEvent.click(screen.getByRole("button", { name: "set" }));
  expect(screen.getByText("message:hello")).toBeInTheDocument();
});

test("picks up a variable added after the provider first mounted", async () => {
  const variables: Variable[] = [{ id: "v1", name: "message", initialValue: "salut" }];
  const { rerender } = render(<VariablesProvider variables={variables}><Probe /></VariablesProvider>);
  const next: Variable[] = [...variables, { id: "v2", name: "count", initialValue: "0" }];
  rerender(<VariablesProvider variables={next}><Probe /></VariablesProvider>);
  await waitFor(() => expect(screen.getByText("count:0")).toBeInTheDocument());
  expect(screen.getByText("message:salut")).toBeInTheDocument(); // untouched
});
```

- [ ] **Step 7: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/VariablesContext.test.tsx`
Expected: FAIL — module `./VariablesContext` does not exist.

- [ ] **Step 8: Implement `VariablesContext.tsx`**

Create `shell/src/builder/VariablesContext.tsx`:

```tsx
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import type { Variable } from "../api/types";

type SetVariable = (name: string, value: string) => void;

const VariablesContext = createContext<Record<string, string>>({});
const SetVariableContext = createContext<SetVariable>(() => {});

export function VariablesProvider({ variables, children }: { variables: Variable[]; children: ReactNode }) {
  const [values, setValues] = useState<Record<string, string>>(() => {
    const initial: Record<string, string> = {};
    for (const v of variables) initial[v.name] = v.initialValue;
    return initial;
  });

  // Pick up a variable added after this provider mounted (e.g. the editor's
  // VariablesPanel adding one live) without resetting values already
  // changed at runtime for variables that already existed.
  useEffect(() => {
    setValues((prev) => {
      let changed = false;
      const next = { ...prev };
      for (const v of variables) {
        if (!(v.name in next)) {
          next[v.name] = v.initialValue;
          changed = true;
        }
      }
      return changed ? next : prev;
    });
  }, [variables]);

  function setVariable(name: string, value: string) {
    setValues((prev) => ({ ...prev, [name]: value }));
  }

  return (
    <SetVariableContext.Provider value={setVariable}>
      <VariablesContext.Provider value={values}>{children}</VariablesContext.Provider>
    </SetVariableContext.Provider>
  );
}

export function useVariables(): Record<string, string> {
  return useContext(VariablesContext);
}

export function useSetVariable(): SetVariable {
  return useContext(SetVariableContext);
}
```

- [ ] **Step 9: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/VariablesContext.test.tsx`
Expected: PASS (3/3).

- [ ] **Step 10: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/builder/VariablesContext.tsx shell/src/builder/VariablesContext.test.tsx
git commit -m "feat(shell): Variable type + VariablesContext (seed from initialValue, live set/read)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `AppRenderer` wires variables into the bus and widget context; Texte reads `{{var:nom}}`

**Files:**
- Modify: `shell/src/builder/registry.ts`
- Modify: `shell/src/builder/WidgetHost.tsx`
- Modify: `shell/src/builder/AppRenderer.tsx`
- Modify: `shell/src/builder/widgets/index.tsx`
- Test: `shell/src/builder/AppRenderer.test.tsx` (extend), `shell/src/builder/widgets/text.test.tsx` (extend)

**Interfaces:**
- Consumes: `VariablesProvider`/`useVariables`/`useSetVariable` (Task 2), `useBusAction` (existing, from `ActionBusContext`).
- Produces:
  - `WidgetContext` gains `variables?: Record<string, string>` (import `Variable` is not needed here — this field is a plain value map, not a `Variable[]`).
  - `WidgetHost` reads `useVariables()` and forwards it into `ctx`.
  - `AppRenderer` wraps its tree in `VariablesProvider`, and for each `config.variables` entry mounts a bridge that registers a `set` bus action on the synthetic target id `var:<variable.id>` — this is what lets `ActionsPanel` (Task 4) wire an emitter's event straight to "Variable : X".set using the *existing* `ActionMessage{from,event,to,action}` shape, no schema change.
  - Texte's `Component` resolves `{{var:nom}}` from `ctx.variables`, independent of whether a data source is bound; `{{champ}}` (record-field) resolution is unchanged.

- [ ] **Step 1: Widen `WidgetContext`**

Edit `shell/src/builder/registry.ts`. Add a field (it already declares `pages?`/`navigate?`/`data?`/`bus?`/`widgetId?`):

```ts
export type WidgetContext = {
  mode: RenderMode;
  navigate?: (pageId: string) => void;
  pages?: Page[];
  variables?: Record<string, string>;
  data?: DataSourceState;
  bus?: ActionBus;
  widgetId?: string;
};
```

- [ ] **Step 2: Thread `variables` through `WidgetHost`**

Edit `shell/src/builder/WidgetHost.tsx`. Add the import:

```tsx
import { useVariables } from "./VariablesContext";
```

Add the hook call and forward it into `ctx`:

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
  const variables = useVariables();
  const dsId = item.props.dataSourceId as string | undefined;
  const data = dsId ? states[dsId] : undefined;
  const def = getWidget(item.widget);
  if (!def) {
    return <div className="flex h-full items-center justify-center bg-slate-100 text-xs text-slate-400">Widget inconnu : {item.widget}</div>;
  }
  const Widget = def.Component;
  return (
    <WidgetErrorBoundary>
      <Widget props={item.props} ctx={{ mode, data, bus: bus ?? undefined, widgetId: item.id, pages, navigate, variables }} />
    </WidgetErrorBoundary>
  );
}
```

(`useVariables()` defaults to `{}` when no `VariablesProvider` ancestor exists — safe for `WidgetHost.test.tsx`'s existing bare-render tests, exactly like `useDataStates()`/`useActionBus()` already are.)

- [ ] **Step 3: Write the failing `AppRenderer`/Texte tests**

Append to `shell/src/builder/AppRenderer.test.tsx`:

```tsx
test("threads variables into widget context, seeded from their initialValue", () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "message", initialValue: "salut" }],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "{{var:message}}" } },
    ] },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  expect(screen.getByText("salut")).toBeInTheDocument();
});

test("a variable.set action updates the value read by a Texte widget", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "message", initialValue: "" }],
    messages: [{ id: "m1", from: "flt1", event: "changed", to: "var:v1", action: "set" }],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "flt1", widget: "filter", x: 0, y: 0, w: 3, h: 1, props: { field: "message", label: "Message" } },
      { id: "t1", widget: "text", x: 0, y: 1, w: 4, h: 2, props: { text: "{{var:message}}" } },
    ] },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "hello");
  expect(await screen.findByText("hello")).toBeInTheDocument();
});
```

Append to `shell/src/builder/widgets/text.test.tsx`:

```tsx
test("text resolves {{var:nom}} directly from ctx.variables, independent of a bound source", () => {
  const Text = getWidget("text")!.Component;
  render(
    <Text props={{ text: "Valeur : {{var:message}}" }} ctx={{ mode: "runtime", variables: { message: "salut" } } as WidgetContext} />,
  );
  expect(screen.getByText("Valeur : salut")).toBeInTheDocument();
});
```

- [ ] **Step 4: Run to verify they fail**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx src/builder/widgets/text.test.tsx`
Expected: FAIL — `AppRenderer` doesn't wire variables yet; Texte doesn't resolve `{{var:...}}`.

- [ ] **Step 5: Wire `VariablesProvider` and the per-variable bus bridge in `AppRenderer`**

Edit `shell/src/builder/AppRenderer.tsx`. Add `Variable` to the type import and add the two new imports:

```tsx
import type { AppConfig, RenderMode, Variable } from "../api/types";
```

```tsx
import { VariablesProvider, useSetVariable } from "./VariablesContext";
import { useBusAction } from "./ActionBusContext";
```

Add this helper and component above the `AppRenderer` function:

```tsx
// A message's payload is whatever shape its emitter chose (Button emits
// {widgetId}, Filtre emits {[field]: value}, …). If the payload is an
// object carrying a key matching this variable's own name — e.g. a Filtre
// configured with field === the variable's name — use that value; any
// other payload shape (or a bare primitive) is stringified as-is.
function valueFromPayload(payload: unknown, name: string): string {
  if (payload && typeof payload === "object" && name in (payload as Record<string, unknown>)) {
    const v = (payload as Record<string, unknown>)[name];
    return v === null || v === undefined ? "" : String(v);
  }
  return payload === null || payload === undefined ? "" : String(payload);
}

function VariableBusBridge({ variable, bus }: { variable: Variable; bus: ActionBus }) {
  const setVariable = useSetVariable();
  useBusAction(bus, `var:${variable.id}`, "set", (payload) => {
    setVariable(variable.name, valueFromPayload(payload, variable.name));
  });
  return null;
}
```

Change the return statement from:

```tsx
  return (
    <div ref={containerRef} className="h-full w-full bg-[var(--gs-color-background)] font-[var(--gs-font)]" style={themeToCssVars(config.theme)}>
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
```

to:

```tsx
  return (
    <div ref={containerRef} className="h-full w-full bg-[var(--gs-color-background)] font-[var(--gs-font)]" style={themeToCssVars(config.theme)}>
      <ActionBusProvider bus={bus}>
        <VariablesProvider variables={config.variables ?? []}>
          {(config.variables ?? []).map((v) => (
            <VariableBusBridge key={v.id} variable={v} bus={bus} />
          ))}
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
        </VariablesProvider>
      </ActionBusProvider>
    </div>
  );
```

- [ ] **Step 6: Make Texte resolve `{{var:nom}}`**

Edit `shell/src/builder/widgets/index.tsx`. Change the `interpolate` function from:

```ts
// Replace {{champ}} tokens with the record's property values (empty if absent).
function interpolate(text: string, record: DataRecord | undefined): string {
  if (!record) return text;
  return text.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, key: string) => {
    const v = record.properties[key];
    return v === null || v === undefined ? "" : String(v);
  });
}
```

to:

```ts
// Replaces {{var:nom}} tokens from ctx.variables (always, regardless of any
// bound source), then {{champ}} tokens from the record's properties (only
// when a source is bound — an unbound Texte still shows {{champ}} verbatim).
function interpolate(text: string, record: DataRecord | undefined, variables: Record<string, string>): string {
  let out = text.replace(/\{\{\s*var:([\w.]+)\s*\}\}/g, (_, name: string) => variables[name] ?? "");
  if (record) {
    out = out.replace(/\{\{\s*([\w.]+)\s*\}\}/g, (_, key: string) => {
      const v = record.properties[key];
      return v === null || v === undefined ? "" : String(v);
    });
  }
  return out;
}
```

Change the `text` widget's `Component` and its `PropsPanel` hint from:

```tsx
        <p className="text-[10px] text-slate-400">Utilisez {"{{champ}}"} pour insérer une valeur de la source liée.</p>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const raw = String(props.text ?? "");
      const text = ctx.data ? interpolate(raw, ctx.data.records[0]) : raw;
      return <p className="whitespace-pre-wrap text-[var(--gs-color-text)]">{text}</p>;
    },
```

to:

```tsx
        <p className="text-[10px] text-slate-400">Utilisez {"{{champ}}"} pour insérer une valeur de la source liée, ou {"{{var:nom}}"} pour une variable.</p>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const raw = String(props.text ?? "");
      const text = interpolate(raw, ctx.data?.records[0], ctx.variables ?? {});
      return <p className="whitespace-pre-wrap text-[var(--gs-color-text)]">{text}</p>;
    },
```

- [ ] **Step 7: Run to verify they pass**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx src/builder/widgets/text.test.tsx`
Expected: PASS. The pre-existing `"text renders verbatim when unbound"` test still passes: `interpolate("Bonjour {{nom}}", undefined, {})` runs the `var:` pass first (no match, `text` unchanged), then skips the record pass entirely (`record` is `undefined`) — `{{nom}}` stays literal, exactly as before.

- [ ] **Step 8: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/registry.ts shell/src/builder/WidgetHost.tsx shell/src/builder/AppRenderer.tsx shell/src/builder/AppRenderer.test.tsx shell/src/builder/widgets/index.tsx shell/src/builder/widgets/text.test.tsx
git commit -m "feat(shell): AppRenderer wires variable.set bus actions; Texte reads {{var:nom}}

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `VariablesPanel` + `ActionsPanel` gains variable targets + `AppBuilderPage` integration

**Files:**
- Create: `shell/src/builder/VariablesPanel.tsx`
- Test: `shell/src/builder/VariablesPanel.test.tsx`
- Modify: `shell/src/builder/ActionsPanel.tsx`
- Test: `shell/src/builder/ActionsPanel.test.tsx` (extend)
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Test: `shell/src/pages/AppBuilderPage.test.tsx` (extend)

**Interfaces:**
- Consumes: `Variable` (Task 2); `AppRenderer`'s `var:<id>`/`set` bus target (Task 3).
- Produces:
  - `VariablesPanel({ variables: Variable[], onChange: (variables: Variable[]) => void })` — add/rename/remove, `id`-keyed controls (`aria-label={`... la variable ${v.id}`}`), plus an "initial value" input per variable.
  - `ActionsPanel` gains an optional `variables?: Variable[]` prop (default `[]`); the "Widget cible" select also lists each variable as `Variable : <name>` (value `var:<id>`), whose only action is `set`.
  - `AppBuilderPage` renders `VariablesPanel` in the left rail and passes `draft.variables ?? []` into both `VariablesPanel` and `ActionsPanel`.

**Note on `ActionsPanel.tsx`'s current state:** if the separate "SP-0d.5 tech-debt cleanup" plan's Task 2 has already been applied to this branch, `ActionsPanel.tsx` already has an `isOnThisPage(items, id)` helper and a `visibleMessages` filter (added there to hide cross-page messages). Step 3 below shows the exact edit for **both** cases — read the current file first and apply whichever block matches what you find.

- [ ] **Step 1: Write the failing `VariablesPanel` tests**

Create `shell/src/builder/VariablesPanel.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { Variable } from "../api/types";
import { VariablesPanel } from "./VariablesPanel";

test("adds a variable with an empty initial value", async () => {
  const onChange = vi.fn();
  render(<VariablesPanel variables={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une variable" }));
  const next = onChange.mock.calls[0][0] as Variable[];
  expect(next).toHaveLength(1);
  expect(next[0].name).toBe("Variable 1");
  expect(next[0].initialValue).toBe("");
});

test("renames a variable", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "", initialValue: "" }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Renommer la variable v1"), "message");
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(next[0].name).toBe("message");
});

test("edits a variable's initial value", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "message", initialValue: "" }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Valeur initiale de la variable v1"), "salut");
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(next[0].initialValue).toBe("salut");
});

test("removes a variable", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "message", initialValue: "" }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Retirer la variable v1" }));
  expect(onChange).toHaveBeenCalledWith([]);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/VariablesPanel.test.tsx`
Expected: FAIL — module missing.

- [ ] **Step 3: Implement `VariablesPanel`**

Create `shell/src/builder/VariablesPanel.tsx`:

```tsx
import type { Variable } from "../api/types";

export function VariablesPanel({
  variables,
  onChange,
}: {
  variables: Variable[];
  onChange: (variables: Variable[]) => void;
}) {
  function addVariable() {
    const v: Variable = { id: crypto.randomUUID(), name: `Variable ${variables.length + 1}`, initialValue: "" };
    onChange([...variables, v]);
  }
  function remove(id: string) {
    onChange(variables.filter((v) => v.id !== id));
  }
  function rename(id: string, name: string) {
    onChange(variables.map((v) => (v.id === id ? { ...v, name } : v)));
  }
  function setInitialValue(id: string, initialValue: string) {
    onChange(variables.map((v) => (v.id === id ? { ...v, initialValue } : v)));
  }
  return (
    <ul className="flex flex-col gap-1">
      {variables.map((v) => (
        <li key={v.id} className="flex items-center gap-1 rounded border border-slate-200 p-1 text-xs">
          <input
            aria-label={`Renommer la variable ${v.id}`}
            className="w-16 rounded border border-slate-300 px-1"
            value={v.name}
            onChange={(e) => rename(v.id, e.target.value)}
          />
          <input
            aria-label={`Valeur initiale de la variable ${v.id}`}
            className="w-16 rounded border border-slate-300 px-1"
            value={v.initialValue}
            onChange={(e) => setInitialValue(v.id, e.target.value)}
          />
          <button type="button" aria-label={`Retirer la variable ${v.id}`} className="text-red-600" onClick={() => remove(v.id)}>✕</button>
        </li>
      ))}
      <li>
        <button type="button" className="rounded border border-slate-300 px-2 py-1 hover:bg-slate-100" onClick={addVariable}>
          Ajouter une variable
        </button>
      </li>
    </ul>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/VariablesPanel.test.tsx`
Expected: PASS (4/4).

- [ ] **Step 5: Extend `ActionsPanel` with variable targets**

Read `shell/src/builder/ActionsPanel.tsx` first, then apply whichever of the two edits below matches its current content.

**If the file still looks like the original (no `isOnThisPage`/`visibleMessages` — the SP-0d.5 tech-debt cleanup plan's Task 2 hasn't run yet on this branch), replace the whole file with:**

```tsx
import { useState } from "react";
import type { ActionMessage, Variable, WidgetItem } from "../api/types";
import { getWidget } from "./registry";

function widgetLabel(items: WidgetItem[], variables: Variable[], id: string): string {
  if (id.startsWith("var:")) {
    const v = variables.find((v) => `var:${v.id}` === id);
    return v ? `Variable : ${v.name}` : id;
  }
  const it = items.find((i) => i.id === id);
  return (it && getWidget(it.widget)?.label) || id;
}
function eventsOf(items: WidgetItem[], id: string): readonly string[] {
  return getWidget(items.find((i) => i.id === id)?.widget ?? "")?.events ?? [];
}
function actionsOf(items: WidgetItem[], id: string): readonly string[] {
  if (id.startsWith("var:")) return ["set"];
  return getWidget(items.find((i) => i.id === id)?.widget ?? "")?.actions ?? [];
}
function resolvesOnThisPage(items: WidgetItem[], variables: Variable[], id: string): boolean {
  if (id.startsWith("var:")) return variables.some((v) => `var:${v.id}` === id);
  return items.some((i) => i.id === id);
}

const selectCls = "h-8 rounded border border-slate-300 bg-white text-xs";

export function ActionsPanel({
  items,
  variables = [],
  messages,
  onChange,
}: {
  items: WidgetItem[];
  variables?: Variable[];
  messages: ActionMessage[];
  onChange: (messages: ActionMessage[]) => void;
}) {
  const emitters = items.filter((i) => (getWidget(i.widget)?.events?.length ?? 0) > 0);
  const widgetReceivers = items.filter((i) => (getWidget(i.widget)?.actions?.length ?? 0) > 0);
  const variableReceivers = variables.map((v) => ({ id: `var:${v.id}`, label: `Variable : ${v.name}` }));
  const [from, setFrom] = useState("");
  const [event, setEvent] = useState("");
  const [to, setTo] = useState("");
  const [action, setAction] = useState("");

  const visibleMessages = messages.filter(
    (m) => resolvesOnThisPage(items, variables, m.from) && resolvesOnThisPage(items, variables, m.to),
  );

  function add() {
    if (!from || !event || !to || !action) return;
    onChange([...messages, { id: crypto.randomUUID(), from, event, to, action }]);
    setFrom(""); setEvent(""); setTo(""); setAction("");
  }
  function remove(id: string) {
    onChange(messages.filter((m) => m.id !== id));
  }

  return (
    <div className="flex flex-col gap-2 text-sm">
      <ul className="flex flex-col gap-1">
        {visibleMessages.map((m) => (
          <li key={m.id} className="flex items-center justify-between rounded border border-slate-200 p-1 text-xs">
            <span>{widgetLabel(items, variables, m.from)}.{m.event} → {widgetLabel(items, variables, m.to)}.{m.action}</span>
            <button type="button" aria-label={`Retirer l'action ${m.id}`} className="text-red-600" onClick={() => remove(m.id)}>✕</button>
          </li>
        ))}
        {visibleMessages.length === 0 && <li className="text-xs text-slate-400">Aucune action.</li>}
      </ul>
      <select aria-label="Widget émetteur" className={selectCls} value={from}
        onChange={(e) => { setFrom(e.target.value); setEvent(""); }}>
        <option value="">Widget émetteur…</option>
        {emitters.map((i) => <option key={i.id} value={i.id}>{widgetLabel(items, variables, i.id)}</option>)}
      </select>
      <select aria-label="Événement" className={selectCls} value={event} disabled={!from}
        onChange={(e) => setEvent(e.target.value)}>
        <option value="">Événement…</option>
        {eventsOf(items, from).map((ev) => <option key={ev} value={ev}>{ev}</option>)}
      </select>
      <select aria-label="Widget cible" className={selectCls} value={to}
        onChange={(e) => { setTo(e.target.value); setAction(""); }}>
        <option value="">Widget cible…</option>
        {widgetReceivers.map((i) => <option key={i.id} value={i.id}>{widgetLabel(items, variables, i.id)}</option>)}
        {variableReceivers.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
      </select>
      <select aria-label="Action" className={selectCls} value={action} disabled={!to}
        onChange={(e) => setAction(e.target.value)}>
        <option value="">Action…</option>
        {actionsOf(items, to).map((a) => <option key={a} value={a}>{a}</option>)}
      </select>
      <button type="button" className="rounded border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100" onClick={add}>
        Ajouter une action
      </button>
    </div>
  );
}
```

**If the tech-debt cleanup plan's Task 2 already ran** (the file already has `isOnThisPage(items: WidgetItem[], id: string)` and filters the rendered list through `visibleMessages`), apply these narrower edits instead of a full replace:
1. Add `Variable` to the type import from `./types`.
2. Widen `widgetLabel`/`actionsOf`/`isOnThisPage` to take a `variables: Variable[]` parameter and handle `id.startsWith("var:")` first (returning `Variable : <name>` / `["set"]` / membership-in-`variables` respectively — same bodies as the `widgetLabel`/`actionsOf`/`resolvesOnThisPage` functions shown in the full-file version above; keep the existing function name `isOnThisPage` rather than renaming it to `resolvesOnThisPage`).
3. Add the `variables?: Variable[]` prop (default `[]`) to `ActionsPanel`'s props type.
4. Add `variableReceivers` (as shown above) and append it to the "Widget cible" `<select>`'s options, after `widgetReceivers`.
5. Pass `variables` into every call to `widgetLabel`/`actionsOf`/`isOnThisPage` that the existing code already makes.

Either way, the resulting behavior and test surface are identical.

- [ ] **Step 6: Write the failing `ActionsPanel` test**

Append to `shell/src/builder/ActionsPanel.test.tsx`:

```tsx
test("wires an emitter to a variable's set action", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "message", initialValue: "" }];
  render(<ActionsPanel items={items} variables={variables} messages={[]} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Widget émetteur"), "f1");
  await userEvent.selectOptions(screen.getByLabelText("Événement"), "changed");
  await userEvent.selectOptions(screen.getByLabelText("Widget cible"), "var:v1");
  await userEvent.selectOptions(screen.getByLabelText("Action"), "set");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une action" }));
  const next = onChange.mock.calls.at(-1)![0] as ActionMessage[];
  expect(next).toHaveLength(1);
  expect(next[0]).toMatchObject({ from: "f1", event: "changed", to: "var:v1", action: "set" });
});
```

(Add `Variable` to this test file's existing `import type { ActionMessage, WidgetItem } from "../api/types";` line.)

- [ ] **Step 7: Run to verify it fails, then passes**

Run: `cd shell && npx vitest run src/builder/ActionsPanel.test.tsx`
Expected: FAIL first (no "Variable : message" target exists), then PASS after Step 5's edit (3/3 — the two pre-existing tests are unaffected since neither passes a `variables` prop, which defaults to `[]`).

- [ ] **Step 8: Wire `VariablesPanel` into `AppBuilderPage`**

Edit `shell/src/pages/AppBuilderPage.tsx`. Add the import:

```tsx
import { VariablesPanel } from "../builder/VariablesPanel";
```

Add a `setVariables` helper next to `setPages`:

```tsx
  const setVariables = (variables: typeof draft.variables) =>
    setDraft((d) => (d ? { ...d, variables } : d));
```

Change the "Actions" section to pass `variables` into `ActionsPanel`, and add a "Variables" section right after it, before "Thème":

```tsx
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Actions</p>
            <ActionsPanel items={activeLayout.items} variables={draft.variables ?? []} messages={draft.messages} onChange={setMessages} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Variables</p>
            <VariablesPanel variables={draft.variables ?? []} onChange={setVariables} />
            <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Thème</p>
            <ThemePanel theme={draft.theme} onChange={setTheme} />
```

- [ ] **Step 9: Extend the `AppBuilderPage` test**

Append to `shell/src/pages/AppBuilderPage.test.tsx`:

```tsx
test("adds a variable and wires a Filtre action to it, then persists both", async () => {
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue(config),
    saveAppConfig,
    featuresUrl: vi.fn().mockReturnValue(""),
    queryDataSource: vi.fn().mockResolvedValue([]),
  });
  await screen.findByRole("button", { name: "Ajouter une variable" });
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une variable" }));
  await userEvent.click(screen.getByRole("button", { name: "Filtre" }));

  const emitterSelect = screen.getByLabelText("Widget émetteur");
  const targetSelect = screen.getByLabelText("Widget cible");
  await userEvent.selectOptions(emitterSelect, within(emitterSelect).getByRole("option", { name: "Filtre" }));
  await userEvent.selectOptions(screen.getByLabelText("Événement"), "changed");
  await userEvent.selectOptions(targetSelect, within(targetSelect).getByRole("option", { name: "Variable : Variable 1" }));
  await userEvent.selectOptions(screen.getByLabelText("Action"), "set");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une action" }));

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1];
  expect(saved.variables).toHaveLength(1);
  expect(saved.messages).toHaveLength(1);
  expect(saved.messages[0]).toMatchObject({ event: "changed", action: "set", to: `var:${saved.variables[0].id}` });
});
```

- [ ] **Step 10: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/VariablesPanel.test.tsx src/builder/ActionsPanel.test.tsx src/pages/AppBuilderPage.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/VariablesPanel.tsx shell/src/builder/VariablesPanel.test.tsx shell/src/builder/ActionsPanel.tsx shell/src/builder/ActionsPanel.test.tsx shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
git commit -m "feat(shell): add VariablesPanel; ActionsPanel can target a variable's set action

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: E2E — a Filtre wired to a variable updates a Texte widget, in the runtime

**Files:**
- Create: `shell/e2e/variables.spec.ts`

**Interfaces:**
- Consumes: the stateful by-item mock store + `mockGeoNode` (existing — the generic PUT-echo already round-trips `variables`, no mock change needed), `VariablesPanel`, the extended `ActionsPanel`, the Filtre/Texte widgets.
- Produces: an E2E that creates an app, adds a Filtre (configured to filter on field `"message"`) and a Texte (bound to `{{var:message}}`), adds a variable named `"message"`, wires Filtre.changed → that variable's `set` action, saves, opens the runtime, types into the Filtre, and confirms the Texte widget shows the typed value.

- [ ] **Step 1: Write the E2E**

Create `shell/e2e/variables.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("a Filtre wired to a variable updates a Texte widget reading it, in the runtime", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App variables");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add the Filtre (emitter) and Texte (reader) widgets.
  await page.getByRole("button", { name: "Filtre" }).click();
  await page.getByLabel("Champ à filtrer").fill("message");
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Valeur : {{var:message}}");

  // Add a variable and name it "message".
  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("message");

  // Wire Filtre.changed -> Variable(message).set.
  await page.getByLabel("Widget émetteur").selectOption({ label: "Filtre" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : message" });
  await page.getByLabel("Action").selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime: typing into the Filtre updates the Texte widget's {{var:message}} binding.
  await page.goto("/apps/9");
  await page.getByLabel("Valeur du filtre").fill("bonjour");
  await expect(page.getByText("Valeur : bonjour")).toBeVisible();
});
```

- [ ] **Step 2: Run the new E2E**

Run: `cd shell && npx playwright test variables`
Expected: PASS — the Texte widget shows "Valeur : bonjour" after typing into the Filtre in the runtime.

- [ ] **Step 3: Run the full E2E suite**

Run: `cd shell && npx playwright test`
Expected: all specs pass (catalog + map-editor + app-builder + data-widget + actions + chart + responsive + theme + pages-navigation + variables, plus `templates.spec.ts`/`tech-debt`-related specs if those plans have already run).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/variables.spec.ts
git commit -m "test(shell): E2E a Filtre wired to a variable updates a Texte widget in the runtime

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage (design 0d.5 §5 « Variables »):** `variables[]` additive backend + front type → Tasks 1–2. Shared state readable/writable by actions (`variable.set`) → Tasks 2–3 (`VariablesContext` + the per-variable bus bridge). Editor panel to manage variables → Task 4 (`VariablesPanel`). Reading a variable from a widget → Task 3 (Texte's `{{var:nom}}`, the confirmed scope for this slice). End-to-end proof (Filtre → variable.set → Texte re-renders in the runtime) → Task 5.
- **Placeholder scan:** none — every step carries complete code or an exact edit against a quoted anchor; the one place with a real ambiguity (Task 4's `ActionsPanel.tsx`, which may already be mid-edited by another plan) gets two explicit, complete alternatives rather than a vague "adjust as needed."
- **Type consistency:** `Variable = { id, name, initialValue }` defined once in `api/types.ts`, consumed identically by `VariablesContext.tsx` (seeding/reading by `name`), `AppRenderer` (`config.variables`, `VariableBusBridge`), `WidgetContext.variables`, `VariablesPanel`, `ActionsPanel`, and `AppBuilderPage`. The synthetic bus target `var:<id>` is constructed and parsed identically in exactly two places: `AppRenderer`'s `VariableBusBridge` (registers it) and `ActionsPanel` (offers it as a "Widget cible" option and renders its label) — no third place reimplements the `var:` prefix convention.
- **Backward compatibility:** `AppConfig.variables?` is optional, mirroring the `pages?`/`layouts?` precedents — every existing `AppConfig` fixture (which never sets `variables`) resolves to `config.variables ?? []` everywhere this plan reads it, and to `undefined` on the wire (dropped by `JSON.stringify`, refilled as `[]` by the backend's `Field(default_factory=list)`). The one call site touched outside this plan's own new code — Texte's `interpolate()` — is proven not to regress the pre-existing "renders verbatim when unbound" behavior (Task 3 Step 7's note).
- **Façade discipline:** no new network access; `variables` flows through the existing `getAppConfig`/`saveAppConfig` façade methods, extended the same way `theme`/`messages`/`pages` were in earlier phases.
- **Engine unity:** `AppRenderer` seeds and wires variables identically in `edit`/`preview`/`runtime` — there is no mode-specific variables code anywhere in this plan.
- **Cross-plan overlap:** Task 4 explicitly names and resolves its one real file-level dependency on the separate SP-0d.5 tech-debt cleanup plan (both touch `ActionsPanel.tsx`'s message-filtering logic) — the task is correct and self-sufficient regardless of which plan runs first.
- **Backend:** confirmed no other change needed — `builder-service/app/schemas.py`'s `BuilderConfig.variables: list[Variable]` (Task 1) is an unconstrained additive list, and no validator references it.
