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
  // Pas de initialTitle : PipelineBuilderPage retombe déjà sur
  // t("pipelineBuilder.defaultTitle") en son absence (voir
  // PipelineBuilderPage.tsx:187) — inutile de dupliquer la chaîne ici en
  // dur (trouvé par le linter i18n, revue finale de branche, Tâche 8).
  return <PipelineBuilderPage pk={null} />;
}

function EditPipelineRoute() {
  const { pk } = useParams();
  return <PipelineBuilderPage pk={pk!} />;
}

// La poignée `.setup()` de main.rs (Rust) peuple SidecarState de façon
// asynchrone après le spawn du sidecar — le premier invoke() de la webview
// arrive presque toujours avant, et rejette avec la chaîne brute
// "sidecar not ready yet" (Result<T, String> Tauri : rejet en chaîne, pas
// en Error). Course confirmée réelle sur la VM Windows (Tâche 6) : sans
// retry, écran "Erreur de démarrage : undefined" ((err as Error).message
// sur une chaîne vaut undefined) à chaque lancement.
// 10s suffit largement sur une machine de dev déjà "chaude", mais un
// binaire PyInstaller onefile (~124 Mo) s'extrait dans un dossier temp à
// CHAQUE lancement, et un binaire fraîchement construit/téléchargé peut
// être scanné par l'antivirus avant sa première exécution -- démontré
// réel en CI (Tâche 8) : "Erreur de démarrage : sidecar not ready yet" à
// chaque run sur un runner Windows tout frais, alors que la même app
// démarre en moins d'une seconde sur une machine déjà utilisée. 45s
// couvre ce cas sans pénaliser le cas rapide (le retry sort dès que le
// sidecar répond, jamais après un délai fixe).
async function getSidecarConnectionWithRetry(
  timeoutMs = 45_000,
  intervalMs = 150,
): Promise<{ baseUrl: string; token: string }> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown;
  while (Date.now() < deadline) {
    try {
      return await invoke<{ baseUrl: string; token: string }>("get_sidecar_connection");
    } catch (err) {
      lastError = err;
      await new Promise((resolve) => setTimeout(resolve, intervalMs));
    }
  }
  throw lastError instanceof Error ? lastError : new Error(String(lastError));
}

async function bootstrap() {
  const root = document.getElementById("root");
  if (!root) throw new Error("desktop entry: #root introuvable");

  const connection = await getSidecarConnectionWithRetry();
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
  const message = err instanceof Error ? err.message : String(err);
  if (root) root.textContent = `Erreur de démarrage : ${message}`;
});
