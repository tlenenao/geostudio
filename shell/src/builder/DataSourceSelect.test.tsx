// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { expect, test, vi } from "vitest";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { DataSource } from "../api/types";
import { server } from "../test/msw/server";
import { DataSourceSelect } from "./DataSourceSelect";
import { DataSourcesEditProvider } from "./DataSourcesEditContext";

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    coreUrl: "https://core.test",
    getToken: () => "test-token",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

const sources: DataSource[] = [
  { id: "ds1", type: "features", service: "fs", layer: "parcs", query: {} },
  { id: "ds2", type: "static", service: "", layer: "", query: {} },
];

test("selects a data source and emits its id", async () => {
  const onChange = vi.fn();
  render(<DataSourceSelect value="" dataSources={sources} onChange={onChange} />, { wrapper });
  await userEvent.selectOptions(screen.getByLabelText("Source de données"), "ds2");
  expect(onChange).toHaveBeenCalledWith("ds2");
});

test("picking a shared dataset not yet inline calls onAdd then onChange with the new source id", async () => {
  server.use(
    http.get("https://core.test/items*", ({ request }) => {
      const url = new URL(request.url);
      if (url.searchParams.get("type") !== "dataset")
        return HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 });
      return HttpResponse.json({
        items: [
          {
            pk: "ds-1",
            resourceType: "dataset",
            title: "Parcs partagés",
            abstract: "",
            owner: "alice",
            thumbnailUrl: null,
            date: "2026-01-01",
            configId: "cfg-ds1",
            isPublished: true,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      });
    }),
  );
  const onChange = vi.fn();
  let added: DataSource | undefined;
  render(
    <DataSourcesEditProvider
      onAdd={(s) => {
        added = s;
      }}
    >
      <DataSourceSelect value="" dataSources={[]} onChange={onChange} />
    </DataSourcesEditProvider>,
    { wrapper },
  );

  const select = await screen.findByLabelText("Source de données");
  await screen.findByRole("option", { name: "Parcs partagés" });
  await userEvent.selectOptions(select, "Parcs partagés");

  expect(added).toMatchObject({ type: "features", service: "core", layer: "", datasetId: "ds-1" });
  expect(onChange).toHaveBeenCalledWith(added!.id);
});

test("a shared dataset already referenced inline is not listed twice", async () => {
  server.use(
    http.get("https://core.test/items*", () =>
      HttpResponse.json({
        items: [
          {
            pk: "ds-1",
            resourceType: "dataset",
            title: "Parcs partagés",
            abstract: "",
            owner: "alice",
            thumbnailUrl: null,
            date: "2026-01-01",
            configId: "cfg-ds1",
            isPublished: true,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      }),
    ),
  );
  render(
    <DataSourcesEditProvider onAdd={() => {}}>
      <DataSourceSelect
        value="s1"
        dataSources={[
          { id: "s1", type: "features", service: "core", layer: "", datasetId: "ds-1", query: {} },
        ]}
        onChange={() => {}}
      />
    </DataSourcesEditProvider>,
    { wrapper },
  );
  expect(screen.queryByRole("option", { name: "Parcs partagés" })).not.toBeInTheDocument();
});
