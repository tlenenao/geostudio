// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { enableMockAuth } from "../auth/useAuth";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { ItemClient } from "../api/types";
import { BindingEditor } from "./BindingEditor";

enableMockAuth();

test("NL draft fills the field; the binding is written only on 'Lier'", async () => {
  const copilotTurn = vi.fn().mockResolvedValue({
    reply: "",
    clientOps: [{ op: "applyCelDraft", args: { expression: "vars.n + 1" } }],
  });
  const onChange = vi.fn();
  render(
    <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
      <BindingEditor props={{ label: "x" }} variables={[]} generateItemId="9" onChange={onChange} />
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByText("Liaisons dynamiques"));
  await userEvent.click(await screen.findByText("Générer"));
  await userEvent.type(screen.getByLabelText("Décrire l'expression"), "n plus un");
  await userEvent.click(screen.getByRole("button", { name: "Proposer" }));
  await userEvent.click(await screen.findByRole("button", { name: "Appliquer" }));

  expect(copilotTurn.mock.calls[0][1].surface).toBe("binding");
  expect(onChange).not.toHaveBeenCalled();
  expect(screen.getByLabelText("Expression de la liaison (CEL)")).toHaveValue("vars.n + 1");
  await userEvent.click(screen.getByRole("button", { name: "Lier la propriété" }));
  expect(onChange).toHaveBeenCalledWith({ label: { $expr: "vars.n + 1" } });
});
