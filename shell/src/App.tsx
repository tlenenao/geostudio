// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { useMemo } from "react";
import { loadConfig } from "./config";
import { AuthProvider } from "./auth/AuthProvider";
import { useAuth } from "./auth/useAuth";
import { createItemClient } from "./api/itemClient";
import { ItemClientProvider } from "./api/ItemClientProvider";
import { AppRoutes } from "./shell/routes";

const runtimeEnv = (window as unknown as { __GEOSTUDIO_ENV__?: Record<string, string | undefined> })
  .__GEOSTUDIO_ENV__;
const config = loadConfig(
  import.meta.env as unknown as Record<string, string | undefined>,
  runtimeEnv,
);
const queryClient = new QueryClient();

// Prefers the `exportToken` query param over the normal OIDC/mock token when
// present. The Playwright export worker (Task 6, core/app/export/jobs.py)
// carries only this token, not a real Keycloak session — every API call it
// makes through the ItemClient must authenticate with it instead. Reads
// `window.location.search` directly (rather than react-router-dom's
// `useSearchParams`) because this component sits above the `BrowserRouter`
// it renders, so no Router context is available at the point `getToken` is
// constructed; the export token, like the browser URL itself, doesn't change
// without a full navigation, so a plain read at call time is equivalent and
// needs no Router.
function buildExportAwareToken(getAccessToken: () => string | undefined) {
  return () => {
    const exportToken = new URLSearchParams(window.location.search).get("exportToken");
    return exportToken ?? getAccessToken();
  };
}

function AppShell() {
  const { getAccessToken } = useAuth();
  const client = useMemo(
    () =>
      createItemClient({
        coreUrl: config.coreUrl,
        martinUrl: config.martinUrl,
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
    <AuthProvider config={config}>
      <QueryClientProvider client={queryClient}>
        <AppShell />
      </QueryClientProvider>
    </AuthProvider>
  );
}
