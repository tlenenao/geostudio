// SPDX-License-Identifier: Apache-2.0
import { usePipelineOps } from "../../api/hooks";
import type { PipelineNodeKind } from "../../api/types";

export const PIPELINE_OP_DND_TYPE = "application/x-geostudio-pipeline-op";

const SECTION_LABEL: Record<PipelineNodeKind, string> = {
  reader: "Sources",
  transform: "Transforms",
  writer: "Écritures",
};

export function PipelinePalette() {
  const opsQuery = usePipelineOps();
  const catalog = opsQuery.data ?? {};
  const byKind: Record<PipelineNodeKind, string[]> = { reader: [], transform: [], writer: [] };
  for (const [op, entry] of Object.entries(catalog)) byKind[entry.kind].push(op);

  return (
    <div className="flex flex-col gap-3 p-2 text-xs">
      {(["reader", "transform", "writer"] as const).map((kind) => (
        <div key={kind}>
          <h3 className="mb-1 font-semibold text-ink-2">{SECTION_LABEL[kind]}</h3>
          <ul className="flex flex-col gap-1">
            {byKind[kind].map((op) => (
              <li key={op}>
                <div
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData(PIPELINE_OP_DND_TYPE, op);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  className="cursor-grab rounded border border-rule bg-surface px-2 py-1 hover:bg-sunken"
                >
                  {op}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
