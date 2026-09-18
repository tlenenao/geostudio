// SPDX-License-Identifier: Apache-2.0
// Point d'entrée Vite du desktop-etl (Phase G, plan Tâche 5). Réutilise
// PipelineBuilderPage tel quel (aucun fichier de builder/pipeline/ modifié)
// derrière un MemoryRouter à 2 routes au lieu du BrowserRouter+AppRoutes
// complet d'App.tsx — ce produit n'a qu'un seul écran.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Routes, Route, useParams } from "react-router-dom";
import { invoke } from "@tauri-apps/api/core";
import { enableMockAuth } from "../auth/useAuth";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { createDesktopItemClient } from "./DesktopItemClient";
import { PipelineBuilderPage } from "../pages/PipelineBuilderPage";
import "../index.css";

enableMockAuth();
const queryClient = new QueryClient();

function NewPipelineRoute() {
  return <PipelineBuilderPage pk={null} initialTitle="Nouveau pipeline" />;
}

function EditPipelineRoute() {
  const { pk } = useParams();
  return <PipelineBuilderPage pk={pk!} />;
}

async function bootstrap() {
  const root = document.getElementById("root");
  if (!root) throw new Error("desktop entry: #root introuvable");

  const connection = await invoke<{ baseUrl: string; token: string }>("get_sidecar_connection");
  const client = createDesktopItemClient(connection);

  createRoot(root).render(
    <StrictMode>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <MemoryRouter initialEntries={["/pipelines/new"]}>
            <Routes>
              <Route path="/pipelines/new" element={<NewPipelineRoute />} />
              <Route path="/pipelines/:pk/edit" element={<EditPipelineRoute />} />
            </Routes>
          </MemoryRouter>
        </ItemClientProvider>
      </QueryClientProvider>
    </StrictMode>,
  );
}

bootstrap().catch((err) => {
  const root = document.getElementById("root");
  if (root) root.textContent = `Erreur de démarrage : ${(err as Error).message}`;
});
