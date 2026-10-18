// SPDX-License-Identifier: Apache-2.0
// D58 : un pipeline créé par le wizard no-code (SP-14o) doit se rouvrir
// dans le wizard s'il est toujours dans une forme qu'il sait relire, et
// dans le DAG complet sinon — jamais l'inverse systématique d'avant. Point
// d'entrée unique appelé par useOpenItem.ts ET ItemDetailRoute
// (routes.tsx) : évite la duplication qui avait laissé les deux dispatchers
// hardcoder /pipelines/{pk}/edit indépendamment (piège CLAUDE.md n°4).
import type { ItemClient } from "../api/types";

export async function resolvePipelineEditorPath(client: ItemClient, pk: string): Promise<string> {
  try {
    // import dynamique : le décompilateur du wizard n'a pas à peser sur la charge initiale.
    const { decompilePipelineToWizardState } =
      await import("../builder/visualQuery/compilePipeline");
    const config = await client.getPipelineConfig(pk);
    const wizardState = decompilePipelineToWizardState(config);
    return wizardState !== null ? `/datasets/visual-query/${pk}/edit` : `/pipelines/${pk}/edit`;
  } catch {
    return `/pipelines/${pk}/edit`;
  }
}
