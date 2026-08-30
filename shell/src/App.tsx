// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { useMemo } from "react";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { loadConfig } from "./config";
import { AuthProvider } from "./auth/AuthProvider";
import { useAuth } from "./auth/useAuth";
import { buildExportAwareToken } from "./auth/exportAwareToken";
import { createItemClient } from "./api/itemClient";
import { ItemClientProvider } from "./api/ItemClientProvider";
import { AppRoutes } from "./shell/routes";
import { AppErrorBoundary } from "./AppErrorBoundary";

const runtimeEnv = (window as unknown as { __GEOSTUDIO_ENV__?: Record<string, string | undefined> })
  .__GEOSTUDIO_ENV__;
const config = loadConfig(
  import.meta.env as unknown as Record<string, string | undefined>,
  runtimeEnv,
);
const queryClient = new QueryClient();

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
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ItemClientProvider>
  );
}

export default function App() {
  return (
    <ToastPrimitive.Provider>
      <TooltipPrimitive.Provider>
        <AppErrorBoundary>
          <AuthProvider config={config}>
            <QueryClientProvider client={queryClient}>
              <AppShell />
            </QueryClientProvider>
          </AuthProvider>
        </AppErrorBoundary>
      </TooltipPrimitive.Provider>
      <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2 outline-none" />
    </ToastPrimitive.Provider>
  );
}
