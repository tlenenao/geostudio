// SPDX-License-Identifier: Apache-2.0
import { test, expect, vi } from "vitest";
import { resolvePipelineEditorPath } from "./resolvePipelineEditorPath";
import type { ItemClient, PipelinePayload } from "../api/types";

function fakeClient(config: PipelinePayload | (() => Promise<PipelinePayload>)): ItemClient {
  return {
    getPipelineConfig: vi.fn(async () => (typeof config === "function" ? await config() : config)),
  } as unknown as ItemClient;
}

test("route vers le wizard quand la forme du pipeline est reconnaissable", async () => {
  const wizardShaped: PipelinePayload = {
    nodes: [
      {
        id: "r1",
        kind: "reader",
        op: "reader.collection",
        x: 0,
        y: 0,
        params: { collectionId: "c1" },
      },
      { id: "w1", kind: "writer", op: "writer.dataset", x: 100, y: 0, params: {} },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const path = await resolvePipelineEditorPath(fakeClient(wizardShaped), "pl-1");
  expect(path).toBe("/datasets/visual-query/pl-1/edit");
});

test("route vers le DAG complet quand la forme n'est pas reconnaissable par le wizard", async () => {
  const handEdited: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.connector.rest", x: 0, y: 0, params: {} },
      { id: "w1", kind: "writer", op: "writer.dataset", x: 100, y: 0, params: {} },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const path = await resolvePipelineEditorPath(fakeClient(handEdited), "pl-2");
  expect(path).toBe("/pipelines/pl-2/edit");
});

test("retombe sur le DAG complet si la récupération de la config échoue", async () => {
  const path = await resolvePipelineEditorPath(
    fakeClient(() => Promise.reject(new Error("network"))),
    "pl-3",
  );
  expect(path).toBe("/pipelines/pl-3/edit");
});
