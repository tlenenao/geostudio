// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AdminExtensionsPage } from "./AdminExtensionsPage";

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. Stub local, avec vi.unstubAllGlobals()
// en afterEach dès son introduction (même patron que SqlLabPage.test.tsx,
// SP-30i).
function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
}

beforeEach(() => stubMatchMedia(false));
afterEach(() => vi.unstubAllGlobals());

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <AdminExtensionsPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("lists extensions (including disabled) and toggles enabled via PATCH", async () => {
  let patchedBody: unknown;
  server.use(
    http.get("https://core.test/extensions", ({ request }) => {
      expect(new URL(request.url).searchParams.get("all")).toBe("true");
      return HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge",
            tag: "gauge-extension-widget",
            label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [],
            events: [],
            actions: [],
            defaultSize: { w: 2, h: 2 },
            permissions: { collections: "all" },
            enabled: false,
          },
        ],
      });
    }),
    http.patch("https://core.test/extensions/acme.gauge", async ({ request }) => {
      patchedBody = await request.json();
      return HttpResponse.json({ id: "acme.gauge", enabled: true });
    }),
  );
  render(<Harness />);
  const toggle = await screen.findByRole("checkbox", { name: "Actif : Jauge (extension)" });
  expect(toggle).not.toBeChecked();
  await userEvent.click(toggle);
  await waitFor(() => expect(patchedBody).toEqual({ enabled: true }));
});

test("surfaces an alert when the PATCH to toggle an extension fails", async () => {
  server.use(
    http.get("https://core.test/extensions", () =>
      HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge",
            tag: "gauge-extension-widget",
            label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [],
            events: [],
            actions: [],
            defaultSize: { w: 2, h: 2 },
            permissions: { collections: "all" },
            enabled: false,
          },
        ],
      }),
    ),
    http.patch("https://core.test/extensions/acme.gauge", () =>
      HttpResponse.json({}, { status: 500 }),
    ),
  );
  render(<Harness />);
  const toggle = await screen.findByRole("checkbox", { name: "Actif : Jauge (extension)" });
  await userEvent.click(toggle);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Échec de la mise à jour de l'extension."),
  );
});

test("disables the enabled toggle when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/extensions", () =>
      HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge",
            tag: "gauge-extension-widget",
            label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [],
            events: [],
            actions: [],
            defaultSize: { w: 2, h: 2 },
            permissions: { collections: "all" },
            enabled: false,
          },
        ],
      }),
    ),
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  const toggle = await screen.findByRole("checkbox", { name: "Actif : Jauge (extension)" });
  expect(toggle).toBeDisabled();
});

test("le volet Catalogue propose un lien vers /admin/roles (RolesAdminPage sinon inatteignable)", async () => {
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  await screen.findByRole("table");
  expect(screen.getByRole("link", { name: "Rôles et privilèges →" })).toHaveAttribute(
    "href",
    "/admin/roles",
  );
});

test("sous viewport étroit, affiche trois onglets Catalogue/Extensions/Détail avec Extensions actif par défaut", async () => {
  stubMatchMedia(true);
  server.use(http.get("https://core.test/extensions", () => HttpResponse.json({ extensions: [] })));
  render(<Harness />);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Extensions", "Détail"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Extensions");
});
