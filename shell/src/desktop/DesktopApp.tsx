// SPDX-License-Identifier: Apache-2.0
// Arbre React du desktop-etl, extrait d'entry.tsx (qui garde le bootstrap
// Tauri/sidecar) pour être montable tel quel en test : entry.tsx exécute
// bootstrap() à l'import, ce fichier-ci n'a aucun effet de bord.
//
// Data router (createMemoryRouter + RouterProvider) et pile ToastProvider
// OBLIGATOIRES : PipelineBuilderPage appelle useToast() (lève sans
// ToastProvider ancêtre) et, via useDirtyGuard, useBlocker() (lève hors
// data router). L'ancien <MemoryRouter><Routes> sans ToastProvider faisait
// planter l'app au démarrage (revue finale Vague B, C1) — même composition
// que App.tsx.
import type { QueryClient } from "@tanstack/react-query";
import { QueryClientProvider } from "@tanstack/react-query";
import { useState } from "react";
import { createMemoryRouter, RouterProvider, useParams } from "react-router-dom";
import * as ToastPrimitive from "@radix-ui/react-toast";
import type { ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
// Import direct (pas le barrel ui/kit) : le barrel embarque tout le kit
// dans le chunk d'entrée (revue finale Vague B, I3).
import { ToastProvider } from "../ui/kit/ToastProvider";
import { PipelineBuilderPage } from "../pages/PipelineBuilderPage";

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

export function createDesktopRouter(initialEntries: string[] = ["/pipelines/new"]) {
  return createMemoryRouter(
    [
      { path: "/pipelines/new", element: <NewPipelineRoute /> },
      { path: "/pipelines/:pk/edit", element: <EditPipelineRoute /> },
    ],
    { initialEntries },
  );
}

export function DesktopApp({
  client,
  queryClient,
  initialEntries,
}: {
  client: ItemClient;
  queryClient: QueryClient;
  initialEntries?: string[];
}) {
  // Routeur créé une seule fois par montage (jamais recréé aux re-rendus,
  // sinon la navigation serait réinitialisée).
  const [router] = useState(() => createDesktopRouter(initialEntries));
  return (
    <ToastPrimitive.Provider>
      <ToastProvider>
        <QueryClientProvider client={queryClient}>
          <ItemClientProvider client={client}>
            <RouterProvider router={router} />
          </ItemClientProvider>
        </QueryClientProvider>
      </ToastProvider>
      <ToastPrimitive.Viewport className="fixed bottom-4 right-4 z-[100] flex w-80 flex-col gap-2 outline-none" />
    </ToastPrimitive.Provider>
  );
}
