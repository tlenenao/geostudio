// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { enableMockAuth } from "../../auth/useAuth";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { ItemClient } from "../../api/types";
import { SqlLabCopilotPanel } from "./SqlLabCopilotPanel";

enableMockAuth();

const COLLECTIONS = [{ id: "incidents", title: "Incidents voirie" }];

describe("SqlLabCopilotPanel", () => {
  it("inserts a generated SQL draft into the editor without executing it", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({
      reply: "Voici un brouillon.",
      clientOps: [{ op: "applySqlDraft", args: { sql: "SELECT titre FROM incidents" } }],
    });
    const setSql = vi.fn();
    render(
      <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
        <SqlLabCopilotPanel sql="" setSql={setSql} collections={COLLECTIONS} />
      </ItemClientProvider>,
    );

    await userEvent.type(screen.getByLabelText("Message au copilote"), "les titres");
    await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));

    await waitFor(() => expect(setSql).toHaveBeenCalledWith("SELECT titre FROM incidents"));
    const [itemId, payload] = copilotTurn.mock.calls[0];
    expect(itemId).toBeUndefined();
    expect(payload.surface).toBe("sql_lab");
    // I1 : la liste des collections visibles accompagne le SQL en cours —
    // c'est le seul moyen pour le modèle de nommer un `collectionId` réel.
    expect(payload.currentConfig).toEqual({ sql: "", collections: COLLECTIONS });
  });
});
