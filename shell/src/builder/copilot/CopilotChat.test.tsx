// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { enableMockAuth } from "../../auth/useAuth";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { ItemClient } from "../../api/types";
import { CopilotChat } from "./CopilotChat";

enableMockAuth();

describe("CopilotChat", () => {
  it("calls copilotTurn with the given surface and context payload, no itemId", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({ reply: "ok", clientOps: [] });
    const onClientOps = vi.fn();
    render(
      <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
        <CopilotChat
          surface="sql_lab"
          contextPayload={{ sql: "SELECT 1" }}
          clientTools={[]}
          opLabels={{}}
          onClientOps={onClientOps}
        />
      </ItemClientProvider>,
    );

    await userEvent.type(screen.getByLabelText("Message au copilote"), "écris une requête");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() => expect(copilotTurn).toHaveBeenCalled());
    const [itemId, payload] = copilotTurn.mock.calls[0];
    expect(itemId).toBeUndefined();
    expect(payload.surface).toBe("sql_lab");
    expect(payload.currentConfig).toEqual({ sql: "SELECT 1" });
    expect(onClientOps).not.toHaveBeenCalled();
  });

  it("forwards clientOps to onClientOps without applying them itself", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "voici",
      clientOps: [{ op: "applySqlDraft", args: { sql: "SELECT 1" } }],
    });
    const onClientOps = vi.fn();
    render(
      <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
        <CopilotChat
          surface="sql_lab"
          contextPayload={{ sql: "" }}
          clientTools={[]}
          opLabels={{ applySqlDraft: "Brouillon SQL inséré" }}
          onClientOps={onClientOps}
        />
      </ItemClientProvider>,
    );

    await userEvent.type(screen.getByLabelText("Message au copilote"), "écris une requête");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() =>
      expect(onClientOps).toHaveBeenCalledWith([
        { op: "applySqlDraft", args: { sql: "SELECT 1" } },
      ]),
    );
    expect(screen.getByText("Brouillon SQL inséré")).toBeVisible();
  });

  // M1 (revue finale de branche GAP-17) : le libellé de succès était calculé
  // AVANT d'appeler onClientOps — l'UI annonçait « Brouillon SQL inséré. »
  // même quand l'applier abandonnait silencieusement l'op (SQL vide,
  // filtres tous invalides, métrique non conforme).
  it("does not claim success when the applier reports the op was dropped", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "voici",
      clientOps: [{ op: "applySqlDraft", args: { sql: "   " } }],
    });
    render(
      <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
        <CopilotChat
          surface="sql_lab"
          contextPayload={{ sql: "" }}
          clientTools={[]}
          opLabels={{ applySqlDraft: "Brouillon SQL inséré" }}
          onClientOps={() => [false]}
        />
      </ItemClientProvider>,
    );

    await userEvent.type(screen.getByLabelText("Message au copilote"), "écris une requête");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    expect(await screen.findByText("Proposition ignorée (invalide) : applySqlDraft")).toBeVisible();
    expect(screen.queryByText("Brouillon SQL inséré")).not.toBeInTheDocument();
  });

  // Un appelant qui ne renvoie rien (CopilotPanel/builder d'App, qui édite
  // via setDraft) garde exactement son comportement : tout est annoncé
  // comme appliqué.
  it("keeps labelling every op when the applier returns nothing", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "voici",
      clientOps: [{ op: "applySqlDraft", args: { sql: "SELECT 1" } }],
    });
    render(
      <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
        <CopilotChat
          surface="sql_lab"
          contextPayload={{ sql: "" }}
          clientTools={[]}
          opLabels={{ applySqlDraft: "Brouillon SQL inséré" }}
          onClientOps={() => {}}
        />
      </ItemClientProvider>,
    );

    await userEvent.type(screen.getByLabelText("Message au copilote"), "écris une requête");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    expect(await screen.findByText("Brouillon SQL inséré")).toBeVisible();
  });
});
