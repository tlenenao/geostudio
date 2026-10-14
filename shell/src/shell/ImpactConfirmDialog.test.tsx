// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { server } from "../test/msw/server";
import { ImpactConfirmDialog } from "./ImpactConfirmDialog";

function setup() {
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ItemClientProvider client={client}>
        <ImpactConfirmDialog
          target={{ type: "collection", id: "parcelles" }}
          title="Supprimer"
          message="Sûr ?"
          confirmLabel="Supprimer"
          onConfirm={() => {}}
          onCancel={() => {}}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

describe("ImpactConfirmDialog", () => {
  it("liste les dépendants visibles et compte les non visibles", async () => {
    server.use(
      http.get("https://core.test/v1/collections/parcelles/impact", () =>
        HttpResponse.json({
          dependents: [
            {
              type: "item",
              id: "m1",
              title: "Carte 1",
              resourceType: "map",
              direct: true,
              depth: 1,
            },
          ],
          hiddenCount: 2,
        }),
      ),
    );
    setup();
    expect(await screen.findByText(/Carte 1/)).toBeInTheDocument();
    expect(screen.getByText(/2 autres objets que vous n'avez pas le droit/)).toBeInTheDocument();
  });

  it("avertit sans bloquer quand la vue d'impact échoue", async () => {
    server.use(
      http.get("https://core.test/v1/collections/parcelles/impact", () =>
        HttpResponse.json({}, { status: 500 }),
      ),
    );
    setup();
    expect(await screen.findByText(/vue d'impact est indisponible/)).toBeInTheDocument();
  });
});
