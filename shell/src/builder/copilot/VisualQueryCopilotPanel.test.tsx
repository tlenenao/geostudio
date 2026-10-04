// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { enableMockAuth } from "../../auth/useAuth";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { CollectionSchema, ItemClient } from "../../api/types";
import { VisualQueryCopilotPanel } from "./VisualQueryCopilotPanel";

enableMockAuth();

const BASE_SCHEMA: CollectionSchema = {
  collection: "incidents",
  pk: "id",
  geometry: null,
  fields: [{ name: "titre", type: "string", required: false }],
};

describe("VisualQueryCopilotPanel", () => {
  it("applies generated filters without creating or running anything", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "Voici un filtre.",
      clientOps: [
        {
          op: "applyVisualQueryDraft",
          args: { filters: [{ column: "titre", operator: "eq", value: "Nid de poule" }] },
        },
      ],
    });
    const setFilters = vi.fn();
    const setJoin = vi.fn();
    const setSummary = vi.fn();
    render(
      <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
        <VisualQueryCopilotPanel
          baseCollectionId="incidents"
          baseSchema={BASE_SCHEMA}
          joinedSchema={null}
          collectionIds={["incidents"]}
          filters={[]}
          join={null}
          summary={null}
          setFilters={setFilters}
          setJoin={setJoin}
          setSummary={setSummary}
        />
      </ItemClientProvider>,
    );

    await userEvent.type(screen.getByLabelText("Message au copilote"), "les nids de poule");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() =>
      expect(setFilters).toHaveBeenCalledWith([
        { column: "titre", operator: "eq", value: "Nid de poule" },
      ]),
    );
    const [itemId, payload] = copilotTurn.mock.calls[0];
    expect(itemId).toBeUndefined();
    expect(payload.surface).toBe("visual_query");
    expect(payload.currentConfig).toEqual({
      baseCollectionId: "incidents",
      filters: [],
      join: null,
      summary: null,
    });
  });

  it("REV-184 : annonce les jambes ignorées quand le brouillon n'est appliqué qu'en partie", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "Voici.",
      clientOps: [
        {
          op: "applyVisualQueryDraft",
          args: {
            filters: [{ column: "titre", operator: "eq", value: "Nid de poule" }],
            join: { collectionId: "collection_inventee", on: "titre", how: "inner" },
          },
        },
      ],
    });
    render(
      <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
        <VisualQueryCopilotPanel
          baseCollectionId="incidents"
          baseSchema={BASE_SCHEMA}
          joinedSchema={null}
          collectionIds={["incidents"]}
          filters={[]}
          join={null}
          summary={null}
          setFilters={vi.fn()}
          setJoin={vi.fn()}
          setSummary={vi.fn()}
        />
      </ItemClientProvider>,
    );
    await userEvent.type(screen.getByLabelText("Message au copilote"), "les nids de poule");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
    expect(
      await screen.findByText("Requête visuelle mise à jour ; ignoré (invalide) : jointure."),
    ).toBeVisible();
  });
});
