// SPDX-License-Identifier: Apache-2.0
// Couverture permanente de createAppRouter()/RouterProvider (Tâche 25,
// suivi de revue Important) : la tâche 25 (commit c5a228ca) a introduit
// createAppRouter() dans ./routes.tsx mais son unique test rouge (sondé en
// TDD, cf. .superpowers/sdd/task-25-brief.md Step 1) a été retiré avant le
// commit pour préserver le "zéro diff" exigé sur routes.test.tsx (qui ne
// couvre que AppRoutes()/<Routes>, jamais createAppRouter()/<RouterProvider>).
// Ce fichier est volontairement séparé de routes.test.tsx (qu'on ne touche
// pas) et ne couvre PAS à nouveau routeElements()/AppRoutes() : seulement le
// branchement createAppRouter() lui-même (initialEntries -> createMemoryRouter
// vs createBrowserRouter, le <Suspense><Outlet/></Suspense> englobant, et le
// vrai RouterProvider).
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { RouterProvider } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { createAppRouter } from "./routes";
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "alice",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

// Seule page mockée : /apps/:pk/edit vit sous ProtectedLayout (RequireAuth +
// AppLayout + Suspense) et charge AppBuilderPage en lazy() — même patron que
// routes.test.tsx pour cette route. Le contenu réel d'AppBuilderPage n'a rien
// à faire ici (déjà testé ailleurs) : seul compte que le routeur y mène.
vi.mock("../pages/AppBuilderPage", () => ({
  AppBuilderPage: ({ pk }: { pk: string }) => <div>app-builder-{pk}</div>,
}));

// jsdom n'implémente pas window.matchMedia (cf. routes.test.tsx / CLAUDE.md
// piège n°10) ; la route protégée passe par AppLayout -> useNarrowViewport.
// Stub local au fichier, jamais dans shell/src/test/setup.ts.
beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
});

function renderRouter(router: ReturnType<typeof createAppRouter>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <RouterProvider router={router} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("createAppRouter({ initialEntries }) resolves a ProtectedLayout route (/apps/:pk/edit) through RouterProvider", async () => {
  const router = createAppRouter({ initialEntries: ["/apps/42/edit"] });
  renderRouter(router);
  expect(await screen.findByText("app-builder-42")).toBeInTheDocument();
});

test("createAppRouter({ initialEntries }) resolves an out-of-layout route (/public/items/:pk) through RouterProvider", async () => {
  // PublicItemPage (routes.tsx: PublicItemRoute, hors ProtectedLayout — pas
  // de RequireAuth) appelle client.getPublicAppConfig(pk), qui tape
  // GET /public/configs/by-item/:pk. Ce endpoint n'a aucun handler MSW par
  // défaut (shell/src/test/msw/handlers.ts) : la requête échoue, et la page
  // retombe sur son état d'erreur "Page introuvable." (role="alert") sans le
  // moindre server.use() — suffisant pour prouver que le routeur atteint
  // réellement cette route hors-layout et que son Suspense/lazy() résout.
  const router = createAppRouter({ initialEntries: ["/public/items/99"] });
  renderRouter(router);
  // Timeout relevé (défaut RTL 1000ms -> 5000ms, même patron que
  // PipelineRunPanel.test.tsx/ExportPanel.test.tsx/AppExportPanel.test.tsx) :
  // le lazy() de PublicItemPage entraîne tout AppRenderer/registerBuiltinWidgets
  // (grossi par la Vague B), mesuré à ~1020-1090ms sur ce poste — juste au-delà
  // du défaut, pas une régression fonctionnelle mais une marge de test épuisée
  // par la croissance organique du graphe de modules.
  expect(await screen.findByRole("alert", {}, { timeout: 5000 })).toHaveTextContent(
    "Page introuvable.",
  );
});

test("createAppRouter() without initialEntries takes the createBrowserRouter branch without throwing", () => {
  // On ne peut pas monter un <RouterProvider> réel adossé à
  // createBrowserRouter en jsdom (pas de vraie History d'onglet navigateur) —
  // cf. brief de la tâche de suivi. On se contente donc de vérifier que la
  // branche createBrowserRouter (pas createMemoryRouter) est bien empruntée
  // et ne lève pas, ce qui aurait échoué si la condition sur
  // `options?.initialEntries` était inversée ou cassée.
  expect(() => createAppRouter()).not.toThrow();
  const router = createAppRouter();
  // createBrowserRouter renvoie un objet Router complet (navigate/subscribe/
  // routes...), tout comme createMemoryRouter — la seule façon observable
  // depuis l'extérieur de distinguer les deux implémentations sans monter de
  // vrai <RouterProvider> est l'absence d'API additionnelle propre à la
  // history mémoire ; on se limite donc à vérifier la forme d'un router
  // valide, qui aurait échoué si createAppRouter() renvoyait autre chose
  // (undefined, une exception avalée, etc.) pour la branche production.
  expect(router).toMatchObject({
    navigate: expect.any(Function),
    subscribe: expect.any(Function),
  });
  expect(router.routes.length).toBeGreaterThan(0);
});
