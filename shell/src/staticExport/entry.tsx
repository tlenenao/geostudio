// SPDX-License-Identifier: Apache-2.0
// Point d'entrée Vite du bundle d'export (SP-18a Statique + SP-18b
// Connecté) : un seul runtime prébâti pour les deux modes, mode détecté au
// chargement par la présence de geostudio-connection.json (core/app/
// appexport/bundler.py). En mode Connecté uniquement, les extensions
// tierces actives sont récupérées et enregistrées avant le premier rendu
// (miroir d'AppRuntimePage.tsx) — un widget tiers charge son JS depuis sa
// propre origine, comme dans le shell normal ; le mode Statique n'a rien à
// enregistrer (StaticItemClient ne le supporte pas). Jamais de redirection
// OIDC ici — enableMockAuth()
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
import { registerExtensionWidget } from "../builder/extensions/registerExtensionWidget";
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
  // Defensive by construction (review finding I1/M5): a Statique bundle has
  // no geostudio-connection.json, so a plain static host 404s and `!ok`
  // correctly falls back to Statique. But this bundle is a client-routed
  // SPA meant for arbitrary static hosts, and many of them (nginx
  // `try_files … /index.html`, Netlify's `/* /index.html 200`, Firebase
  // Hosting's SPA rewrite) answer *every* unmatched path with a 200 serving
  // index.html — `response.json()` would then throw on the HTML body,
  // propagate out of bootstrap(), and break the already-shipped Statique
  // mode on those hosts. Any fetch/parse failure, or a payload that
  // doesn't actually look like { coreUrl: string }, is treated the same as
  // "no connection file": fall back to Statique.
  try {
    const response = await fetch("./geostudio-connection.json");
    if (!response.ok) return null;
    const data: unknown = await response.json();
    if (
      typeof data === "object" &&
      data !== null &&
      "coreUrl" in data &&
      typeof (data as { coreUrl: unknown }).coreUrl === "string" &&
      (data as { coreUrl: string }).coreUrl !== ""
    ) {
      return data as { coreUrl: string };
    }
    return null;
  } catch {
    return null;
  }
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
  if (connection) {
    // Connecté mode only (SP-18b review finding I2): the export guard
    // (core/app/appexport/guard.py) allows third-party widgets in this
    // mode on the premise that they load their JS from their own origin —
    // but nothing here ever registered them until now. StaticItemClient
    // doesn't support listActiveExtensions and doesn't need to: nothing
    // extension-related can be bundled statically.
    //
    // Tolérant par construction (SP-18b re-review, fix round 2) : un échec
    // de `listActiveExtensions()` (404, réseau, CORS…) ne doit jamais faire
    // échouer tout le bootstrap — les widgets builtin doivent quand même
    // s'afficher même si le catalogue d'extensions est indisponible.
    try {
      (await client.listActiveExtensions()).forEach(registerExtensionWidget);
    } catch {
      // Extensions indisponibles : on continue sans elles.
    }
  }
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
