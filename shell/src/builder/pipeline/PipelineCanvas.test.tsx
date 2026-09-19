// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { PipelineEdge, PipelineNode, PipelineOpsCatalog } from "../../api/types";
import { PipelineCanvas } from "./PipelineCanvas";
import { expectAriaWired } from "../../test/expectAriaWired";

// @xyflow/react appelle ResizeObserver sans garde — stub local à ce fichier
// uniquement, même patron que EChart.test.tsx (cf. plan Global Constraints).
// jsdom ne fait aucune mise en page : offsetWidth/offsetHeight valent
// toujours 0 et le ResizeObserver natif n'existe pas. Sans mesure non nulle,
// @xyflow/react ne marque jamais les nœuds "initialisés"
// (internals.handleBounds reste undefined) et EdgeWrapper retourne null en
// permanence — les arêtes (et donc le bouton "+" testé plus bas) ne
// s'affichent jamais. Le stub doit donc *déclencher* la mesure (observe()
// appelle synchroniquement le callback) et offsetWidth/offsetHeight doivent
// être non nuls pour que la boucle updateNodeInternals (@xyflow/system)
// n'abandonne pas (elle ignore silencieusement toute mesure 0×0).
beforeEach(() => {
  Object.defineProperty(HTMLElement.prototype, "offsetWidth", { configurable: true, value: 160 });
  Object.defineProperty(HTMLElement.prototype, "offsetHeight", { configurable: true, value: 48 });
  class StubResizeObserver {
    private readonly callback: ResizeObserverCallback;
    constructor(callback: ResizeObserverCallback) {
      this.callback = callback;
    }
    observe(target: Element) {
      const rect = { width: 160, height: 48 } as DOMRectReadOnly;
      const entry = {
        target,
        contentRect: rect,
        borderBoxSize: [{ inlineSize: 160, blockSize: 48 }],
        contentBoxSize: [{ inlineSize: 160, blockSize: 48 }],
        devicePixelContentBoxSize: [{ inlineSize: 160, blockSize: 48 }],
      } as unknown as ResizeObserverEntry;
      this.callback([entry], this as unknown as ResizeObserver);
    }
    unobserve() {}
    disconnect() {}
  }
  vi.stubGlobal("ResizeObserver", StubResizeObserver);
  // jsdom n'implémente pas DOMMatrixReadOnly (aucun moteur CSS) ; @xyflow/system
  // s'en sert pour lire le zoom courant depuis `transform: matrix(...)` lors de
  // la mesure des nœuds. m22 = facteur d'échelle vertical = zoom par défaut (1).
  class StubDOMMatrixReadOnly {
    m22 = 1;
    constructor(_transform?: string) {}
  }
  vi.stubGlobal("DOMMatrixReadOnly", StubDOMMatrixReadOnly);
});
afterEach(() => {
  vi.unstubAllGlobals();
  Reflect.deleteProperty(HTMLElement.prototype, "offsetWidth");
  Reflect.deleteProperty(HTMLElement.prototype, "offsetHeight");
});

const NODES: PipelineNode[] = [
  {
    id: "r1",
    kind: "reader",
    op: "reader.collection",
    x: 0,
    y: 0,
    params: { collectionId: "villes" },
    title: "Villes",
  },
  {
    id: "w1",
    kind: "writer",
    op: "writer.collection",
    x: 300,
    y: 0,
    params: { collectionId: "villes_propres" },
    title: "Écriture",
  },
];
const EDGES: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1" }];

test("renders one labeled element per node", () => {
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  expect(screen.getByText("Villes")).toBeInTheDocument();
  expect(screen.getByText("Écriture")).toBeInTheDocument();
});

test("clicking a node calls onSelectNode with its id", () => {
  const onSelectNode = vi.fn();
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={onSelectNode}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByText("Villes"));
  expect(onSelectNode).toHaveBeenCalledWith("r1");
});

test("the edge's insert button is present and triggers onInsertOnEdge with the edge id and a chosen op", () => {
  const onInsertOnEdge = vi.fn();
  const catalog: PipelineOpsCatalog = {
    "transform.filter": { kind: "transform", paramsSchema: { properties: {} } },
  };
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={onInsertOnEdge}
      opsCatalog={catalog}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  const insertButton = screen.getByRole("button", { name: "Insérer une étape sur cette arête" });
  expectAriaWired(insertButton, insertButton.getAttribute("aria-controls")!, false);
  fireEvent.click(insertButton);
  expectAriaWired(insertButton, insertButton.getAttribute("aria-controls")!, true);
  expect(screen.getByRole("menu")).toHaveAttribute(
    "id",
    insertButton.getAttribute("aria-controls"),
  );
  fireEvent.click(screen.getByRole("menuitem", { name: "transform.filter" }));
  expect(onInsertOnEdge).toHaveBeenCalledWith("e1", "transform.filter");
});

test("the edge insertion menu offers the 5 spatial transform ops", () => {
  const catalog: PipelineOpsCatalog = Object.fromEntries(
    [
      "transform.buffer",
      "transform.reproject",
      "transform.intersection",
      "transform.countWithin",
      "transform.h3Aggregate",
    ].map((op) => [op, { kind: "transform", paramsSchema: { properties: {} } }]),
  );
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={catalog}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Insérer une étape sur cette arête" }));
  for (const op of [
    "transform.buffer",
    "transform.reproject",
    "transform.intersection",
    "transform.countWithin",
    "transform.h3Aggregate",
  ]) {
    expect(screen.getByRole("menuitem", { name: op })).toBeInTheDocument();
  }
});

const BINARY_CATALOG: PipelineOpsCatalog = {
  "reader.collection": { kind: "reader", paramsSchema: { properties: {} } },
  "writer.collection": { kind: "writer", paramsSchema: { properties: {} } },
  "transform.join": {
    kind: "transform",
    paramsSchema: { properties: {} },
    acceptsSecondaryInput: true,
  },
};

test("a node whose op accepts a secondary input renders a second target handle", () => {
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {}, title: "R" },
    { id: "t1", kind: "transform", op: "transform.join", x: 300, y: 0, params: {}, title: "J" },
  ];
  render(
    <PipelineCanvas
      nodes={nodes}
      edges={[]}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={BINARY_CATALOG}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  const joinNodeEl = screen.getByText("J").closest(".react-flow__node")!;
  expect(joinNodeEl.querySelectorAll(".react-flow__handle").length).toBe(3); // primary target + secondary target + source
});

test("a node whose op does not accept a secondary input renders only one target handle", () => {
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  const readerNodeEl = screen.getByText("Villes").closest(".react-flow__node")!;
  expect(readerNodeEl.querySelectorAll(".react-flow__handle").length).toBe(2); // target + source
});

test("the edge insertion menu offers Fusionner (transform.merge)", () => {
  const catalog: PipelineOpsCatalog = {
    "transform.merge": { kind: "transform", paramsSchema: { properties: {} } },
  };
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={catalog}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Insérer une étape sur cette arête" }));
  expect(screen.getByRole("menuitem", { name: "transform.merge" })).toBeInTheDocument();
});

test("a node present in nodeStats shows its row count as a badge", () => {
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      nodeStats={{ r1: { nodeId: "r1", op: "reader.collection", rowCount: 42 } }}
      runStatus="running"
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  expect(screen.getByText("42")).toBeInTheDocument();
});

test("the first not-yet-completed node in topological order shows a spinner while running", () => {
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      nodeStats={{}}
      runStatus="running"
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  expect(screen.getByRole("status", { name: "Exécution en cours" })).toBeInTheDocument();
});

test("no spinner is shown once the run is no longer 'running'", () => {
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      nodeStats={{}}
      runStatus="succeeded"
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  expect(screen.queryByRole("status", { name: "Exécution en cours" })).not.toBeInTheDocument();
});

test("a node with validation errors shows an error badge even when not selected", () => {
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      nodeErrors={{ r1: ["collectionId est requis."] }}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  expect(screen.getByRole("status", { name: "1 erreur(s) sur ce nœud" })).toBeInTheDocument();
});

test("a node with no validation errors shows no error badge", () => {
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      nodeErrors={{ r1: [] }}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  expect(screen.queryByText("!")).not.toBeInTheDocument();
});

test("the edge insertion menu is derived from opsCatalog, including an op not in the old hardcoded list", () => {
  const catalog: PipelineOpsCatalog = {
    "reader.collection": { kind: "reader", paramsSchema: { properties: {} } },
    "writer.collection": { kind: "writer", paramsSchema: { properties: {} } },
    "transform.swapCoordinates": {
      kind: "transform",
      paramsSchema: { properties: {}, description: "Permuter lat/lng" },
    },
  };
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={catalog}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Insérer une étape sur cette arête" }));
  expect(screen.getByRole("menuitem", { name: "transform.swapCoordinates" })).toBeInTheDocument();
  // readers/writers never appear in this menu — only transform.* ops.
  expect(screen.queryByRole("menuitem", { name: "reader.collection" })).not.toBeInTheDocument();
});

test("renders a minimap", () => {
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  expect(document.querySelector(".react-flow__minimap")).not.toBeNull();
});

test("a visible delete button on a node removes it via onNodesChange", () => {
  const onNodesChange = vi.fn();
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={onNodesChange}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Supprimer Villes" }));
  expect(onNodesChange).toHaveBeenCalledWith(NODES.filter((n) => n.id !== "r1"));
});

test("clicking the connect affordance on a node, then clicking another node, creates a primary edge between them", () => {
  const onEdgesChange = vi.fn();
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {}, title: "R" },
    { id: "t1", kind: "transform", op: "transform.filter", x: 300, y: 0, params: {}, title: "T" },
  ];
  render(
    <PipelineCanvas
      nodes={nodes}
      edges={[]}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={onEdgesChange}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Connecter depuis R" }));
  fireEvent.click(screen.getByText("T"));
  expect(onEdgesChange).toHaveBeenCalledWith([
    expect.objectContaining({ from: "r1", to: "t1", id: expect.any(String) }),
  ]);
});

test("pressing Escape cancels an in-progress connection", () => {
  const onEdgesChange = vi.fn();
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {}, title: "R" },
    { id: "t1", kind: "transform", op: "transform.filter", x: 300, y: 0, params: {}, title: "T" },
  ];
  render(
    <PipelineCanvas
      nodes={nodes}
      edges={[]}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={onEdgesChange}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      notes={[]}
      onNotesChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Connecter depuis R" }));
  fireEvent.keyDown(window, { key: "Escape" });
  fireEvent.click(screen.getByText("T"));
  expect(onEdgesChange).not.toHaveBeenCalled();
});

test("renders a canvas note and editing its label calls onNotesChange", () => {
  const onNotesChange = vi.fn();
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      notes={[{ id: "note-1", label: "Étape 1", x: 0, y: 0, width: 200, height: 120 }]}
      onNotesChange={onNotesChange}
    />,
  );
  fireEvent.change(screen.getByLabelText("Étiquette de la zone"), {
    target: { value: "Étape 1 renommée" },
  });
  expect(onNotesChange).toHaveBeenCalledWith([
    { id: "note-1", label: "Étape 1 renommée", x: 0, y: 0, width: 200, height: 120 },
  ]);
});

test("clicking a note does not call onSelectNode", () => {
  const onSelectNode = vi.fn();
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={onSelectNode}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      notes={[{ id: "note-1", label: "Étape 1", x: 0, y: 0, width: 200, height: 120 }]}
      onNotesChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByLabelText("Étiquette de la zone"));
  expect(onSelectNode).not.toHaveBeenCalled();
});

test("clicking the connect affordance on a node, then clicking a note, does not create an edge", () => {
  const onEdgesChange = vi.fn();
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {}, title: "R" },
    { id: "t1", kind: "transform", op: "transform.filter", x: 300, y: 0, params: {}, title: "T" },
  ];
  render(
    <PipelineCanvas
      nodes={nodes}
      edges={[]}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={onEdgesChange}
      onInsertOnEdge={vi.fn()}
      opsCatalog={{}}
      notes={[{ id: "note-1", label: "A note", x: 100, y: 100, width: 200, height: 120 }]}
      onNotesChange={vi.fn()}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Connecter depuis R" }));
  fireEvent.click(screen.getByLabelText("Étiquette de la zone"));
  expect(onEdgesChange).not.toHaveBeenCalled();
});
