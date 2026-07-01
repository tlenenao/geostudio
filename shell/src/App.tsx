import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { useMemo } from "react";
import { loadConfig } from "./config";
import { AuthProvider } from "./auth/AuthProvider";
import { useAuth } from "./auth/useAuth";
import { RequireAuth } from "./auth/RequireAuth";
import { createItemClient } from "./api/itemClient";
import { ItemClientProvider } from "./api/ItemClientProvider";
import { AppLayout } from "./shell/AppLayout";
import { AppRoutes } from "./shell/routes";

const config = loadConfig(import.meta.env as unknown as Record<string, string | undefined>);
const queryClient = new QueryClient();

function AuthedApp() {
  const { getAccessToken } = useAuth();
  const client = useMemo(
    () =>
      createItemClient({
        geonodeUrl: config.geonodeUrl,
        builderUrl: config.builderUrl,
        getToken: getAccessToken,
      }),
    [getAccessToken],
  );
  return (
    <ItemClientProvider client={client}>
      <BrowserRouter>
        <AppLayout>
          <AppRoutes />
        </AppLayout>
      </BrowserRouter>
    </ItemClientProvider>
  );
}

export default function App() {
  return (
    <AuthProvider config={config}>
      <QueryClientProvider client={queryClient}>
        <RequireAuth>
          <AuthedApp />
        </RequireAuth>
      </QueryClientProvider>
    </AuthProvider>
  );
}
