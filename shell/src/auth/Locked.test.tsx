// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Locked } from "./Locked";

describe("Locked", () => {
  it("affiche la raison et rend le contenu inopérant", () => {
    render(
      <Locked reason="Écriture réservée aux éditeurs de cet élément.">
        <button>Modifier</button>
      </Locked>,
    );
    const button = screen.getByRole("button", { name: "Modifier" });
    expect(button).toBeDisabled();
    expect(screen.getByText("Écriture réservée aux éditeurs de cet élément.")).toBeVisible();
  });

  it("relie la raison au contenu pour les lecteurs d'écran", () => {
    render(
      <Locked reason="Le partage est réservé au propriétaire.">
        <button>Partager</button>
      </Locked>,
    );
    const group = screen.getByRole("group");
    expect(group).toHaveAccessibleDescription("Le partage est réservé au propriétaire.");
  });
});
