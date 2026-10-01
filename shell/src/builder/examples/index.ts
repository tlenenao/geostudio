// SPDX-License-Identifier: Apache-2.0
import { registerCounterExampleWidget } from "./counterWidget";
import { registerCounterWcExampleWidget } from "./counterWidgetWc";

// P10.06 : les widgets d'exemple du SDK n'ont rien à faire dans la palette d'un
// créateur en production. Ils ne sont enregistrés qu'en mode d'auth « mock »
// (dev/E2E : le cœur refuse ce mode hors CORE_ENV=development).
export function registerExampleWidgets(): void {
  const runtimeEnv = (
    window as unknown as { __GEOSTUDIO_ENV__?: Record<string, string | undefined> }
  ).__GEOSTUDIO_ENV__;
  const env = import.meta.env as unknown as Record<string, string | undefined>;
  const mode = runtimeEnv?.VITE_AUTH_MODE || env.VITE_AUTH_MODE;
  if (mode !== "mock") return;
  registerCounterExampleWidget();
  registerCounterWcExampleWidget();
}
