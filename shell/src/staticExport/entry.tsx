// SPDX-License-Identifier: Apache-2.0
// Point d'entrée Vite du bundle d'export (SP-18a Statique + SP-18b
// Connecté) : un seul runtime prébâti pour les deux modes, mode détecté au
// chargement par la présence de geostudio-connection.json (core/app/
// appexport/bundler.py). Jamais de redirection OIDC ici — enableMockAuth()
// avant le premier rendu, dans les deux modes : AppRenderer appelle
// useAuth() (via ActionConditionBridge) et ce hook lit `mockMode` avant de
// toucher react-oidc-context, qui lèverait sinon faute d'<AuthProvider>
// ancêtre — INDÉPENDANT du getToken passé à createItemClient ci-dessous.
//
// Piège découvert en conception SP-18b, à ne pas réintroduire :
// enableMockAuth() fait retourner "mock-token" à useAuth().getAccessToken —
// si ce token était câblé dans createItemClient's getToken, chaque requête
// anonyme casserait (get_current_user_optional traite tout Authorization
// présent comme "doit être valide", jamais de repli anonyme sur un token
// invalide). Le getToken du mode Connecté est donc un () => undefined
// codé en dur, jamais relié à useAuth().
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { enableMockAuth } from "../auth/useAuth";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { createStaticItemClient } from "./StaticItemClient";
import type { AppConfig, ItemClient } from "../api/types";
import "../index.css";

enableMockAuth();
registerBuiltinWidgets();
// DataContext (builder/DataContext.tsx) appelle useQueries (@tanstack/react-query),
// tout comme App.tsx en mode normal — sans ce provider, tout widget de données
// (table/list/chart/…) fait planter React avec "No QueryClient set" avant même
// le premier rendu, indépendamment du choix de widget.
const queryClient = new QueryClient();

async function loadConnection(): Promise<{ coreUrl: string } | null> {
  const response = await fetch("./geostudio-connection.json");
  if (!response.ok) return null;
  return (await response.json()) as { coreUrl: string };
}

function buildClient(config: AppConfig, connection: { coreUrl: string } | null): ItemClient {
  if (connection) {
    return createItemClient({ coreUrl: connection.coreUrl, getToken: () => undefined });
  }
  return createStaticItemClient(config);
}

async function bootstrap() {
  const root = document.getElementById("root");
  if (!root) throw new Error("export entry: #root introuvable");
  const response = await fetch("./geostudio-app-config.json");
  if (!response.ok) throw new Error("export entry: geostudio-app-config.json introuvable");
  const config = (await response.json()) as AppConfig;
  const connection = await loadConnection();
  const client = buildClient(config, connection);
  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <div className="h-screen w-screen">
            {/* No `pageId`/`onNavigate` here: leaving `pageId` undefined lets
                AppRenderer's own internal state drive navigation (nav
                widgets, tabs, story mode) — a fixed `pageId` prop pins the
                active page forever since it always wins over internal state
                (SP-18a review, C3). */}
            <AppRenderer config={config} mode="runtime" />
          </div>
        </ItemClientProvider>
      </QueryClientProvider>
    </StrictMode>,
  );
}

bootstrap().catch((err) => {
  const root = document.getElementById("root");
  if (root) root.textContent = `Erreur de chargement : ${(err as Error).message}`;
});
