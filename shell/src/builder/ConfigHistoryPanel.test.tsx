// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { ConfigHistoryPanel } from "./ConfigHistoryPanel";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { ItemClient } from "../api/types";

// Le panneau invalide le cache react-query de sa config après restauration :
// il lui faut donc un QueryClientProvider, comme à ses cinq points de montage
// réels (les cinq éditeurs sont tous sous celui d'App.tsx).
function renderPanel(
  client: Partial<ItemClient>,
  onRestored = vi.fn(),
  queryClient = new QueryClient(),
) {
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client as ItemClient}>
        <ConfigHistoryPanel pk="app-1" currentVersion={2} onRestored={onRestored} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return onRestored;
}

beforeEach(() => {
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

test("liste les versions, la plus récente en tête, et marque la courante", async () => {
  renderPanel({
    listConfigRevisions: vi.fn().mockResolvedValue([
      { version: 1, createdAt: "2026-08-01T10:00:00" },
      { version: 2, createdAt: "2026-08-02T11:00:00" },
    ]),
  });

  const items = await screen.findAllByRole("listitem");
  expect(items[0]).toHaveTextContent("Version 2");
  expect(items[0]).toHaveTextContent("courante");
  expect(items[1]).toHaveTextContent("Version 1");
  // Pas de bouton Restaurer sur la version courante.
  expect(screen.getAllByRole("button", { name: /restaurer/i })).toHaveLength(1);
});

test("un échec de chargement est visible et distinct d'un historique vide", async () => {
  renderPanel({ listConfigRevisions: vi.fn().mockRejectedValue(new Error("boom")) });

  expect(await screen.findByRole("alert")).toHaveTextContent(/impossible de charger/i);
  expect(screen.queryByText(/aucune version/i)).toBeNull();
});

test("un historique vide le dit explicitement", async () => {
  renderPanel({ listConfigRevisions: vi.fn().mockResolvedValue([]) });

  expect(await screen.findByText(/aucune version/i)).toBeInTheDocument();
});

test("restaurer demande confirmation, appelle le client puis prévient le parent", async () => {
  const rollbackConfig = vi.fn().mockResolvedValue(undefined);
  const listConfigRevisions = vi.fn().mockResolvedValue([
    { version: 1, createdAt: "2026-08-01T10:00:00" },
    { version: 2, createdAt: "2026-08-02T11:00:00" },
  ]);
  const onRestored = renderPanel({ listConfigRevisions, rollbackConfig });

  await userEvent.click(await screen.findByRole("button", { name: /restaurer/i }));

  expect(window.confirm).toHaveBeenCalled();
  expect(rollbackConfig).toHaveBeenCalledWith("app-1", 1);
  await waitFor(() => expect(onRestored).toHaveBeenCalled());
  // La liste est rechargée après restauration.
  await waitFor(() => expect(listConfigRevisions).toHaveBeenCalledTimes(2));
});

test("annuler la confirmation ne restaure rien", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  const rollbackConfig = vi.fn();
  renderPanel({
    listConfigRevisions: vi.fn().mockResolvedValue([
      { version: 1, createdAt: "2026-08-01T10:00:00" },
      { version: 2, createdAt: "2026-08-02T11:00:00" },
    ]),
    rollbackConfig,
  });

  await userEvent.click(await screen.findByRole("button", { name: /restaurer/i }));

  expect(rollbackConfig).not.toHaveBeenCalled();
});

test("un échec de restauration est affiché", async () => {
  renderPanel({
    listConfigRevisions: vi.fn().mockResolvedValue([
      { version: 1, createdAt: "2026-08-01T10:00:00" },
      { version: 2, createdAt: "2026-08-02T11:00:00" },
    ]),
    rollbackConfig: vi.fn().mockRejectedValue(new Error("422")),
  });

  await userEvent.click(await screen.findByRole("button", { name: /restaurer/i }));

  expect(await screen.findByRole("alert")).toHaveTextContent(/impossible de restaurer/i);
});

test("restaurer invalide le cache de la config, quelle que soit la page qui monte le panneau", async () => {
  // Une restauration est une écriture ; toutes les autres écritures du dépôt
  // invalident la clé de leur config (useSaveMap/useSaveDataset/
  // useSavePipeline/useSaveApp). Sans ça, le cache garde le contenu d'avant
  // le rollback et un simple refetch (alt-tab, staleTime: 0) réécrase le
  // brouillon sur les trois pages à seed inconditionnel (revue finale SP-23,
  // I3). Les cinq clés diffèrent : la couverture ne peut pas venir d'une
  // liste tenue à la main dans le panneau.
  const queryClient = new QueryClient();
  const keys = [
    ["app", "app-1", undefined],
    ["map", "app-1"],
    ["dataset", "app-1"],
    ["pipeline", "app-1"],
    ["report-schedule", "app-1"],
  ];
  for (const key of keys) queryClient.setQueryData(key, { stale: true });
  queryClient.setQueryData(["items", { type: "app" }], { unrelated: true });

  renderPanel(
    {
      listConfigRevisions: vi.fn().mockResolvedValue([
        { version: 1, createdAt: "2026-08-01T10:00:00" },
        { version: 2, createdAt: "2026-08-02T11:00:00" },
      ]),
      rollbackConfig: vi.fn().mockResolvedValue(undefined),
    },
    vi.fn(),
    queryClient,
  );

  await userEvent.click(await screen.findByRole("button", { name: /restaurer/i }));

  for (const key of keys) {
    await waitFor(() => expect(queryClient.getQueryState(key)?.isInvalidated).toBe(true));
  }
  expect(queryClient.getQueryState(["items", { type: "app" }])?.isInvalidated).toBe(false);
});
