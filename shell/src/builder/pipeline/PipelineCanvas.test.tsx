// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { PipelineEdge, PipelineNode, PipelineOpsCatalog } from "../../api/types";
import { PipelineCanvas } from "./PipelineCanvas";

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
    />,
  );
  fireEvent.click(screen.getByText("Villes"));
  expect(onSelectNode).toHaveBeenCalledWith("r1");
});

test("the edge's insert button is present and triggers onInsertOnEdge with the edge id and a chosen op", () => {
  const onInsertOnEdge = vi.fn();
  render(
    <PipelineCanvas
      nodes={NODES}
      edges={EDGES}
      selectedNodeId={null}
      onSelectNode={vi.fn()}
      onNodesChange={vi.fn()}
      onEdgesChange={vi.fn()}
      onInsertOnEdge={onInsertOnEdge}
      opsCatalog={{}}
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Insérer une étape sur cette arête" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Filtrer" }));
  expect(onInsertOnEdge).toHaveBeenCalledWith("e1", "transform.filter");
});

test("the edge insertion menu offers the 5 spatial transform ops", () => {
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
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Insérer une étape sur cette arête" }));
  for (const label of ["Buffer", "Reprojeter", "Intersection", "Compter dans", "Agréger H3"]) {
    expect(screen.getByRole("menuitem", { name: label })).toBeInTheDocument();
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
    />,
  );
  const readerNodeEl = screen.getByText("Villes").closest(".react-flow__node")!;
  expect(readerNodeEl.querySelectorAll(".react-flow__handle").length).toBe(2); // target + source
});

test("the edge insertion menu offers Fusionner (transform.merge)", () => {
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
    />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Insérer une étape sur cette arête" }));
  expect(screen.getByRole("menuitem", { name: "Fusionner" })).toBeInTheDocument();
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
    />,
  );
  expect(screen.queryByRole("status", { name: "Exécution en cours" })).not.toBeInTheDocument();
});
