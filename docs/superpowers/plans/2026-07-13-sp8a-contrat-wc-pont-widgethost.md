# SP-8a — Contrat Web Component + pont WidgetHost : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Un widget peut être écrit comme un Web Component standard (custom
element + manifeste JSON typé) plutôt qu'en React, et se comporte comme un
widget interne dans le builder GeoStudio (palette, panneau de props, thème,
data source, events, actions composées) — sans toucher au renderer, à la
palette ou au panneau de props existants.

**Architecture:** Un manifeste (`WcWidgetManifest`) décrit un widget WC
(tag, props typées, events, actions, taille par défaut). Un adaptateur
`registerWcWidget(manifest)` construit un `WidgetDefinition` standard
(même forme que les widgets React existants) et l'enregistre via le
`registerWidget` déjà en place — donc `WidgetPalette`, `PropsPanel.tsx`,
`ActionsPanel.tsx`, `WidgetHost.tsx` fonctionnent sans modification. Le
`Component` généré (`WcHost`) monte l'élément custom via
`document.createElement`, lui assigne `props`/`data`/`user`/`navigate`
comme propriétés DOM (jamais d'attributs sérialisés), relaie ses
`CustomEvent` vers l'`ActionBus`, et invoque ses méthodes publiques quand
le bus déclenche une de ses actions déclarées. Le thème passe par les CSS
custom properties déjà posées sur le conteneur racine (héritées nativement
à travers le DOM, shadow DOM inclus — rien à construire). Le widget
`Compteur` est réimplémenté en Lit comme preuve du pont, à côté de
l'original React (les deux coexistent).

**Tech Stack:** React 19 + TypeScript (shell existant), Lit 3 (nouvelle
dépendance, widgets WC), Vitest + Testing Library (tests unitaires),
Playwright (E2E).

## Global Constraints

- Aucune modification de `registry.ts`, `WidgetHost.tsx`, `PropsPanel.tsx`,
  `ActionsPanel.tsx`, `WidgetPalette.tsx` — le pont est entièrement contenu
  dans `shell/src/builder/wc/`.
- Props/data/user/navigate passés à l'élément custom **comme propriétés
  DOM**, jamais comme attributs HTML sérialisés.
- Events widget → host : `CustomEvent` natif dispatché par l'élément sur
  lui-même, un nom par entrée de `manifest.events`.
- Actions host → widget : le bus invoque une méthode publique du même nom
  que l'action sur l'instance de l'élément (`el.reset(payload)`).
- Le `Compteur` React existant (`counterWidget.tsx`, type
  `"example.counter"`) n'est ni supprimé ni modifié — le `Compteur` WC est
  un widget distinct (type `"example.counter-wc"`) enregistré en plus.
- Types de props supportés en v1 : `string | number | boolean` (YAGNI —
  suffisant pour le `Compteur`, extensible plus tard si un besoin réel
  apparaît).
- `lit` en dépendance `dependencies` (pas `devDependencies`) — le code Lit
  est embarqué dans le bundle applicatif, pas seulement utilisé en test.
- Toutes les commandes shell s'exécutent depuis `shell/` (`cd
  /home/lenen/projets/geostudio/shell` si le répertoire courant diffère).
- Les 20 specs E2E existantes doivent rester vertes.

---

### Task 1: Manifeste WC + panneau de props généré

**Files:**
- Create: `shell/src/builder/wc/manifest.ts`
- Create: `shell/src/builder/wc/generatedPropsPanel.tsx`
- Test: `shell/src/builder/wc/generatedPropsPanel.test.tsx`

**Interfaces:**
- Produces: `WcWidgetManifest` (type), `makeGeneratedPropsPanel(manifest:
  WcWidgetManifest): (p: { props: Record<string, unknown>; onChange:
  (props: Record<string, unknown>) => void; dataSources?: unknown }) =>
  ReactNode` — compatible avec la signature `PropsPanel` de
  `WidgetDefinition` (`shell/src/builder/registry.ts:24`).

- [ ] **Step 1: Écrire le type `WcWidgetManifest`**

`shell/src/builder/wc/manifest.ts` :

```ts
export type WcWidgetManifest = {
  type: string;
  tag: string;
  label: string;
  props: Array<{
    name: string;
    type: "string" | "number" | "boolean";
    label: string;
    default: unknown;
  }>;
  events?: readonly string[];
  actions?: readonly string[];
  defaultSize: { w: number; h: number };
};
```

- [ ] **Step 2: Écrire le test du panneau généré (échoue — le fichier n'existe pas encore)**

`shell/src/builder/wc/generatedPropsPanel.test.tsx` :

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { makeGeneratedPropsPanel } from "./generatedPropsPanel";
import type { WcWidgetManifest } from "./manifest";

const manifest: WcWidgetManifest = {
  type: "test.panel",
  tag: "test-panel-widget",
  label: "Test panneau",
  props: [
    { name: "initial", type: "number", label: "Valeur initiale", default: 0 },
    { name: "title", type: "string", label: "Titre", default: "" },
    { name: "loud", type: "boolean", label: "Bruyant", default: false },
  ],
  defaultSize: { w: 2, h: 2 },
};

test("renders one field per manifest prop, typed accordingly", () => {
  const Panel = makeGeneratedPropsPanel(manifest);
  render(<Panel props={{ initial: 3, title: "X", loud: true }} onChange={() => {}} />);
  expect(screen.getByLabelText("Valeur initiale")).toHaveAttribute("type", "number");
  expect(screen.getByLabelText("Valeur initiale")).toHaveValue(3);
  expect(screen.getByLabelText("Titre")).toHaveAttribute("type", "text");
  expect(screen.getByLabelText("Titre")).toHaveValue("X");
  expect(screen.getByLabelText("Bruyant")).toHaveAttribute("type", "checkbox");
  expect(screen.getByLabelText("Bruyant")).toBeChecked();
});

test("editing a number field calls onChange with a coerced number", async () => {
  const Panel = makeGeneratedPropsPanel(manifest);
  const onChange = vi.fn();
  render(<Panel props={{ initial: 3, title: "", loud: false }} onChange={onChange} />);
  await userEvent.clear(screen.getByLabelText("Valeur initiale"));
  await userEvent.type(screen.getByLabelText("Valeur initiale"), "7");
  expect(onChange).toHaveBeenLastCalledWith({ initial: 7, title: "", loud: false });
});

test("editing a boolean field calls onChange with a boolean", async () => {
  const Panel = makeGeneratedPropsPanel(manifest);
  const onChange = vi.fn();
  render(<Panel props={{ initial: 3, title: "", loud: false }} onChange={onChange} />);
  await userEvent.click(screen.getByLabelText("Bruyant"));
  expect(onChange).toHaveBeenLastCalledWith({ initial: 3, title: "", loud: true });
});
```

- [ ] **Step 3: Lancer le test pour vérifier qu'il échoue**

Run: `npm test -- generatedPropsPanel --run`
Expected: FAIL — `Cannot find module './generatedPropsPanel'`

- [ ] **Step 4: Implémenter le panneau généré**

`shell/src/builder/wc/generatedPropsPanel.tsx` :

```tsx
import type { WcWidgetManifest } from "./manifest";

export function makeGeneratedPropsPanel(manifest: WcWidgetManifest) {
  return function GeneratedPropsPanel({
    props,
    onChange,
  }: {
    props: Record<string, unknown>;
    onChange: (props: Record<string, unknown>) => void;
  }) {
    return (
      <div className="flex flex-col gap-2 text-sm">
        {manifest.props.map((p) => (
          <label key={p.name} className="flex flex-col gap-1">
            {p.label}
            {p.type === "boolean" ? (
              <input
                type="checkbox"
                aria-label={p.label}
                checked={Boolean(props[p.name])}
                onChange={(e) => onChange({ ...props, [p.name]: e.target.checked })}
              />
            ) : (
              <input
                type={p.type === "number" ? "number" : "text"}
                aria-label={p.label}
                className="h-9 rounded-md border border-slate-300 px-2"
                value={String(props[p.name] ?? "")}
                onChange={(e) =>
                  onChange({
                    ...props,
                    [p.name]: p.type === "number" ? Number(e.target.value) : e.target.value,
                  })
                }
              />
            )}
          </label>
        ))}
      </div>
    );
  };
}
```

- [ ] **Step 5: Lancer le test pour vérifier qu'il passe**

Run: `npm test -- generatedPropsPanel --run`
Expected: PASS (3 tests)

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/wc/manifest.ts shell/src/builder/wc/generatedPropsPanel.tsx shell/src/builder/wc/generatedPropsPanel.test.tsx
git commit -m "feat(shell): manifeste WC + panneau de props généré (SP-8a)"
```

---

### Task 2: `WcHost` — montage + propriétés DOM

**Files:**
- Create: `shell/src/builder/wc/WcHost.tsx`
- Test: `shell/src/builder/wc/WcHost.test.tsx`

**Interfaces:**
- Consumes: `WcWidgetManifest` (Task 1, `./manifest`), `WidgetContext`
  (`shell/src/builder/registry.ts:5`, champs `mode`, `data`, `user`,
  `navigate`, `bus`, `widgetId` déjà définis).
- Produces: `makeWcHost(manifest: WcWidgetManifest): (p: { props:
  Record<string, unknown>; ctx: WidgetContext }) => ReactNode` — compatible
  avec la signature `Component` de `WidgetDefinition`. Cette étape ne câble
  pas encore les events/actions (Task 3).

- [ ] **Step 1: Écrire le test de montage (échoue — le fichier n'existe pas encore)**

`shell/src/builder/wc/WcHost.test.tsx` :

```tsx
import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { makeWcHost } from "./WcHost";
import type { WcWidgetManifest } from "./manifest";
import type { WidgetContext } from "../registry";

class TestWcWidget extends HTMLElement {
  props?: unknown;
  data?: unknown;
  user?: unknown;
  navigate?: unknown;
}
if (!customElements.get("test-wc-host-widget")) {
  customElements.define("test-wc-host-widget", TestWcWidget);
}

const manifest: WcWidgetManifest = {
  type: "test.wc-host",
  tag: "test-wc-host-widget",
  label: "Test WcHost",
  props: [{ name: "initial", type: "number", label: "Initial", default: 0 }],
  defaultSize: { w: 2, h: 2 },
};

afterEach(cleanup);

test("mounts the custom element inside its container", () => {
  const WcHost = makeWcHost(manifest);
  const { container } = render(<WcHost props={{ initial: 5 }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(container.querySelector("test-wc-host-widget")).not.toBeNull();
});

test("assigns props/data/user/navigate as DOM properties, not attributes", () => {
  const WcHost = makeWcHost(manifest);
  const navigate = vi.fn();
  const ctx = {
    mode: "runtime",
    data: { loading: false, error: false, records: [] },
    user: { name: "alice" },
    navigate,
  } as unknown as WidgetContext;
  const { container } = render(<WcHost props={{ initial: 5 }} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as TestWcWidget;
  expect(el.props).toEqual({ initial: 5 });
  expect(el.data).toEqual(ctx.data);
  expect(el.user).toEqual({ name: "alice" });
  expect(el.navigate).toBe(navigate);
  expect(el.getAttribute("props")).toBeNull();
  expect(el.getAttribute("data")).toBeNull();
});

test("re-assigns props on every prop change", () => {
  const WcHost = makeWcHost(manifest);
  const ctx = { mode: "runtime" } as WidgetContext;
  const { container, rerender } = render(<WcHost props={{ initial: 1 }} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as TestWcWidget;
  rerender(<WcHost props={{ initial: 2 }} ctx={ctx} />);
  expect(el.props).toEqual({ initial: 2 });
});

test("removes the element from the DOM on unmount", () => {
  const WcHost = makeWcHost(manifest);
  const ctx = { mode: "runtime" } as WidgetContext;
  const { container, unmount } = render(<WcHost props={{}} ctx={ctx} />);
  expect(container.querySelector("test-wc-host-widget")).not.toBeNull();
  unmount();
  expect(container.querySelector("test-wc-host-widget")).toBeNull();
});
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `npm test -- WcHost --run`
Expected: FAIL — `Cannot find module './WcHost'`

- [ ] **Step 3: Implémenter `WcHost` (montage + propriétés, sans events/actions)**

`shell/src/builder/wc/WcHost.tsx` :

```tsx
import { useEffect, useRef } from "react";
import type { WidgetContext } from "../registry";
import type { WcWidgetManifest } from "./manifest";

export function makeWcHost(manifest: WcWidgetManifest) {
  return function WcHost({
    props,
    ctx,
  }: {
    props: Record<string, unknown>;
    ctx: WidgetContext;
  }) {
    const containerRef = useRef<HTMLDivElement>(null);
    const elRef = useRef<HTMLElement | null>(null);

    useEffect(() => {
      const el = document.createElement(manifest.tag);
      elRef.current = el;
      containerRef.current?.appendChild(el);
      return () => {
        el.remove();
        elRef.current = null;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
      const el = elRef.current as (HTMLElement & Record<string, unknown>) | null;
      if (!el) return;
      el.props = props;
      el.data = ctx.data;
      el.user = ctx.user;
      el.navigate = ctx.navigate;
    });

    return <div ref={containerRef} className="h-full w-full" />;
  };
}
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `npm test -- WcHost --run`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/wc/WcHost.tsx shell/src/builder/wc/WcHost.test.tsx
git commit -m "feat(shell): WcHost monte un custom element et lui assigne props/data/user/navigate (SP-8a)"
```

---

### Task 3: `WcHost` — events et actions

**Files:**
- Modify: `shell/src/builder/wc/WcHost.tsx`
- Modify: `shell/src/builder/wc/WcHost.test.tsx`

**Interfaces:**
- Consumes: `ActionBus` (`shell/src/builder/ActionBus.ts`) — `emit(widgetId,
  event, payload?)`, `register(widgetId, action, handler): () => void`,
  `configure(messages)`.
- Produces: `makeWcHost` (Task 2) gagne le câblage events/actions — sa
  signature publique ne change pas.

- [ ] **Step 1: Ajouter les tests d'events/actions (échouent — pas encore câblé)**

Ajouter à `shell/src/builder/wc/WcHost.test.tsx` (après les imports existants, ajouter `act` et `ActionBus`) :

```tsx
import { act, cleanup, render } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ActionBus } from "../ActionBus";
import { makeWcHost } from "./WcHost";
import type { WcWidgetManifest } from "./manifest";
import type { WidgetContext } from "../registry";
```

(remplace la ligne d'import `@testing-library/react` existante — `act` et
`ActionBus` s'ajoutent aux imports déjà présents, `cleanup`/`render`
inchangés.)

Étendre `TestWcWidget` avec une méthode d'action et déclarer les
events/actions dans le manifeste de test :

```tsx
class TestWcWidget extends HTMLElement {
  props?: unknown;
  data?: unknown;
  user?: unknown;
  navigate?: unknown;
  resetCalls: unknown[] = [];
  reset(payload?: unknown) {
    this.resetCalls.push(payload);
  }
}
if (!customElements.get("test-wc-host-widget")) {
  customElements.define("test-wc-host-widget", TestWcWidget);
}

const manifest: WcWidgetManifest = {
  type: "test.wc-host",
  tag: "test-wc-host-widget",
  label: "Test WcHost",
  props: [{ name: "initial", type: "number", label: "Initial", default: 0 }],
  events: ["changed"],
  actions: ["reset"],
  defaultSize: { w: 2, h: 2 },
};
```

Ajouter les tests :

```tsx
test("relays a CustomEvent dispatched by the element to bus.emit", () => {
  const WcHost = makeWcHost(manifest);
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("t1", "onChanged", handler);
  bus.configure([{ id: "m", from: "w1", event: "changed", to: "t1", action: "onChanged" }]);
  const ctx = { mode: "runtime", bus, widgetId: "w1" } as WidgetContext;
  const { container } = render(<WcHost props={{}} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as TestWcWidget;
  el.dispatchEvent(new CustomEvent("changed", { detail: { count: 3 } }));
  expect(handler).toHaveBeenCalledWith({ count: 3 });
});

test("invoking a bus action calls the matching public method on the element", () => {
  const WcHost = makeWcHost(manifest);
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "emitter", event: "go", to: "w1", action: "reset" }]);
  const ctx = { mode: "runtime", bus, widgetId: "w1" } as WidgetContext;
  const { container } = render(<WcHost props={{}} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as TestWcWidget;
  act(() => {
    bus.emit("emitter", "go", { to: 0 });
  });
  expect(el.resetCalls).toEqual([{ to: 0 }]);
});

test("unregisters the bus action and stops relaying events on unmount", () => {
  const WcHost = makeWcHost(manifest);
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "emitter", event: "go", to: "w1", action: "reset" }]);
  const ctx = { mode: "runtime", bus, widgetId: "w1" } as WidgetContext;
  const { container, unmount } = render(<WcHost props={{}} ctx={ctx} />);
  const el = container.querySelector("test-wc-host-widget") as TestWcWidget;
  unmount();
  bus.emit("emitter", "go");
  expect(el.resetCalls).toEqual([]);
});
```

- [ ] **Step 2: Lancer les tests pour vérifier qu'ils échouent**

Run: `npm test -- WcHost --run`
Expected: FAIL — les 3 nouveaux tests échouent (aucun relais events/actions
encore câblé), les 4 tests de Task 2 continuent de passer.

- [ ] **Step 3: Câbler events et actions dans `WcHost`**

`shell/src/builder/wc/WcHost.tsx` — remplacer le fichier entier :

```tsx
import { useEffect, useRef } from "react";
import type { WidgetContext } from "../registry";
import type { WcWidgetManifest } from "./manifest";

export function makeWcHost(manifest: WcWidgetManifest) {
  return function WcHost({
    props,
    ctx,
  }: {
    props: Record<string, unknown>;
    ctx: WidgetContext;
  }) {
    const containerRef = useRef<HTMLDivElement>(null);
    const elRef = useRef<HTMLElement | null>(null);

    useEffect(() => {
      const el = document.createElement(manifest.tag);
      elRef.current = el;
      containerRef.current?.appendChild(el);
      return () => {
        el.remove();
        elRef.current = null;
      };
      // eslint-disable-next-line react-hooks/exhaustive-deps
    }, []);

    useEffect(() => {
      const el = elRef.current as (HTMLElement & Record<string, unknown>) | null;
      if (!el) return;
      el.props = props;
      el.data = ctx.data;
      el.user = ctx.user;
      el.navigate = ctx.navigate;
    });

    useEffect(() => {
      const el = elRef.current;
      if (!el || !ctx.bus || !ctx.widgetId) return;
      const bus = ctx.bus;
      const widgetId = ctx.widgetId;
      const offs = (manifest.events ?? []).map((name) => {
        const listener = (e: Event) => bus.emit(widgetId, name, (e as CustomEvent).detail);
        el.addEventListener(name, listener);
        return () => el.removeEventListener(name, listener);
      });
      const unregs = (manifest.actions ?? []).map((name) =>
        bus.register(widgetId, name, (payload) => {
          (el as HTMLElement & Record<string, (payload?: unknown) => void>)[name]?.(payload);
        }),
      );
      return () => {
        offs.forEach((off) => off());
        unregs.forEach((unreg) => unreg());
      };
    }, [ctx.bus, ctx.widgetId]);

    return <div ref={containerRef} className="h-full w-full" />;
  };
}
```

- [ ] **Step 4: Lancer les tests pour vérifier qu'ils passent**

Run: `npm test -- WcHost --run`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/wc/WcHost.tsx shell/src/builder/wc/WcHost.test.tsx
git commit -m "feat(shell): WcHost relaie les CustomEvent vers le bus et invoque les actions (SP-8a)"
```

---

### Task 4: `registerWcWidget` — adaptateur registre

**Files:**
- Create: `shell/src/builder/wc/registerWcWidget.ts`
- Test: `shell/src/builder/wc/registerWcWidget.test.tsx`

**Interfaces:**
- Consumes: `registerWidget`/`getWidget`/`_resetRegistry`
  (`shell/src/builder/registry.ts`), `makeGeneratedPropsPanel` (Task 1),
  `makeWcHost` (Task 2/3), `WcWidgetManifest` (Task 1).
- Produces: `registerWcWidget(manifest: WcWidgetManifest): void` — point
  d'entrée public unique du module `wc/`, utilisé par Task 5 pour le
  `Compteur` WC et par toute future intégration (SP-8b : chargement
  dynamique).

- [ ] **Step 1: Écrire le test (échoue — le fichier n'existe pas encore)**

`shell/src/builder/wc/registerWcWidget.test.tsx` :

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import type { WidgetContext } from "../registry";
import { registerWcWidget } from "./registerWcWidget";
import type { WcWidgetManifest } from "./manifest";

class RegisterTestWidget extends HTMLElement {
  props?: unknown;
}
if (!customElements.get("register-test-widget")) {
  customElements.define("register-test-widget", RegisterTestWidget);
}

const manifest: WcWidgetManifest = {
  type: "test.register",
  tag: "register-test-widget",
  label: "Test enregistré",
  props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 7 }],
  events: ["changed"],
  actions: ["reset"],
  defaultSize: { w: 3, h: 2 },
};

beforeEach(() => _resetRegistry());

test("registers a WidgetDefinition with the manifest's identity and defaults", () => {
  registerWcWidget(manifest);
  const def = getWidget("test.register")!;
  expect(def.label).toBe("Test enregistré");
  expect(def.defaultProps).toEqual({ initial: 7 });
  expect(def.defaultSize).toEqual({ w: 3, h: 2 });
  expect(def.events).toEqual(["changed"]);
  expect(def.actions).toEqual(["reset"]);
});

test("the generated props panel edits props through onChange", async () => {
  registerWcWidget(manifest);
  const Panel = getWidget("test.register")!.PropsPanel;
  const onChange = vi.fn();
  render(<Panel props={{ initial: 7 }} dataSources={[]} onChange={onChange} />);
  await userEvent.clear(screen.getByLabelText("Valeur initiale"));
  await userEvent.type(screen.getByLabelText("Valeur initiale"), "9");
  expect(onChange).toHaveBeenLastCalledWith({ initial: 9 });
});

test("the generated Component mounts the custom element with its props", () => {
  registerWcWidget(manifest);
  const Component = getWidget("test.register")!.Component;
  const { container } = render(
    <Component props={{ initial: 9 }} ctx={{ mode: "runtime" } as WidgetContext} />,
  );
  const el = container.querySelector("register-test-widget") as RegisterTestWidget;
  expect(el.props).toEqual({ initial: 9 });
});
```

- [ ] **Step 2: Lancer le test pour vérifier qu'il échoue**

Run: `npm test -- registerWcWidget --run`
Expected: FAIL — `Cannot find module './registerWcWidget'`

- [ ] **Step 3: Implémenter l'adaptateur**

`shell/src/builder/wc/registerWcWidget.ts` :

```ts
import { registerWidget } from "../registry";
import { makeGeneratedPropsPanel } from "./generatedPropsPanel";
import { makeWcHost } from "./WcHost";
import type { WcWidgetManifest } from "./manifest";

export function registerWcWidget(manifest: WcWidgetManifest): void {
  registerWidget({
    type: manifest.type,
    label: manifest.label,
    defaultProps: Object.fromEntries(manifest.props.map((p) => [p.name, p.default])),
    defaultSize: manifest.defaultSize,
    events: manifest.events,
    actions: manifest.actions,
    PropsPanel: makeGeneratedPropsPanel(manifest),
    Component: makeWcHost(manifest),
  });
}
```

- [ ] **Step 4: Lancer le test pour vérifier qu'il passe**

Run: `npm test -- registerWcWidget --run`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/wc/registerWcWidget.ts shell/src/builder/wc/registerWcWidget.test.tsx
git commit -m "feat(shell): registerWcWidget branche un manifeste WC dans le registre de widgets (SP-8a)"
```

---

### Task 5: `Compteur` porté en Web Component de référence

**Files:**
- Create: `shell/src/builder/examples/counterWidgetWc.ts`
- Test: `shell/src/builder/examples/counterWidgetWc.test.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Modify: `shell/src/pages/AppRuntimePage.tsx`
- Modify: `shell/package.json` (dépendance `lit`)

**Interfaces:**
- Consumes: `registerWcWidget` (Task 4), `WcWidgetManifest` (Task 1).
- Produces: `registerCounterWcExampleWidget(): void`, widget enregistré sous
  `type: "example.counter-wc"`, tag `gs-counter` — utilisé par Task 6 (E2E).

- [ ] **Step 1: Installer `lit`**

Run: `cd /home/lenen/projets/geostudio/shell && npm install lit@^3.3.0`
Expected: `package.json` gagne `"lit": "^3.3.0"` dans `dependencies`,
`package-lock.json` mis à jour.

- [ ] **Step 2: Écrire le test du `Compteur` WC (échoue — le fichier n'existe pas encore)**

`shell/src/builder/examples/counterWidgetWc.test.tsx` :

```tsx
import { act, render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { ActionBus } from "../ActionBus";
import { registerCounterWcExampleWidget } from "./counterWidgetWc";
import type { GsCounter } from "./counterWidgetWc";
import type { WidgetContext } from "../registry";

beforeEach(() => {
  _resetRegistry();
  registerCounterWcExampleWidget();
});

test("starts at its initial value and increments on click", async () => {
  const Component = getWidget("example.counter-wc")!.Component;
  const { container } = render(
    <Component props={{ initial: 5 }} ctx={{ mode: "runtime" } as WidgetContext} />,
  );
  const el = container.querySelector("gs-counter") as GsCounter;
  await el.updateComplete;
  expect(el.shadowRoot!.querySelector("span")!.textContent).toBe("5");
  await userEvent.click(el.shadowRoot!.querySelector("button")!);
  await el.updateComplete;
  expect(el.shadowRoot!.querySelector("span")!.textContent).toBe("6");
});

test("emits changed with the new count", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("t1", "setFilter", handler);
  bus.configure([{ id: "m", from: "c1", event: "changed", to: "t1", action: "setFilter" }]);
  const Component = getWidget("example.counter-wc")!.Component;
  const { container } = render(
    <Component props={{ initial: 0 }} ctx={{ mode: "runtime", bus, widgetId: "c1" } as WidgetContext} />,
  );
  const el = container.querySelector("gs-counter") as GsCounter;
  await el.updateComplete;
  await userEvent.click(el.shadowRoot!.querySelector("button")!);
  expect(handler).toHaveBeenCalledWith({ count: 1 });
});

test("declares a reset action that resets to the initial value", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "emitter", event: "go", to: "c1", action: "reset" }]);
  const Component = getWidget("example.counter-wc")!.Component;
  const { container } = render(
    <Component props={{ initial: 3 }} ctx={{ mode: "runtime", bus, widgetId: "c1" } as WidgetContext} />,
  );
  const el = container.querySelector("gs-counter") as GsCounter;
  await el.updateComplete;
  await userEvent.click(el.shadowRoot!.querySelector("button")!);
  await el.updateComplete;
  expect(el.shadowRoot!.querySelector("span")!.textContent).toBe("4");
  await act(async () => {
    bus.emit("emitter", "go");
  });
  await el.updateComplete;
  expect(el.shadowRoot!.querySelector("span")!.textContent).toBe("3");
});

test("declares the events/actions the ActionsPanel needs to wire it", () => {
  expect(getWidget("example.counter-wc")!.events).toEqual(["changed"]);
  expect(getWidget("example.counter-wc")!.actions).toEqual(["reset"]);
});
```

- [ ] **Step 3: Lancer le test pour vérifier qu'il échoue**

Run: `npm test -- counterWidgetWc --run`
Expected: FAIL — `Cannot find module './counterWidgetWc'`

- [ ] **Step 4: Implémenter le `Compteur` en Lit**

`shell/src/builder/examples/counterWidgetWc.ts` :

```ts
import { LitElement, css, html } from "lit";
import { customElement, property, state } from "lit/decorators.js";
import { registerWcWidget } from "../wc/registerWcWidget";
import type { WcWidgetManifest } from "../wc/manifest";

@customElement("gs-counter")
export class GsCounter extends LitElement {
  static styles = css`
    :host {
      display: flex;
      height: 100%;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      gap: 0.25rem;
      font-family: var(--gs-font, system-ui, sans-serif);
    }
    span {
      font-size: 1.5rem;
      font-weight: 600;
      color: var(--gs-color-text, #0f172a);
    }
    button {
      border: 1px solid var(--gs-color-border, #cbd5e1);
      border-radius: var(--gs-radius, 0.375rem);
      padding: 0.25rem 0.5rem;
      font-size: 0.875rem;
      background: var(--gs-color-surface, #f8fafc);
      cursor: pointer;
    }
  `;

  @property({ attribute: false }) props: { initial?: number } = {};
  @state() private count = 0;
  private initialized = false;

  protected willUpdate(): void {
    if (!this.initialized) {
      this.count = Number(this.props?.initial ?? 0);
      this.initialized = true;
    }
  }

  reset(): void {
    this.count = Number(this.props?.initial ?? 0);
  }

  private increment(): void {
    this.count += 1;
    this.dispatchEvent(new CustomEvent("changed", { detail: { count: this.count } }));
  }

  protected render() {
    return html`
      <span>${this.count}</span>
      <button type="button" @click=${this.increment}>+1</button>
    `;
  }
}

export const counterWcManifest: WcWidgetManifest = {
  type: "example.counter-wc",
  tag: "gs-counter",
  label: "Compteur (WC)",
  props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 0 }],
  events: ["changed"],
  actions: ["reset"],
  defaultSize: { w: 2, h: 2 },
};

export function registerCounterWcExampleWidget(): void {
  registerWcWidget(counterWcManifest);
}
```

- [ ] **Step 5: Lancer le test pour vérifier qu'il passe**

Run: `npm test -- counterWidgetWc --run`
Expected: PASS (4 tests)

- [ ] **Step 6: Enregistrer le widget dans le builder et le runtime**

`shell/src/pages/AppBuilderPage.tsx` — ajouter l'import après celui de
`registerCounterExampleWidget` (ligne 14) :

```ts
import { registerCounterWcExampleWidget } from "../builder/examples/counterWidgetWc";
```

et l'appel après `registerCounterExampleWidget();` (ligne 22) :

```ts
registerCounterWcExampleWidget();
```

`shell/src/pages/AppRuntimePage.tsx` — même ajout après l'import et l'appel
existants de `registerCounterExampleWidget` (lignes 5 et 8) :

```ts
import { registerCounterWcExampleWidget } from "../builder/examples/counterWidgetWc";
```

```ts
registerCounterWcExampleWidget();
```

- [ ] **Step 7: Lancer toute la suite vitest pour vérifier l'absence de régression**

Run: `npm test -- --run`
Expected: PASS — tous les tests existants + les nouveaux passent (aucune
suppression, uniquement des ajouts).

- [ ] **Step 8: Lancer le typecheck**

Run: `npm run build`
Expected: succès (`tsc --noEmit` puis `vite build`), aucune erreur de type.

- [ ] **Step 9: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/src/builder/examples/counterWidgetWc.ts shell/src/builder/examples/counterWidgetWc.test.tsx shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppRuntimePage.tsx
git commit -m "feat(shell): Compteur porté en Web Component de référence (SP-8a)"
```

---

### Task 6: E2E — widget WC dans le builder, thème, events, actions

**Files:**
- Create: `shell/e2e/wc-widget-bridge.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`shell/e2e/mocks.ts`), le widget `Compteur (WC)`
  enregistré par Task 5 (label palette "Compteur (WC)", tag `gs-counter`).

- [ ] **Step 1: Écrire la spec E2E**

`shell/e2e/wc-widget-bridge.spec.ts` :

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un widget Web Component se pose dans le builder, suit le thème, émet un event vers une action composée et répond à une action du bus", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App WC");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Compteur (WC) posé sur le canvas : props par défaut, thème live.
  await page.getByRole("button", { name: "Compteur (WC)" }).click();
  const counter = page.locator("gs-counter");
  await expect(counter.getByText("0", { exact: true })).toBeVisible();
  await counter.getByRole("button", { name: "+1" }).click();
  await expect(counter.getByText("1", { exact: true })).toBeVisible();

  const colorBefore = await counter.locator("span").evaluate((el) => getComputedStyle(el).color);
  await page.getByLabel("Couleur du texte").fill("#ff0000");
  await expect(async () => {
    const colorAfter = await counter.locator("span").evaluate((el) => getComputedStyle(el).color);
    expect(colorAfter).not.toBe(colorBefore);
  }).toPass();

  // Bouton (déclenchera reset sur le Compteur WC) et Texte (affichera la variable count).
  await page.getByRole("button", { name: "Bouton" }).click();
  await page.getByRole("button", { name: "Texte" }).click();
  await page.getByLabel("Texte du widget").fill("Compte : {{var:count}}");

  await page.getByRole("button", { name: "Ajouter une variable" }).click();
  await page.getByLabel(/Renommer la variable/).fill("count");
  await page.getByLabel(/Type de la variable/).selectOption("number");

  // Compteur (WC).changed -> Variable(count).set
  await page.getByLabel("Widget émetteur").selectOption({ label: "Compteur (WC)" });
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ label: "Variable : count" });
  await page.getByLabel("Action").selectOption("set");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  // Bouton.clicked -> Compteur (WC).reset
  await page.getByLabel("Widget émetteur").selectOption({ label: "Bouton" });
  await page.getByLabel("Événement").selectOption("clicked");
  await page.getByLabel("Widget cible").selectOption({ label: "Compteur (WC)" });
  await page.getByLabel("Action").selectOption("reset");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime : remontage à froid, defaultProps.initial = 0.
  await page.goto("/apps/9");
  const runtimeCounter = page.locator("gs-counter");
  await expect(runtimeCounter.getByText("0", { exact: true })).toBeVisible();

  await runtimeCounter.getByRole("button", { name: "+1" }).click();
  await runtimeCounter.getByRole("button", { name: "+1" }).click();
  await runtimeCounter.getByRole("button", { name: "+1" }).click();
  await expect(runtimeCounter.getByText("3", { exact: true })).toBeVisible();

  // L'event "changed" a déclenché l'action composée jusqu'au Texte.
  await expect(page.getByText("Compte : 3")).toBeVisible();

  // Bouton.clicked déclenche l'action "reset" du bus sur le widget WC.
  await page.getByRole("button", { name: "Bouton" }).click();
  await expect(runtimeCounter.getByText("0", { exact: true })).toBeVisible();
});
```

- [ ] **Step 2: Lancer la nouvelle spec seule**

Run: `npm run e2e -- wc-widget-bridge`
Expected: PASS (1 test).

Si le test échoue sur une étape de sélection (`selectOption`/`getByLabel`),
inspecter le DOM produit — les libellés exacts (`Compteur (WC)`, `Compte :
{{var:count}}`, régex `/Renommer la variable/`, `/Type de la variable/`)
suivent exactement les conventions déjà utilisées par
`shell/e2e/action-conditions.spec.ts` et `shell/e2e/expr-bindings.spec.ts` —
comparer contre ces fichiers en cas d'écart.

- [ ] **Step 3: Lancer toute la suite E2E pour vérifier l'absence de régression**

Run: `npm run e2e`
Expected: PASS — 21 specs vertes (20 existantes + `wc-widget-bridge.spec.ts`).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/wc-widget-bridge.spec.ts
git commit -m "test(e2e): pont Web Component — thème, events, actions composées (SP-8a)"
```

---

## Vérification finale

- [ ] `cd shell && npm run build` — `tsc --noEmit` + `vite build` sans erreur.
- [ ] `cd shell && npm test -- --run` — tous les tests vitest passent.
- [ ] `cd shell && npm run e2e` — 21 specs E2E vertes.
- [ ] Relire `docs/superpowers/specs/2026-07-13-sp8a-contrat-wc-pont-widgethost-design.md`
  et confirmer que chaque critère d'acceptation a une preuve dans les tests
  ci-dessus (palette → canvas → props/thème/events/actions → aucune
  régression sur le `Compteur` React ni les 20 specs E2E précédentes).
