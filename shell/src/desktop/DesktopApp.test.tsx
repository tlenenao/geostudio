// SPDX-License-Identifier: Apache-2.0
// Régression C1 (revue finale Vague B) : l'arbre du desktop-etl montait
// PipelineBuilderPage sous un <MemoryRouter><Routes> sans ToastProvider —
// useToast() et useBlocker() (via useDirtyGuard) levaient, l'app plantait au
// démarrage. Aucun test ni CI ne l'a vu (le workflow desktop ne se déclenche
// que sur shell/src/desktop/**). Ce test monte l'arbre réel livré par
// entry.tsx (DesktopApp), sans le bootstrap Tauri.
import { QueryClient } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ItemClient, PipelineOpsCatalog } from "../api/types";
import { t } from "../i18n";
import { DesktopApp } from "./DesktopApp";

// Même stub que PipelineBuilderPage.test.tsx : maplibre-gl appelle
// URL.createObjectURL à l'import, absent de jsdom.
vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { Map: MockMap, setWorkerUrl: () => {} };
});

vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({
    isLoading: false,
    isAuthenticated: true,
    username: "alice",
    getAccessToken: () => "t",
    signIn: vi.fn(),
    signOut: vi.fn(),
    error: null,
  }),
}));

class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

// Stubs locaux au fichier (piège n°10), jamais dans src/test/setup.ts.
beforeEach(() => {
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

const CATALOG: PipelineOpsCatalog = {};

function makeClient(): ItemClient {
  const client: Partial<ItemClient> = {
    getPipelineOps: () => Promise.resolve(CATALOG),
    listCollections: () => Promise.resolve([]),
    getPipelineRuns: vi.fn().mockResolvedValue([]),
    getInstanceInfo: () =>
      Promise.resolve({
        readOnly: false,
        etlEnabled: true,
        exportEnabled: false,
        appExportEnabled: false,
        tileset3dEnabled: false,
        terrain3dEnabled: false,
        copilotEnabled: false,
        adminToolsEnabled: false,
        quotasEnabled: false,
      }),
  };
  return client as ItemClient;
}

test("monte le builder de pipeline sans lever (ToastProvider + data router)", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(<DesktopApp client={makeClient()} queryClient={queryClient} />);
  expect(
    await screen.findByRole("heading", { name: t("pipelineBuilder.defaultTitle") }),
  ).toBeInTheDocument();
});
