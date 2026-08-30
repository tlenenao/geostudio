// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Menu } from "./Menu";
import { expectTokenizedClasses } from "./testUtils";

// Le repositionnement Popper (@floating-ui/react-dom) sous jsdom coûte
// réellement un peu de CPU par ouverture même avec avoidCollisions=false
// posé dans Menu.tsx (qui élimine la vraie boucle de reset shift/flip,
// cf. Combobox.tsx/Combobox.test.tsx Task 13, Popover.tsx/Popover.test.tsx
// Task 20) — mesuré ici : isolé, ce fichier passe en ~5s (aucun test proche
// du testTimeout par défaut de 5000ms) ; en suite complète (`npm run test`,
// 200 fichiers), "un item disabled n'appelle pas onSelect" a dépassé ce
// testTimeout par intermittence sous charge CPU. Relevé local à ce fichier,
// pas touché à shell/src/test/setup.ts ni à vitest.config.ts — même
// précédent que Combobox.test.tsx et Popover.test.tsx.
// Porté à 45000 (Task 31, portes de qualité) : sous couverture v8, le même
// dépassement se reproduisait même à parallélisme réduit — 45000 stable sur
// 2 exécutions consécutives avec couverture, parallélisme par défaut.
const OPEN_TIMEOUT = 45000;

test(
  "clic sur le déclencheur ouvre le menu, clic sur un item l'exécute et ferme",
  async () => {
    const onSelect = vi.fn();
    const { container } = render(
      <Menu
        trigger={<button>Actions</button>}
        items={[
          { label: "Modifier", onSelect: () => {} },
          { label: "Supprimer", onSelect, danger: true },
        ]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Actions" }));
    const item = await screen.findByRole("menuitem", { name: "Supprimer" });
    await userEvent.click(item);
    expect(onSelect).toHaveBeenCalledTimes(1);
    expect(screen.queryByRole("menuitem", { name: "Supprimer" })).not.toBeInTheDocument();
    expectTokenizedClasses(container);
  },
  OPEN_TIMEOUT,
);

test(
  "un item disabled n'appelle pas onSelect",
  async () => {
    const onSelect = vi.fn();
    render(
      <Menu
        trigger={<button>Actions</button>}
        items={[{ label: "Publier", onSelect, disabled: true }]}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Actions" }));
    const item = await screen.findByRole("menuitem", { name: "Publier" });
    expect(item).toHaveAttribute("aria-disabled", "true");
    await userEvent.click(item);
    expect(onSelect).not.toHaveBeenCalled();
  },
  OPEN_TIMEOUT,
);
