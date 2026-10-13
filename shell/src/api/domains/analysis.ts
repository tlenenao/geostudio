// SPDX-License-Identifier: Apache-2.0
// ARC-25 : outils d'analyse spatiale (op de pipeline exécutées sur un dataset).
import type { AnalysisRequest, AnalysisResult, AnalysisTool, ItemClient } from "../types";
import type { ItemClientBase } from "../base";

type AnalysisMethods = Pick<ItemClient, "listAnalysisTools" | "runAnalysis">;

export function createAnalysisMethods(base: Pick<ItemClientBase, "request">): AnalysisMethods {
  return {
    async listAnalysisTools(): Promise<AnalysisTool[]> {
      const body = await base.request<{ tools: AnalysisTool[] }>("GET", "/analysis/tools");
      return body.tools;
    },
    async runAnalysis(collectionId: string, body: AnalysisRequest): Promise<AnalysisResult> {
      return base.request<AnalysisResult>(
        "POST",
        `/collections/${encodeURIComponent(collectionId)}/analysis`,
        body,
      );
    },
  };
}
