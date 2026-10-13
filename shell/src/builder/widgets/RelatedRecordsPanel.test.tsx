// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RelatedRecordsPanel } from "./RelatedRecordsPanel";
import type { CollectionRelation, ItemClient } from "../../api/types";

const relation: CollectionRelation = {
  id: "r1",
  name: "proprietaires",
  cardinality: "one_to_many",
  parentCollectionId: "p",
  childCollectionId: "o",
  onDelete: "restrict",
};

function setup(client: Partial<ItemClient>) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <RelatedRecordsPanel client={client as ItemClient} collectionId="p" fid="1" />
    </QueryClientProvider>,
  );
}

describe("RelatedRecordsPanel", () => {
  it("liste les enregistrements liés au dépliage", async () => {
    const listRelatedRecords = vi.fn().mockResolvedValue({
      relation,
      direction: "children",
      collectionId: "o",
      features: [{ id: 7, properties: { nom: "Mme Durand" } }],
      numberReturned: 1,
      numberMatched: 1,
    });
    setup({ listCollectionRelations: vi.fn().mockResolvedValue([relation]), listRelatedRecords });
    const toggle = await screen.findByRole("button", { name: "Enregistrements liés" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(await screen.findByText("Mme Durand")).toBeInTheDocument();
    expect(screen.getByText("proprietaires (1)")).toBeInTheDocument();
    expect(listRelatedRecords).toHaveBeenCalledWith("p", "1", "r1");
  });

  it("ne rend rien sans relation", () => {
    setup({ listCollectionRelations: vi.fn().mockResolvedValue([]), listRelatedRecords: vi.fn() });
    expect(screen.queryByRole("button")).toBeNull();
  });
});
