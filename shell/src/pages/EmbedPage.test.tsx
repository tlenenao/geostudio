// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";
import { server } from "../test/msw/server";
import { enableMockAuth } from "../auth/useAuth";

// EmbedPage.tsx appelle loadConfig() (comme App.tsx) au chargement du
// module, hors de tout composant — dans l'app réelle, ces variables
// viennent du build Vite/de l'injection runtime (__GEOSTUDIO_ENV__) et sont
// déjà présentes bien avant que cette route lazy() ne soit atteinte. En test
// unitaire, ce module est importé isolément : il faut stuber
// `import.meta.env` avant l'import (donc un `import()` dynamique après
// `vi.stubEnv`, pas un `import` statique — les imports statiques sont
// hoistés avant tout code du fichier, y compris un `vi.stubEnv` placé
// au-dessus). VITE_AUTH_MODE=mock évite d'avoir à fournir les 3 variables
// OIDC (cf. config.test.ts::"mock mode does not require oidc vars").
vi.stubEnv("VITE_CORE_URL", "https://core.test");
vi.stubEnv("VITE_AUTH_MODE", "mock");
// AppRenderer (utilisé par EmbedPage pour une ressource app/dashboard)
// appelle useAuth() sans condition via son ActionConditionBridge — dans
// l'app réelle, /embed/:token vit sous le même <AuthProvider> racine que le
// reste du shell (App.tsx enveloppe TOUTES les routes, protégées ou non, cf.
// routes.tsx) donc le contexte react-oidc-context existe toujours, même non
// authentifié. Ici, EmbedPage est monté seul, sans AuthProvider : sans
// enableMockAuth(), useOidcAuth() lève (pas de contexte), trouvaille réelle
// absente du texte du brief (piège CLAUDE.md n°3), même classe que
// useMcpToken.test.tsx (cf. commentaire ci-dessous sur l'ordre
// import/enableMockAuth).
enableMockAuth();
const { EmbedPage } = await import("./EmbedPage");

function renderWithClient(token: string) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <EmbedPage token={token} />
    </QueryClientProvider>,
  );
}

test("shows an explicit message for a non app/dashboard resource type", async () => {
  server.use(
    http.get("https://core.test/v1/share-links/tok-map", () =>
      HttpResponse.json({
        itemId: "map-1",
        title: "Carte",
        resourceType: "map",
        expiresAt: "2026-10-01",
      }),
    ),
  );
  renderWithClient("tok-map");
  expect(await screen.findByText(/ne peut pas être intégré/i)).toBeInTheDocument();
});

test("shows an explicit message for an invalid or expired token", async () => {
  server.use(
    http.get("https://core.test/v1/share-links/bad", () =>
      HttpResponse.json({ detail: "invalid or expired share link" }, { status: 401 }),
    ),
  );
  renderWithClient("bad");
  expect(await screen.findByText(/expiré ou révoqué/i)).toBeInTheDocument();
});

test("renders the App via AppRenderer for a valid app token, sending only the share-link header", async () => {
  let sawAuthorization = false;
  let sawShareHeader = false;
  server.use(
    http.get("https://core.test/v1/share-links/tok-app", () =>
      HttpResponse.json({
        itemId: "app-1",
        title: "Mon App",
        resourceType: "app",
        expiresAt: "2026-10-01",
      }),
    ),
    http.get("https://core.test/v1/configs/by-item/app-1", ({ request }) => {
      sawAuthorization = request.headers.get("authorization") !== null;
      sawShareHeader = request.headers.get("x-share-link-token") === "tok-app";
      return HttpResponse.json({
        config: {
          kind: "app",
          theme: {},
          dataSources: [],
          messages: [],
          layout: { type: "grid", items: [] },
        },
      });
    }),
  );
  renderWithClient("tok-app");
  // Le brief prévoyait un `setTimeout(0)` arbitraire ici pour laisser les deux
  // requêtes en cascade (résolution du lien, puis config de l'app) se
  // terminer — piège CLAUDE.md n°10 : attendre directement, via `waitFor`,
  // que le handler de config ait effectivement vu passer la requête et posé
  // les deux booléens, plutôt qu'un délai fixe qui ne prouve rien sur la
  // machine de CI. Vérifié par falsification (voir task-12-report.md) :
  // sans `getShareLinkToken` câblé sur l'ItemClient de l'embed, ce `waitFor`
  // échoue bien en timeout au lieu de passer silencieusement.
  await waitFor(() => {
    expect(sawShareHeader).toBe(true);
  });
  expect(sawAuthorization).toBe(false);
});
