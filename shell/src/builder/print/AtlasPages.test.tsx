// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { DataSource, ItemClient } from "../../api/types";
import { AtlasPages } from "./AtlasPages";

const src: DataSource = { id: "s", type: "features", service: "x", layer: "l", query: {} };
let lastQuery = vi.fn();
const rows = Array.from({ length: 60 }, (_, i) => ({ id: i, properties: { nom: `C${i}` } }));
function setup(entityId?: string, total: number | null = 60, sortBy?: string) {
  const queryDataSourcePage = vi.fn().mockResolvedValue({ records: rows, total });
  const client = { queryDataSourcePage } as unknown as ItemClient;
  lastQuery = queryDataSourcePage;
  return render(
    <QueryClientProvider client={new QueryClient()}>
      <ItemClientProvider client={client}>
        <AtlasPages
          atlas={{
            dataSourceId: "s",
            titleTemplate: "${record.nom}",
            fields: [{ label: "Nom", template: "${record.nom}" }],
            maxPages: 50,
            ...(sortBy ? { sortBy } : {}),
          }}
          dataSources={[src]}
          {...(entityId ? { entityId } : {})}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("une page par entité, plafonnée à maxPages, puis prêt", async () => {
  const { container } = setup();
  await waitFor(() => expect(container.querySelectorAll("[data-atlas-page]")).toHaveLength(50));
  expect(screen.getByRole("heading", { name: "C0" })).toBeInTheDocument();
  await waitFor(() => expect(document.body.dataset.exportReady).toBe("true"));
});

test("entityId : une seule fiche", async () => {
  const { container } = setup("7");
  await waitFor(() => expect(container.querySelectorAll("[data-atlas-page]")).toHaveLength(1));
});

test("AUD-057 : plafond et tri poussés au cœur, bandeau si l'atlas est tronqué", async () => {
  const { container } = setup(undefined, 60, "-nom");
  await waitFor(() => expect(container.querySelector("[data-atlas-truncated]")).not.toBeNull());
  expect(lastQuery.mock.calls[0]![0].query).toMatchObject({ limit: 50, sortby: "-nom" });
});

test("AUD-057 : pas de bandeau quand tout tient dans le plafond", async () => {
  const { container } = setup(undefined, 50);
  await waitFor(() => expect(container.querySelectorAll("[data-atlas-page]")).toHaveLength(50));
  expect(container.querySelector("[data-atlas-truncated]")).toBeNull();
});
