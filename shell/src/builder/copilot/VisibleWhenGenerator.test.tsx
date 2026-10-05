// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { enableMockAuth } from "../../auth/useAuth";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { ItemClient } from "../../api/types";
import { VisibleWhenGenerator } from "./VisibleWhenGenerator";

enableMockAuth();

function renderWith(copilotTurn: ReturnType<typeof vi.fn>, onApply = vi.fn()) {
  render(
    <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
      <VisibleWhenGenerator
        itemId="9"
        availableFields={["vars.statut", "user.name"]}
        current=""
        onApply={onApply}
      />
    </ItemClientProvider>,
  );
  return onApply;
}

async function ask() {
  await userEvent.click(screen.getByText("Générer"));
  await userEvent.type(screen.getByLabelText("Décrire la condition"), "statut ouvert");
  await userEvent.click(screen.getByRole("button", { name: "Proposer" }));
}

describe("VisibleWhenGenerator", () => {
  it("labels the textarea per context", async () => {
    render(
      <ItemClientProvider client={{ copilotTurn: vi.fn() } as never}>
        <VisibleWhenGenerator
          itemId="9"
          context="computedColumn"
          availableFields={[]}
          current=""
          onApply={vi.fn()}
        />
      </ItemClientProvider>,
    );
    await userEvent.click(screen.getByText("Générer"));
    expect(screen.getByLabelText("Décrire l'expression")).toBeInTheDocument();
  });

  it("shows the draft and applies it only on click", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "Voici une condition.",
      clientOps: [{ op: "applyCelDraft", args: { expression: 'vars.statut == "ouvert"' } }],
    });
    const onApply = renderWith(copilotTurn);
    await ask();

    expect(await screen.findByText('vars.statut == "ouvert"')).toBeInTheDocument();
    expect(onApply).not.toHaveBeenCalled();
    await userEvent.click(screen.getByRole("button", { name: "Appliquer" }));
    expect(onApply).toHaveBeenCalledWith('vars.statut == "ouvert"');

    const [itemId, payload] = copilotTurn.mock.calls[0];
    expect(itemId).toBe("9");
    expect(payload.surface).toBe("visible_when");
    expect(payload.mcpToken).toBe("mock-mcp-token");
    expect(payload.clientTools.map((tool: { name: string }) => tool.name)).toEqual([
      "applyCelDraft",
    ]);
    expect(payload.currentConfig).toEqual({
      availableFields: ["vars.statut", "user.name"],
      visibleWhen: "",
    });
  });

  it("blocks an invalid draft and explains why", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "",
      clientOps: [{ op: "applyCelDraft", args: { expression: "vars.statut ==" } }],
    });
    renderWith(copilotTurn);
    await ask();
    await screen.findByText("vars.statut ==");
    expect(screen.getByRole("button", { name: "Appliquer" })).toBeDisabled();
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("says when the copilot proposed nothing, and when the call failed", async () => {
    const copilotTurn = vi
      .fn()
      .mockResolvedValueOnce({ reply: "Je ne sais pas.", clientOps: [] })
      .mockRejectedValueOnce(new Error("502"));
    renderWith(copilotTurn);
    await ask();
    expect(await screen.findByText("Aucune condition proposée.")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Proposer" }));
    await waitFor(() =>
      expect(screen.getByText("Échec de la requête au copilote.")).toBeInTheDocument(),
    );
  });
});
