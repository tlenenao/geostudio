// SPDX-License-Identifier: Apache-2.0
import type {
  ActionMessage,
  AppConfig,
  CopilotTurnResult,
  DataSource,
  ItemClient,
  Page,
  PrintLayoutConfig,
  Theme,
  Variable,
} from "../types";
import type { ItemClientBase } from "../base";

type AppsMethods = Pick<
  ItemClient,
  "getAppConfig" | "getPublicAppConfig" | "saveAppConfig" | "copilotTurn" | "getAppConfigSchema"
>;

// Le cœur accorde jusqu'à 30s à un tour de copilote (TURN_TIMEOUT_SECONDS,
// core/app/copilot/routes.py) : 30s + 5s de marge, au lieu des 15s par défaut
// de fetchWithTimeout (base.ts) qui coupaient un tour encore en cours.
export const COPILOT_TURN_TIMEOUT_MS = 35_000;

export function createAppsMethods(base: ItemClientBase): AppsMethods {
  const { request } = base;
  return {
    async getAppConfig(pk: string, mode?: "runtime"): Promise<AppConfig> {
      const qs = mode ? `?mode=${mode}` : "";
      const data = await request<{
        version?: number;
        config?: {
          kind?: "app" | "dashboard";
          theme?: Theme;
          dataSources?: DataSource[];
          messages?: ActionMessage[];
          pages?: Page[];
          variables?: Variable[];
          layout?: AppConfig["layout"] | null;
          navigationMode?: "tabs" | "story";
          interactions?: "auto" | "manual";
          printLayout?: PrintLayoutConfig | null;
        };
      }>("GET", `/configs/by-item/${pk}${qs}`);
      const c = data.config;
      if (!c?.layout) throw new Error("getAppConfig: config has no layout");
      return {
        kind: c.kind ?? "app",
        theme: c.theme ?? {},
        dataSources: c.dataSources ?? [],
        // Configs enregistrées avant P10.01 : le cœur renvoie id null/absent.
        messages: (c.messages ?? []).map((m, i) => (m.id ? m : { ...m, id: `msg-${i}` })),
        pages: c.pages,
        variables: c.variables,
        layout: c.layout,
        navigationMode: c.navigationMode,
        interactions: c.interactions,
        printLayout: c.printLayout ?? null,
        baseVersion: data.version,
      };
    },

    async getPublicAppConfig(pk: string): Promise<AppConfig> {
      const data = await request<{
        config?: {
          kind?: "app" | "dashboard";
          theme?: Theme;
          dataSources?: DataSource[];
          messages?: ActionMessage[];
          pages?: Page[];
          variables?: Variable[];
          layout?: AppConfig["layout"] | null;
          navigationMode?: "tabs" | "story";
          interactions?: "auto" | "manual";
        };
      }>("GET", `/public/configs/by-item/${encodeURIComponent(pk)}`);
      const c = data.config;
      if (!c?.layout) throw new Error("getPublicAppConfig: config has no layout");
      return {
        kind: c.kind ?? "app",
        theme: c.theme ?? {},
        dataSources: c.dataSources ?? [],
        messages: c.messages ?? [],
        pages: c.pages,
        variables: c.variables,
        layout: c.layout,
        navigationMode: c.navigationMode,
        interactions: c.interactions,
      };
    },

    async saveAppConfig(pk: string, config: AppConfig): Promise<number | undefined> {
      const saved = await request<{ version?: number }>(
        "PUT",
        `/configs/by-item/${pk}`,
        {
          version: 1,
          kind: config.kind,
          theme: config.theme,
          dataSources: config.dataSources,
          messages: config.messages,
          pages: config.pages,
          variables: config.variables,
          layout: config.layout,
          navigationMode: config.navigationMode,
          interactions: config.interactions,
          printLayout: config.printLayout ?? null,
        },
        undefined,
        config.baseVersion === undefined ? undefined : { "If-Match": `"${config.baseVersion}"` },
      );
      return saved?.version;
    },

    async copilotTurn(itemId, payload): Promise<CopilotTurnResult> {
      return request<CopilotTurnResult>(
        "POST",
        "/copilot/turn",
        { itemId, ...payload },
        COPILOT_TURN_TIMEOUT_MS,
      );
    },

    async getAppConfigSchema(): Promise<Record<string, unknown>> {
      return request<Record<string, unknown>>("GET", "/schemas/app-config");
    },
  };
}
