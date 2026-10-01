// SPDX-License-Identifier: Apache-2.0
// P07.04 : le shell respecte les bornes du cœur (core/app/copilot/routes.py).
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { enableMockAuth } from "../../auth/useAuth";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { ItemClient } from "../../api/types";
import { CopilotChat } from "./CopilotChat";

enableMockAuth();

describe("CopilotChat — bornes du cœur", () => {
  it("25 tours : historique envoyé <= 40 messages, saisie bornée à 4000", async () => {
    const copilotTurn = vi.fn().mockResolvedValue({ reply: "ok", clientOps: [] });
    render(
      <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
        <CopilotChat
          surface="sql_lab"
          contextPayload={{}}
          clientTools={[]}
          opLabels={{}}
          onClientOps={vi.fn()}
        />
      </ItemClientProvider>,
    );
    const box = screen.getByLabelText("Message au copilote");
    expect(box).toHaveAttribute("maxlength", "4000");
    for (let i = 0; i < 25; i++) {
      fireEvent.change(box, { target: { value: `m${i}` } });
      const send = screen.getByRole("button", { name: "Envoyer" });
      await waitFor(() => expect(send).toBeEnabled());
      fireEvent.click(send);
      await waitFor(() => expect(copilotTurn).toHaveBeenCalledTimes(i + 1));
      // le tour est fini quand la réponse (2 messages par tour) est affichée
      await waitFor(() => expect(screen.getAllByText("ok")).toHaveLength(i + 1));
    }
    const sent = copilotTurn.mock.calls.map(([, p]) => p.history.length);
    expect(Math.max(...sent)).toBeLessThanOrEqual(40);
    expect(sent[24]).toBe(40);
  });
});
