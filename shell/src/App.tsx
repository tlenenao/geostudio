// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import { useMemo } from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { loadConfig } from "./config";
import { ConfigProvider } from "./ConfigContext";
import { AuthProvider } from "./auth/AuthProvider";
import { useAuth } from "./auth/useAuth";
import { buildExportAwareToken } from "./auth/exportAwareToken";
import { createItemClient } from "./api/itemClient";
import { ItemClientProvider } from "./api/ItemClientProvider";
import { createAppRouter } from "./shell/routes";
import { AppErrorBoundary } from "./AppErrorBoundary";
// Import direct (pas le barrel ui/kit) : le barrel tire les ~40 primitives du
// kit dans le chunk initial (revue finale Vague B, REV-253).
import { ToastProvider } from "./ui/kit/ToastProvider";
import { ConnectivityBanner } from "./shell/ConnectivityBanner";

const runtimeEnv = (window as unknown as { __GEOSTUDIO_ENV__?: Record<string, string | undefined> })
  .__GEOSTUDIO_ENV__;
const config = loadConfig(
  import.meta.env as unknown as Record<string, string | undefined>,
  runtimeEnv,
);
// SP-B7 (étape 6) : borne le retry par défaut de React Query à 1 (2 appels
// fetch au total) au lieu de 3 (4 appels, backoff exponentiel) — sans ce
// réglage, le timeout de 15s de fetchWithTimeout (base.ts) se multiplierait
// par le retry par défaut avant qu'une query ne se stabilise en erreur,
// retardant l'apparition de ConnectivityBanner de ~45s+ sur une vraie panne
// cœur. Exporté (plutôt que privé au module) pour être testable
// directement depuis App.test.tsx sans avoir à monter <App /> en entier
// (ce qui nécessiterait des variables d'environnement de config absentes
// de l'environnement de test).
export const queryClient = new QueryClient({ defaultOptions: { queries: { retry: 1 } } });

// Data router (Task 25/SP-B6a) : créé une seule fois au niveau module, comme
// queryClient ci-dessus — jamais recréé aux rendus de AppShell, sinon chaque
// re-render de AppShell (ex: getAccessToken qui change) réinitialiserait la
// navigation. Nécessaire pour useBlocker (Task 26, data router uniquement).
const router = createAppRouter();

function AppShell() {
  const { getAccessToken } = useAuth();
  const client = useMemo(
    () =>
      createItemClient({
        coreUrl: config.coreUrl,
        getToken: buildExportAwareToken(getAccessToken),
      }),
    [getAccessToken],
  );
  return (
    <ItemClientProvider client={client}>
      <RouterProvider router={router} />
    </ItemClientProvider>
  );
}

export default function App() {
  return (
    <ToastPrimitive.Provider>
      <ToastProvider>
        <TooltipPrimitive.Provider>
          <AppErrorBoundary>
            <AuthProvider config={config}>
              <QueryClientProvider client={queryClient}>
                <ConfigProvider config={config}>
                  <ConnectivityBanner />
                  <AppShell />
                </ConfigProvider>
              </QueryClientProvider>
            </AuthProvider>
          </AppErrorBoundary>
        </TooltipPrimitive.Provider>
      </ToastProvider>
      <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2 outline-none" />
    </ToastPrimitive.Provider>
  );
}
