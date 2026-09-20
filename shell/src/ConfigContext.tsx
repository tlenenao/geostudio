// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext } from "react";
import type { AppConfig } from "./config";

const ConfigContext = createContext<AppConfig | null>(null);

export function ConfigProvider({
  config,
  children,
}: {
  config: AppConfig;
  children: React.ReactNode;
}) {
  return <ConfigContext.Provider value={config}>{children}</ConfigContext.Provider>;
}

export function useConfig(): AppConfig {
  const config = useContext(ConfigContext);
  if (!config) {
    throw new Error("useConfig must be used within a ConfigProvider");
  }
  return config;
}
