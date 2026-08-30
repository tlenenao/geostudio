// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import { Popover } from "./Popover";
import { expectTokenizedClasses } from "./testUtils";

// Le repositionnement Popper (@floating-ui/react-dom) sous jsdom coûte
// réellement ~2 à 3s par ouverture (mesuré) même avec avoidCollisions=false
// posé dans Popover.tsx (qui élimine la vraie boucle de reset shift/flip,
// cf. Combobox.tsx/Combobox.test.tsx, Task 13) — un coût de mesure DOM
// (getComputedStyle/getBoundingClientRect répétés) suffisant pour dépasser
// par intermittence le testTimeout par défaut du dépôt (5000ms, aucune
// surcharge dans vitest.config.ts) quand la suite complète tourne sous
// charge CPU. Reproduit 3 fois de suite sur "Échap ferme le popover ouvert"
// en lançant `npm run test` complet (198 autres fichiers), jamais en lançant
// ce fichier seul ou seulement src/ui/kit/. Relevé local à ce fichier, pas
// touché à shell/src/test/setup.ts ni à vitest.config.ts — même précédent
// que Combobox.test.tsx.
// Porté à 45000 (Task 31, portes de qualité) : sous couverture v8, le même
// dépassement se reproduisait même à parallélisme réduit — 45000 stable sur
// 2 exécutions consécutives avec couverture, parallélisme par défaut.
const OPEN_TIMEOUT = 45000;

test(
  "un clic réel sur le déclencheur ouvre le contenu, porté hors de #root",
  async () => {
    const root = document.createElement("div");
    root.id = "root";
    document.body.appendChild(root);
    const { container } = render(
      <Popover trigger={<button>Ouvrir</button>}>Contenu du popover</Popover>,
      {
        container: root,
      },
    );
    expect(screen.queryByText("Contenu du popover")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Ouvrir" }));
    const content = await screen.findByText("Contenu du popover");
    expect(content).toBeInTheDocument();
    expect(root.contains(content)).toBe(false);
    expectTokenizedClasses(container);
    document.body.removeChild(root);
  },
  OPEN_TIMEOUT,
);

test(
  "Échap ferme le popover ouvert",
  async () => {
    render(<Popover trigger={<button>Ouvrir</button>}>Contenu</Popover>);
    await userEvent.click(screen.getByRole("button", { name: "Ouvrir" }));
    expect(await screen.findByText("Contenu")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByText("Contenu")).not.toBeInTheDocument();
  },
  OPEN_TIMEOUT,
);
