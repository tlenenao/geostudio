// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { CollectionProfile, ItemClient } from "../api/types";
import { expectTokenizedClasses } from "../ui/kit/testUtils";
import { CollectionProfilePanel } from "./CollectionProfilePanel";

function renderPanel(getCollectionProfile: ItemClient["getCollectionProfile"]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={{ getCollectionProfile } as ItemClient}>
        <CollectionProfilePanel collectionId="parcs" id="p" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

const profile: CollectionProfile = {
  rowCount: 1200,
  sampled: true,
  truncatedColumns: false,
  pending: false,
  asOf: "2026-10-10T10:00:00+00:00",
  columns: [
    {
      name: "surface",
      type: "number",
      nonNull: 900,
      nulls: 300,
      distinct: 400,
      min: 1,
      max: 50,
      median: 12,
      histogram: [
        { bucketIndex: 0, bucketStart: 1, bucketEnd: 25, count: 800 },
        { bucketIndex: 1, bucketStart: 25, bucketEnd: 50, count: 100 },
      ],
    },
    {
      name: "commune",
      type: "string",
      nonNull: 1200,
      nulls: 0,
      distinct: 3,
      topValues: [{ value: "Tulle", count: 700 }],
    },
  ],
  geometry: {
    column: "geom",
    bbox: [1.5, 45.1, 2.5, 45.9],
    types: [{ type: "POINT", count: 1200 }],
  },
};

test("affiche lignes, échantillon, colonnes, histogramme et emprise", async () => {
  const { container } = renderPanel(vi.fn().mockResolvedValue(profile));
  expect(await screen.findByText(/1\s200 lignes/)).toBeInTheDocument();
  expect(screen.getByText(/échantillon/)).toBeInTheDocument();
  expect(screen.getByRole("rowheader", { name: "surface" })).toBeInTheDocument();
  expect(screen.getByText(/Tulle \(700\)/)).toBeInTheDocument();
  expect(screen.getByText(/médiane 12/)).toBeInTheDocument();
  expect(screen.getByRole("img", { name: "Répartition de surface" })).toBeInTheDocument();
  expect(screen.getByText(/POINT \(1\s200\)/)).toBeInTheDocument();
  expect(screen.getByText(/Emprise/)).toBeInTheDocument();
  expect(screen.getByText("75 %")).toBeInTheDocument();
  expectTokenizedClasses(container);
});

test("lac pas encore alimenté : message dédié", async () => {
  renderPanel(vi.fn().mockResolvedValue({ ...profile, pending: true, rowCount: 0, columns: [] }));
  expect(await screen.findByText(/pas encore disponibles/)).toBeInTheDocument();
});

test("erreur de chargement : bannière avec nouvelle tentative", async () => {
  renderPanel(vi.fn().mockRejectedValue(new Error("boom")));
  expect(await screen.findByRole("button", { name: "Réessayer" })).toBeInTheDocument();
});
