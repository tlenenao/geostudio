// SPDX-License-Identifier: Apache-2.0
// Point d'entrée Vite du bundle "export statique" (SP-18a) : démarre l'app
// avec zéro backend GeoStudio, la config gelée étant embarquée à côté de ce
// bundle (core/app/appexport/bundler.py). Jamais de redirection OIDC ici —
// il n'y a pas de cœur à authentifier contre — d'où enableMockAuth() avant
// le premier rendu : AppRenderer appelle useAuth() (via ActionConditionBridge)
// et ce hook lit `mockMode` avant de toucher react-oidc-context, qui
// lèverait sinon faute d'<AuthProvider> ancêtre.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { enableMockAuth } from "../auth/useAuth";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { createStaticItemClient } from "./StaticItemClient";
import type { AppConfig } from "../api/types";
import "../index.css";

enableMockAuth();
registerBuiltinWidgets();
// DataContext (builder/DataContext.tsx) appelle useQueries (@tanstack/react-query),
// tout comme App.tsx en mode normal — sans ce provider, tout widget de données
// (table/list/chart/…) fait planter React avec "No QueryClient set" avant même
// le premier rendu, indépendamment du choix de widget.
const queryClient = new QueryClient();

async function bootstrap() {
  const root = document.getElementById("root");
  if (!root) throw new Error("export entry: #root introuvable");
  const response = await fetch("./geostudio-app-config.json");
  if (!response.ok) throw new Error("export entry: geostudio-app-config.json introuvable");
  const config = (await response.json()) as AppConfig;
  const client = createStaticItemClient(config);
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
