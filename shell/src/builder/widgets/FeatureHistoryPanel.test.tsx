// SPDX-License-Identifier: Apache-2.0
import { describe, it, expect, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { FeatureHistoryPanel } from "./FeatureHistoryPanel";
import type { FeatureVersion, ItemClient } from "../../api/types";

const versions: FeatureVersion[] = [
  {
    id: 2,
    fid: "1",
    op: "update",
    at: "2026-10-12T10:00:00Z",
    actor: { id: "u1", username: "alice" },
    before: { properties: { nom: "A" }, geometry: null },
    after: { properties: { nom: "B" }, geometry: null },
  },
  {
    id: 1,
    fid: "1",
    op: "create",
    at: "2026-10-12T09:00:00Z",
    actor: null,
    before: null,
    after: { properties: { nom: "A" }, geometry: null },
  },
];

function setup(canWrite: boolean) {
  const restoreFeatureVersion = vi.fn().mockResolvedValue(undefined);
  const client = {
    listFeatureHistory: vi.fn().mockResolvedValue(versions),
    restoreFeatureVersion,
  } as unknown as ItemClient;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <FeatureHistoryPanel client={client} collectionId="c" fid="1" canWrite={canWrite} />
    </QueryClientProvider>,
  );
  return restoreFeatureVersion;
}

describe("FeatureHistoryPanel", () => {
  it("liste les versions, l'auteur et les champs modifiés, et restaure", async () => {
    const restore = setup(true);
    const toggle = screen.getByRole("button", { name: "Historique" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(toggle);
    expect(await screen.findByText(/Modification .* alice/)).toBeInTheDocument();
    expect(screen.getByText(/auteur effacé/)).toBeInTheDocument();
    expect(screen.getAllByText("Champs modifiés : nom")).toHaveLength(2);
    await userEvent.click(screen.getAllByRole("button", { name: "Restaurer cette version" })[0]!);
    expect(restore).toHaveBeenCalledWith("c", "1", 2);
  });

  it("masque la restauration sans droit d'écriture", async () => {
    setup(false);
    await userEvent.click(screen.getByRole("button", { name: "Historique" }));
    await screen.findByText(/Modification/);
    expect(screen.queryByRole("button", { name: "Restaurer cette version" })).toBeNull();
  });
});
