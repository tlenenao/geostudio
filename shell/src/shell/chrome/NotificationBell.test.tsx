// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { test, expect, beforeEach } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../../test/msw/server";
import { createItemClient } from "../../api/itemClient";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { NotificationBell } from "./NotificationBell";

// Sonde de destination pour vérifier que cliquer une notification avec item
// navigue réellement (pas seulement "n'a pas planté") — même patron que
// src/shell/ImportFileButton.test.tsx::MapProbe.
function PipelineProbe() {
  const { id } = useParams();
  return <div>pipeline-{id}</div>;
}

// NotificationBell interroge toujours la préférence (useNotificationPreference),
// même quand aucun test ci-dessous ne l'exerce — sans ce handler par défaut,
// `onUnhandledRequest: "error"` (src/test/setup.ts) fait échouer la requête ;
// invisible en exécution isolée du fichier (le rejet silencieux n'a pas le
// temps de bloquer un test qui n'attend rien dessus) mais réel sous la suite
// complète (3 des 5 tests ci-dessous, ceux qui cliquent pour ouvrir le
// panneau, timeout à 5000ms) — vérifié par exécution empirique des deux
// (piège n°3/n°10 : un test qui "passe toujours" isolément ne prouve rien).
beforeEach(() => {
  server.use(
    http.get("https://core.test/v1/notifications/preference", () =>
      HttpResponse.json({ value: "all" }),
    ),
  );
});

// Même constat que src/ui/kit/Popover.test.tsx et AccountMenu.test.tsx
// (NotificationBell ouvre ce même Popover) : le repositionnement Popper sous
// jsdom dépasse par intermittence le testTimeout par défaut (5000ms) quand la
// suite complète tourne sous charge CPU, jamais en lançant ce fichier seul —
// vérifié empiriquement (les 3 tests qui cliquent le déclencheur timeout sous
// `npm run test`, jamais isolément). Même valeur (45000) reprise ici plutôt
// que redécouverte.
const OPEN_TIMEOUT = 45000;

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <NotificationBell />
          <Routes>
            <Route path="/pipelines/:id/edit" element={<PipelineProbe />} />
          </Routes>
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("masque le badge quand le compte non-lu est à zéro", async () => {
  server.use(
    http.get("https://core.test/v1/notifications/unread-count", () =>
      HttpResponse.json({ count: 0 }),
    ),
  );
  render(<Harness />);
  await screen.findByRole("button", { name: "Notifications" });
  expect(screen.queryByText("2")).not.toBeInTheDocument();
});

test("affiche le badge avec le compte non-lu", async () => {
  server.use(
    http.get("https://core.test/v1/notifications/unread-count", () =>
      HttpResponse.json({ count: 3 }),
    ),
  );
  render(<Harness />);
  expect(await screen.findByText("3")).toBeInTheDocument();
});

test(
  "ouvre le panneau et affiche les notifications",
  async () => {
    server.use(
      http.get("https://core.test/v1/notifications/unread-count", () =>
        HttpResponse.json({ count: 1 }),
      ),
      http.get("https://core.test/v1/notifications", () =>
        HttpResponse.json({
          notifications: [
            {
              id: "n1",
              kind: "pipeline",
              status: "failure",
              itemId: "item-1",
              itemResourceType: "pipeline",
              itemTitle: "Pipeline nocturne",
              errorMessage: "timeout",
              createdAt: "2026-09-04T10:00:00Z",
              readAt: null,
            },
          ],
          total: 1,
        }),
      ),
    );
    render(<Harness />);
    await userEvent.click(await screen.findByRole("button", { name: "Notifications" }));
    expect(await screen.findByText("Pipeline nocturne")).toBeInTheDocument();
    expect(screen.getByText("timeout")).toBeInTheDocument();
  },
  OPEN_TIMEOUT,
);

test(
  "une notification sans item n'est pas cliquable, une notification avec item ouvre son écran et la marque lue",
  async () => {
    let markReadCalledWith: string | null = null;
    server.use(
      http.get("https://core.test/v1/notifications/unread-count", () =>
        HttpResponse.json({ count: 2 }),
      ),
      http.get("https://core.test/v1/notifications", () =>
        HttpResponse.json({
          notifications: [
            {
              id: "n2",
              kind: "ingestion",
              status: "failure",
              itemId: null,
              itemResourceType: null,
              itemTitle: "Import cassé",
              errorMessage: "fichier invalide",
              createdAt: "2026-09-04T10:00:00Z",
              readAt: null,
            },
            {
              id: "n3",
              kind: "pipeline",
              status: "success",
              itemId: "pl-1",
              itemResourceType: "pipeline",
              itemTitle: "Pipeline ok",
              errorMessage: null,
              createdAt: "2026-09-04T09:00:00Z",
              readAt: null,
            },
          ],
          total: 2,
        }),
      ),
      http.post("https://core.test/v1/notifications/:id/read", ({ params }) => {
        markReadCalledWith = params.id as string;
        return HttpResponse.json({
          id: params.id,
          kind: "pipeline",
          status: "success",
          itemId: "pl-1",
          itemResourceType: "pipeline",
          itemTitle: "Pipeline ok",
          errorMessage: null,
          createdAt: "2026-09-04T09:00:00Z",
          readAt: "2026-09-04T10:05:00Z",
        });
      }),
    );
    render(<Harness />);
    await userEvent.click(await screen.findByRole("button", { name: "Notifications" }));

    // Moitié 1 : sans item, jamais cliquable.
    await screen.findByText("Import cassé");
    expect(screen.queryByRole("button", { name: /Import cassé/ })).not.toBeInTheDocument();

    // Moitié 2 : avec item, cliquer ouvre son écran (navigation réelle, pas
    // seulement "n'a pas planté") ET marque la notification lue.
    const title = await screen.findByText("Pipeline ok");
    const clickable = title.closest("button");
    expect(clickable).not.toBeNull();
    await userEvent.click(clickable as HTMLButtonElement);

    await screen.findByText("pipeline-pl-1"); // rendu par PipelineProbe -> navigation confirmée
    await waitFor(() => expect(markReadCalledWith).toBe("n3"));
  },
  OPEN_TIMEOUT,
);

test(
  "changer la préférence appelle PATCH /notifications/preference avec la valeur choisie",
  async () => {
    let patchedValue: string | null = null;
    server.use(
      http.get("https://core.test/v1/notifications/unread-count", () =>
        HttpResponse.json({ count: 0 }),
      ),
      http.get("https://core.test/v1/notifications", () =>
        HttpResponse.json({ notifications: [], total: 0 }),
      ),
      http.patch("https://core.test/v1/notifications/preference", async ({ request }) => {
        const body = (await request.json()) as { value: string };
        patchedValue = body.value;
        return HttpResponse.json({ value: body.value });
      }),
    );
    render(<Harness />);
    await userEvent.click(await screen.findByRole("button", { name: "Notifications" }));
    const select = await screen.findByRole("combobox");
    await userEvent.selectOptions(select, "Échecs seulement");
    await waitFor(() => expect(patchedValue).toBe("failures_only"));
  },
  OPEN_TIMEOUT,
);

test(
  "affiche un état d'erreur visible quand le chargement des notifications échoue (pas 'Aucune notification.')",
  async () => {
    server.use(
      http.get("https://core.test/v1/notifications/unread-count", () =>
        HttpResponse.json({ count: 0 }),
      ),
      http.get("https://core.test/v1/notifications", () => new HttpResponse(null, { status: 500 })),
    );
    render(<Harness />);
    await userEvent.click(await screen.findByRole("button", { name: "Notifications" }));
    await screen.findByRole("alert");
    expect(screen.queryByText("Aucune notification.")).not.toBeInTheDocument();
  },
  OPEN_TIMEOUT,
);

test(
  "un échec de « Tout marquer comme lu » reste visible, pas silencieux",
  async () => {
    server.use(
      http.get("https://core.test/v1/notifications/unread-count", () =>
        HttpResponse.json({ count: 1 }),
      ),
      http.get("https://core.test/v1/notifications", () =>
        HttpResponse.json({ notifications: [], total: 0 }),
      ),
      http.post(
        "https://core.test/v1/notifications/read-all",
        () => new HttpResponse(null, { status: 500 }),
      ),
    );
    render(<Harness />);
    await userEvent.click(await screen.findByRole("button", { name: "Notifications" }));
    await userEvent.click(await screen.findByRole("button", { name: "Tout marquer comme lu" }));
    await screen.findByRole("alert");
  },
  OPEN_TIMEOUT,
);

test(
  "« Tout marquer comme lu » appelle POST /notifications/read-all",
  async () => {
    let called = false;
    server.use(
      http.get("https://core.test/v1/notifications/unread-count", () =>
        HttpResponse.json({ count: 1 }),
      ),
      http.get("https://core.test/v1/notifications", () =>
        HttpResponse.json({ notifications: [], total: 0 }),
      ),
      http.post("https://core.test/v1/notifications/read-all", () => {
        called = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    render(<Harness />);
    await userEvent.click(await screen.findByRole("button", { name: "Notifications" }));
    await userEvent.click(await screen.findByRole("button", { name: "Tout marquer comme lu" }));
    await waitFor(() => expect(called).toBe(true));
  },
  OPEN_TIMEOUT,
);
