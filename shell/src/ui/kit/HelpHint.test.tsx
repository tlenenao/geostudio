// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { HelpHint } from "./HelpHint";

test("le déclencheur est nommé et ouvre l'explication", async () => {
  render(<HelpHint label="Aide CEL">Utilisez record.champ</HelpHint>);
  expect(screen.queryByText("Utilisez record.champ")).toBeNull();
  await userEvent.click(screen.getByRole("button", { name: "Aide CEL" }));
  expect(await screen.findByText("Utilisez record.champ")).toBeInTheDocument();
});
