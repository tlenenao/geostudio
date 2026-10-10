// SPDX-License-Identifier: Apache-2.0
// Point d'entrée Vite du desktop-etl (Phase G, plan Tâche 5). Réutilise
// PipelineBuilderPage tel quel (aucun fichier de builder/pipeline/ modifié)
// derrière un data router mémoire à 2 routes (DesktopApp.tsx) au lieu du
// routeur complet d'App.tsx — ce produit n'a qu'un seul écran.
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient } from "@tanstack/react-query";
import { invoke } from "@tauri-apps/api/core";
import { enableMockAuth } from "../auth/useAuth";
import { createDesktopItemClient } from "./DesktopItemClient";
import { DesktopApp } from "./DesktopApp";
import "../index.css";
import { t } from "../i18n";
import "../i18n/domains/misc";

enableMockAuth();
const queryClient = new QueryClient();

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
      <DesktopApp client={client} queryClient={queryClient} />
    </StrictMode>,
  );
}

bootstrap().catch((err) => {
  const root = document.getElementById("root");
  const message = err instanceof Error ? err.message : String(err);
  if (root) root.textContent = t("desktop.startupError", { message });
});
