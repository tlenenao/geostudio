// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { LineagePanel } from "./LineagePanel";

describe("LineagePanel (AUD-086)", () => {
  it("lists upstream and downstream nodes, items as links", async () => {
    const client = {
      getLineage: vi.fn().mockResolvedValue({
        target: { type: "item", id: "p1", title: "Pipe", resourceType: "pipeline" },
        nodes: [
          {
            type: "collection",
            id: "c1",
            title: "Communes",
            resourceType: "collection",
            direction: "upstream",
          },
          { type: "item", id: "m1", title: "Carte", resourceType: "map", direction: "downstream" },
        ],
        edges: [],
        hiddenCount: 1,
      }),
    };
    render(
      <MemoryRouter>
        <QueryClientProvider client={new QueryClient()}>
          <ItemClientProvider client={client as never}>
            <LineagePanel itemId="p1" />
          </ItemClientProvider>
        </QueryClientProvider>
      </MemoryRouter>,
    );
    expect(await screen.findByText("Communes")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Carte" })).toHaveAttribute("href", "/items/m1");
    expect(screen.getByText(/1 élément masqué/)).toBeInTheDocument();
    expect(client.getLineage).toHaveBeenCalledWith("p1");
  });
});
