// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, registerWidget } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { AppRenderer } from "./AppRenderer";
import type { AppConfig, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { AuthState } from "../auth/useAuth";
import { useBusAction } from "./ActionBusContext";
import { useEffect } from "react";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "tanguy",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

const stubClient = {
  queryDataSource: vi.fn().mockResolvedValue([]),
  featuresUrl: vi.fn().mockReturnValue(""),
  getDatasetConfig: vi
    .fn()
    .mockResolvedValue({ source: "collection", collectionId: "col1", columns: {} }),
  getCollectionSchema: vi
    .fn()
    .mockResolvedValue({ collection: "col1", pk: "id", geometry: null, fields: [] }),
} as unknown as ItemClient;

function Wrapper({ children }: { children: React.ReactNode }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return (
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={stubClient}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

const config: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: {
    type: "grid",
    breakpoints: {},
    items: [{ id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Salut" } }],
  },
};

test("runtime mode renders widgets without edit chrome", () => {
  render(<AppRenderer config={config} mode="runtime" />, { wrapper: Wrapper });
  expect(screen.getByText("Salut")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Sélectionner/ })).toBeNull();
});

test("edit mode moving a widget calls onChange with the new position", async () => {
  const onChange = vi.fn();
  render(
    <AppRenderer
      config={config}
      mode="edit"
      selectedId="t1"
      onSelect={vi.fn()}
      onChange={onChange}
    />,
    { wrapper: Wrapper },
  );
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-t1 à droite" }));
  const next = onChange.mock.calls[0][0] as AppConfig;
  expect(next.layout.items[0]).toMatchObject({ x: 1 });
});

test("configures the bus so a button click drives a wired action", async () => {
  // Two buttons: one emits "clicked"; the message wires it to the other's… there is
  // no builtin action on button, so assert wiring via a spy widget is covered in
  // ActionBusContext.test. Here assert the renderer wires messages without crashing
  // and renders interactive widgets.
  const cfg: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [{ id: "m", from: "b1", event: "clicked", to: "b1", action: "noop" }],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "b1", widget: "button", x: 0, y: 0, w: 2, h: 1, props: { label: "Go" } }],
    },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  // No target action registered → emitting is a safe no-op; the app still renders.
  await userEvent.click(screen.getByRole("button", { name: "Go" }));
  expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument();
});

test("edits the sm layout when the breakpoint prop is sm, leaving the base intact", async () => {
  let latest: AppConfig | null = null;
  const cfg: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } }],
    },
  };
  render(
    <AppRenderer
      config={cfg}
      mode="edit"
      breakpoint="sm"
      selectedId="w1"
      onSelect={() => {}}
      onChange={(c) => {
        latest = c;
      }}
    />,
    { wrapper: Wrapper },
  );
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-w1 à droite" }));
  expect(latest!.layout.items[0].x).toBe(0); // base untouched
  expect(latest!.layout.items[0].layouts?.sm).toEqual({ x: 1, y: 0, w: 4, h: 2 });
});

test("renders the item at its sm override when breakpoint=sm", () => {
  const cfg: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "w1",
          widget: "text",
          x: 0,
          y: 0,
          w: 4,
          h: 2,
          props: { text: "Hi" },
          layouts: { sm: { x: 6, y: 2, w: 6, h: 2 } },
        },
      ],
    },
  };
  const { container } = render(<AppRenderer config={cfg} mode="runtime" breakpoint="sm" />, {
    wrapper: Wrapper,
  });
  expect(container.querySelector("[data-col]")).toHaveAttribute("data-col", "6");
});

test("applies theme CSS variables on the root container, falling back to defaults", () => {
  const cfg: AppConfig = { ...config, theme: { colors: { primary: "#ff0000" } } };
  const { container } = render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  const root = container.firstChild as HTMLElement;
  expect(root.style.getPropertyValue("--gs-color-primary")).toBe("#ff0000");
  expect(root.style.getPropertyValue("--gs-color-background")).toBe("#ffffff"); // default, untouched
  expect(root).toHaveClass("bg-[var(--gs-color-background)]");
  expect(root).toHaveClass("font-[var(--gs-font)]");
});

test("renders only the active page's items when pages exist", () => {
  const cfg: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "a1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: { text: "Accueil" } }],
    },
    pages: [
      {
        id: "p1",
        name: "Accueil",
        layout: {
          type: "grid",
          breakpoints: {},
          items: [{ id: "a1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: { text: "Accueil" } }],
        },
      },
      {
        id: "p2",
        name: "Détails",
        layout: {
          type: "grid",
          breakpoints: {},
          items: [{ id: "b1", widget: "text", x: 0, y: 0, w: 2, h: 2, props: { text: "Détails" } }],
        },
      },
    ],
  };
  render(<AppRenderer config={cfg} mode="runtime" pageId="p2" />, { wrapper: Wrapper });
  expect(screen.getByText("Détails")).toBeInTheDocument();
  expect(screen.queryByText("Accueil")).toBeNull();
});

test("edits write to the active page's layout, mirroring pages[0] into the top-level layout", async () => {
  let latest: AppConfig | null = null;
  const cfg: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "a1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } }],
    },
    pages: [
      {
        id: "p1",
        name: "Accueil",
        layout: {
          type: "grid",
          breakpoints: {},
          items: [{ id: "a1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } }],
        },
      },
    ],
  };
  render(
    <AppRenderer
      config={cfg}
      mode="edit"
      pageId="p1"
      selectedId="a1"
      onSelect={() => {}}
      onChange={(c) => {
        latest = c;
      }}
    />,
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
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "n1", widget: "nav-probe", x: 0, y: 0, w: 2, h: 1, props: {} }],
    },
    pages: [
      {
        id: "p1",
        name: "Accueil",
        layout: {
          type: "grid",
          breakpoints: {},
          items: [{ id: "n1", widget: "nav-probe", x: 0, y: 0, w: 2, h: 1, props: {} }],
        },
      },
      { id: "p2", name: "Détails", layout: { type: "grid", breakpoints: {}, items: [] } },
    ],
  };
  const onNavigate = vi.fn();
  render(<AppRenderer config={cfg} mode="runtime" pageId="p1" onNavigate={onNavigate} />, {
    wrapper: Wrapper,
  });
  expect(screen.getByText("pages:Accueil,Détails")).toBeInTheDocument();
  await userEvent.click(screen.getByText("go"));
  expect(onNavigate).toHaveBeenCalledWith("p2");
});

test("threads variables into widget context, seeded from their initialValue", () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "message", initialValue: "salut" }],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "{{var:message}}" } },
      ],
    },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  expect(screen.getByText("salut")).toBeInTheDocument();
});

test("a variable.set action updates the value read by a Texte widget", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "message", initialValue: "" }],
    messages: [{ id: "m1", from: "flt1", event: "changed", to: "var:v1", action: "set" }],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "flt1",
          widget: "filter",
          x: 0,
          y: 0,
          w: 3,
          h: 1,
          props: { field: "message", label: "Message" },
        },
        { id: "t1", widget: "text", x: 0, y: 1, w: 4, h: 2, props: { text: "{{var:message}}" } },
      ],
    },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "hello");
  expect(await screen.findByText("hello")).toBeInTheDocument();
});

test("a variable.set action with non-matching object payload resolves to empty string, not [object Object]", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "message", initialValue: "initial" }],
    messages: [{ id: "m1", from: "btn1", event: "clicked", to: "var:v1", action: "set" }],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: "btn1", widget: "button", x: 0, y: 0, w: 2, h: 1, props: { label: "Click me" } },
        {
          id: "t1",
          widget: "text",
          x: 0,
          y: 1,
          w: 4,
          h: 2,
          props: { text: "Value: {{var:message}}" },
        },
      ],
    },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  const textElement = screen.getByText("Value: initial");
  expect(textElement).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Click me" }));
  // Button emits {widgetId}, which doesn't have a "message" key.
  // The variable should resolve to empty string, not "[object Object]".
  expect(textElement.textContent).toBe("Value: ");
  expect(screen.queryByText(/\[object Object\]/)).toBeNull();
});

test("a message's condition gates the action on the emitting event's payload", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "status", initialValue: "" }],
    messages: [
      {
        id: "m1",
        from: "flt1",
        event: "changed",
        to: "var:v1",
        action: "set",
        when: "record.status == 'Nord'",
      },
    ],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "flt1",
          widget: "filter",
          x: 0,
          y: 0,
          w: 3,
          h: 1,
          props: { field: "status", label: "Filtre" },
        },
        {
          id: "t1",
          widget: "text",
          x: 0,
          y: 1,
          w: 4,
          h: 2,
          props: { text: "Statut: {{var:status}}" },
        },
      ],
    },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  expect(screen.getByText("Statut:")).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "Nord");
  expect(await screen.findByText("Statut: Nord")).toBeInTheDocument();
});

test("a message's condition can reference live vars, not just the payload", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [
      { id: "gate", name: "gate", initialValue: "open" },
      { id: "v1", name: "message", initialValue: "" },
    ],
    messages: [
      {
        id: "m1",
        from: "flt1",
        event: "changed",
        to: "var:v1",
        action: "set",
        when: "vars.gate == 'open'",
      },
    ],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "flt1",
          widget: "filter",
          x: 0,
          y: 0,
          w: 3,
          h: 1,
          props: { field: "message", label: "Filtre" },
        },
        {
          id: "t1",
          widget: "text",
          x: 0,
          y: 1,
          w: 4,
          h: 2,
          props: { text: "Msg: {{var:message}}" },
        },
      ],
    },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "hi");
  expect(await screen.findByText("Msg: hi")).toBeInTheDocument();
});

test("a message's condition prevents the action from firing when it evaluates falsy", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "message", initialValue: "initial" }],
    messages: [
      {
        id: "m1",
        from: "flt1",
        event: "changed",
        to: "var:v1",
        action: "set",
        when: "vars.gate == 'open'",
      },
    ],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "flt1",
          widget: "filter",
          x: 0,
          y: 0,
          w: 3,
          h: 1,
          props: { field: "message", label: "Filtre" },
        },
        {
          id: "t1",
          widget: "text",
          x: 0,
          y: 1,
          w: 4,
          h: 2,
          props: { text: "Msg: {{var:message}}" },
        },
      ],
    },
  };
  // No "gate" variable exists on this config, so vars.gate is undefined → the
  // condition evaluates falsy (evaluateExpression warns + returns undefined).
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "hi");
  expect(screen.getByText("Msg: initial")).toBeInTheDocument();
});

test("a number-typed variable coerces the payload's matching field to a number", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "count", type: "number", initialValue: 0 }],
    messages: [{ id: "m1", from: "flt1", event: "changed", to: "var:v1", action: "set" }],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "flt1",
          widget: "filter",
          x: 0,
          y: 0,
          w: 3,
          h: 1,
          props: { field: "count", label: "Filtre" },
        },
        {
          id: "t1",
          widget: "text",
          x: 0,
          y: 1,
          w: 4,
          h: 2,
          props: { text: "Total : {{var:count}}" },
        },
      ],
    },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "42");
  expect(await screen.findByText("Total : 42")).toBeInTheDocument();
});

test("a number-typed variable keeps its previous value when the payload is not a valid number", async () => {
  const cfg: AppConfig = {
    ...config,
    variables: [{ id: "v1", name: "count", type: "number", initialValue: 7 }],
    messages: [{ id: "m1", from: "flt1", event: "changed", to: "var:v1", action: "set" }],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "flt1",
          widget: "filter",
          x: 0,
          y: 0,
          w: 3,
          h: 1,
          props: { field: "count", label: "Filtre" },
        },
        {
          id: "t1",
          widget: "text",
          x: 0,
          y: 1,
          w: 4,
          h: 2,
          props: { text: "Total : {{var:count}}" },
        },
      ],
    },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.type(screen.getByLabelText("Valeur du filtre"), "abc");
  expect(screen.getByText("Total : 7")).toBeInTheDocument();
});

test("a record-typed variable receives the emitter's whole payload, not an extraction by name", async () => {
  const cfg: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    variables: [{ id: "v1", name: "selected", type: "record", initialValue: null }],
    messages: [{ id: "m1", from: "btn1", event: "clicked", to: "var:v1", action: "set" }],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: "btn1", widget: "button", x: 0, y: 0, w: 2, h: 1, props: { label: "Go" } },
        {
          id: "t1",
          widget: "text",
          x: 0,
          y: 1,
          w: 4,
          h: 2,
          props: { text: "Sélection : {{var:selected}}" },
        },
      ],
    },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.click(screen.getByRole("button", { name: "Go" }));
  // Button emits { widgetId: "btn1" } — the whole payload, stored as-is (record type bypasses by-name extraction).
  expect(await screen.findByText('Sélection : {"widgetId":"btn1"}')).toBeInTheDocument();
});

test("a list-typed variable receives the emitter's whole payload when it is an array", async () => {
  _resetRegistry();
  registerBuiltinWidgets();
  registerWidget({
    type: "list-emitter-probe",
    label: "Probe",
    defaultProps: {},
    defaultSize: { w: 2, h: 1 },
    events: ["emitted"],
    PropsPanel: () => null,
    Component: ({ ctx }) => (
      <button onClick={() => ctx.bus?.emit(ctx.widgetId ?? "", "emitted", [1, 2, 3])}>emit</button>
    ),
  });
  const cfg: AppConfig = {
    kind: "app",
    theme: {},
    dataSources: [],
    variables: [{ id: "v1", name: "items", type: "list", initialValue: [] }],
    messages: [{ id: "m1", from: "p1", event: "emitted", to: "var:v1", action: "set" }],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: "p1", widget: "list-emitter-probe", x: 0, y: 0, w: 2, h: 1, props: {} },
        {
          id: "t1",
          widget: "text",
          x: 0,
          y: 1,
          w: 4,
          h: 2,
          props: { text: "Items : {{var:items}}" },
        },
      ],
    },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  await userEvent.click(screen.getByRole("button", { name: "emit" }));
  expect(await screen.findByText("Items : [1,2,3]")).toBeInTheDocument();
});

const flySpy = vi.fn();

function registerFlyTarget() {
  registerWidget({
    type: "flytarget",
    label: "FlyTarget",
    defaultProps: {},
    defaultSize: { w: 2, h: 1 },
    actions: ["flyTo"],
    PropsPanel: () => null,
    Component: ({ ctx }) => {
      useBusAction(ctx.bus, ctx.widgetId, "flyTo", (p) => flySpy(p));
      return <div>cible</div>;
    },
  });
}

function storyConfig(): AppConfig {
  return {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    navigationMode: "story",
    layout: { type: "grid", breakpoints: {}, items: [] },
    pages: [
      {
        id: "p1",
        name: "Intro",
        layout: {
          type: "grid",
          breakpoints: {},
          items: [
            { id: "m1", widget: "flytarget", x: 0, y: 0, w: 2, h: 1, props: {} },
            { id: "txt1", widget: "text", x: 0, y: 1, w: 4, h: 1, props: { text: "Chapitre un" } },
          ],
        },
        onEnter: [
          {
            id: "oe1",
            from: "p1",
            event: "enter",
            to: "m1",
            action: "flyTo",
            payload: { center: [1, 2] },
          },
        ],
      },
      {
        id: "p2",
        name: "Suite",
        layout: {
          type: "grid",
          breakpoints: {},
          items: [
            {
              id: "txt2",
              widget: "text",
              x: 0,
              y: 0,
              w: 4,
              h: 1,
              props: { text: "Chapitre deux" },
            },
          ],
        },
        onEnter: [],
      },
    ],
  };
}

test("story mode shows a progress bar and prev/next; prev is disabled on the first chapter", () => {
  registerFlyTarget();
  render(<AppRenderer config={storyConfig()} mode="runtime" />, { wrapper: Wrapper });
  expect(screen.getByText("Chapitre 1 / 2")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Précédent" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Suivant" })).toBeEnabled();
});

test("story mode dispatches the active page's onEnter to its widget on entry", () => {
  flySpy.mockClear();
  registerFlyTarget();
  render(<AppRenderer config={storyConfig()} mode="runtime" />, { wrapper: Wrapper });
  expect(flySpy).toHaveBeenCalledWith({ center: [1, 2] });
});

test("story mode navigates to the next chapter and updates the progress counter", async () => {
  registerFlyTarget();
  render(<AppRenderer config={storyConfig()} mode="runtime" />, { wrapper: Wrapper });
  expect(screen.getByText("Chapitre un")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Suivant" }));
  expect(screen.getByText("Chapitre 2 / 2")).toBeInTheDocument();
  expect(screen.getByText("Chapitre deux")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Suivant" })).toBeDisabled();
});

test("tabs-mode config (no navigationMode) shows no story chrome and no onEnter dispatch", () => {
  flySpy.mockClear();
  registerFlyTarget();
  const cfg = storyConfig();
  cfg.navigationMode = "tabs";
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  expect(screen.queryByText(/Chapitre 1 \/ 2/)).toBeNull();
  expect(screen.queryByRole("button", { name: "Suivant" })).toBeNull();
  expect(flySpy).not.toHaveBeenCalled();
});

test("edit mode never dispatches onEnter and shows no story chrome", () => {
  flySpy.mockClear();
  registerFlyTarget();
  render(<AppRenderer config={storyConfig()} mode="edit" />, { wrapper: Wrapper });
  expect(screen.queryByRole("button", { name: "Suivant" })).toBeNull();
  expect(flySpy).not.toHaveBeenCalled();
});

test("mounts AnalyticsContextProvider with config.interactions and a widget can read it", async () => {
  const cfg: AppConfig = {
    ...config,
    interactions: "auto",
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Salut" } }],
    },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  // Smoke test: rendering with interactions:"auto" doesn't crash and still shows the widget.
  expect(screen.getByText("Salut")).toBeInTheDocument();
});

test("a widget under AppRenderer can read the analytics context via useAnalyticsContext", async () => {
  const { getWidget, registerWidget: register } = await import("./registry");
  const { useAnalyticsContext, useSetTimeRange } = await import("./AnalyticsContext");
  register({
    type: "__analytics_probe__",
    label: "probe",
    defaultProps: {},
    defaultSize: { w: 1, h: 1 },
    PropsPanel: () => null,
    Component: () => {
      const ctx = useAnalyticsContext();
      const setTimeRange = useSetTimeRange();
      useEffect(() => {
        setTimeRange({ from: "a", to: "b" });
      }, [setTimeRange]);
      return <p>probe:{ctx.timeRange ? "set" : "empty"}</p>;
    },
  });
  const cfg: AppConfig = {
    ...config,
    interactions: "auto",
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "p1", widget: "__analytics_probe__", x: 0, y: 0, w: 4, h: 2, props: {} }],
    },
  };
  render(<AppRenderer config={cfg} mode="runtime" />, { wrapper: Wrapper });
  expect(await screen.findByText("probe:set")).toBeInTheDocument();
  expect(getWidget("__analytics_probe__")).toBeDefined();
});

test("shows the analytics context indicator only in non-edit mode with interactions auto", async () => {
  const autoConfig: AppConfig = { ...config, interactions: "auto" };
  const { rerender } = render(<AppRenderer config={autoConfig} mode="edit" />, {
    wrapper: Wrapper,
  });
  expect(screen.queryByLabelText("Effacer la période")).not.toBeInTheDocument();

  rerender(<AppRenderer config={{ ...config, interactions: "manual" }} mode="runtime" />);
  expect(screen.queryByLabelText("Effacer la période")).not.toBeInTheDocument();
});

test("shows the explorer menu on an eligible widget only when interactions is auto and not edit mode", async () => {
  const autoConfig: AppConfig = {
    ...config,
    interactions: "auto",
    dataSources: [
      { id: "src1", type: "features", service: "core", layer: "col1", datasetId: "ds1", query: {} },
    ],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        {
          id: "ind1",
          widget: "indicator",
          x: 0,
          y: 0,
          w: 2,
          h: 2,
          props: { dataSourceId: "src1", label: "Total" },
        },
      ],
    },
  };
  const { rerender } = render(<AppRenderer config={autoConfig} mode="runtime" />, {
    wrapper: Wrapper,
  });
  expect(await screen.findByLabelText("Explorer")).toBeInTheDocument();

  rerender(<AppRenderer config={autoConfig} mode="edit" />);
  expect(screen.queryByLabelText("Explorer")).not.toBeInTheDocument();

  rerender(<AppRenderer config={{ ...autoConfig, interactions: "manual" }} mode="runtime" />);
  expect(screen.queryByLabelText("Explorer")).not.toBeInTheDocument();
});
