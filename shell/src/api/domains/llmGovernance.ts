// SPDX-License-Identifier: Apache-2.0
import type { ItemClient } from "../types";
import type { ItemClientBase } from "../base";

type Methods = Pick<
  ItemClient,
  "getLlmUsage" | "getLlmSettings" | "putLlmSettings" | "deleteLlmSettings"
>;

/** Gouvernance du LLM par tenant (L9, AUD-106/149) ; privilège settings.instance.manage. */
export function createLlmGovernanceMethods(base: ItemClientBase): Methods {
  const { request } = base;
  return {
    getLlmUsage: () => request("GET", "/copilot/usage"),
    getLlmSettings: () => request("GET", "/copilot/llm-settings"),
    putLlmSettings: (body) => request("PUT", "/copilot/llm-settings", body),
    async deleteLlmSettings() {
      await request("DELETE", "/copilot/llm-settings");
    },
  };
}
