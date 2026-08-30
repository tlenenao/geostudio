// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { Combobox } from "./Combobox";
import { expectTokenizedClasses } from "./testUtils";

// Polyfills pour jsdom : Radix Popover (via PopoverPrimitive.Content) requiert
// ces méthodes DOM, absentes de jsdom — voir Select.test.tsx (Task 12) pour
// le même motif. Ne pas ajouter à shell/src/test/setup.ts (piège documenté).
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}

const OPTIONS = [
  { value: "a", label: "Alpha" },
  { value: "b", label: "Beta" },
  { value: "c", label: "Gamma" },
];

// Le repositionnement Popper (@floating-ui/react-dom) sous jsdom coûte
// réellement ~1 à 4s par ouverture/frappe (mesuré) — pas une boucle infinie
// (cf. avoidCollisions=false dans Combobox.tsx qui a déjà éliminé la vraie
// boucle de reset shift/flip, ~13s/test), mais un coût de mesure DOM
// (getComputedStyle/getBoundingClientRect répétés) suffisant pour dépasser
// par intermittence le testTimeout par défaut du dépôt (5000ms, aucune
// surcharge dans vitest.config.ts). Relevé local à ce fichier, pas touché à
// shell/src/test/setup.ts ni à vitest.config.ts.
// Porté à 45000 (Task 31, portes de qualité) : sous `npm run test --
// --coverage` (instrumentation v8), le même test dépassait encore 15000 et
// jusqu'à 30000 par intermittence, y compris en réduisant le parallélisme
// (`--maxWorkers`) — le coût de mesure Popper s'additionne au surcoût de
// l'instrumentation de couverture. 45000 est resté stable sur 2 exécutions
// consécutives de la suite complète avec couverture, parallélisme par défaut.
const OPEN_TIMEOUT = 45000;

test(
  "filtre les options en tapant, affiche uniquement les correspondances",
  async () => {
    const onValueChange = vi.fn();
    const { container } = render(
      <Combobox aria-label="Collection" value="" onValueChange={onValueChange} options={OPTIONS} />,
    );
    const input = screen.getByRole("combobox", { name: "Collection" });
    await userEvent.click(input);
    await userEvent.type(input, "ga");
    expect(screen.getByRole("option", { name: "Gamma" })).toBeInTheDocument();
    expect(screen.queryByRole("option", { name: "Alpha" })).not.toBeInTheDocument();
    expectTokenizedClasses(container);
  },
  OPEN_TIMEOUT,
);

test(
  "flèche bas puis Entrée sélectionne l'option surlignée",
  async () => {
    const onValueChange = vi.fn();
    render(
      <Combobox aria-label="Collection" value="" onValueChange={onValueChange} options={OPTIONS} />,
    );
    const input = screen.getByRole("combobox", { name: "Collection" });
    await userEvent.click(input);
    await userEvent.keyboard("{ArrowDown}{Enter}");
    expect(onValueChange).toHaveBeenCalledWith("a");
  },
  OPEN_TIMEOUT,
);

test(
  "Échap ferme la liste sans sélectionner",
  async () => {
    const onValueChange = vi.fn();
    render(
      <Combobox aria-label="Collection" value="" onValueChange={onValueChange} options={OPTIONS} />,
    );
    const input = screen.getByRole("combobox", { name: "Collection" });
    await userEvent.click(input);
    expect(screen.getByRole("listbox")).toBeInTheDocument();
    await userEvent.keyboard("{Escape}");
    expect(screen.queryByRole("listbox")).not.toBeInTheDocument();
    expect(onValueChange).not.toHaveBeenCalled();
  },
  OPEN_TIMEOUT,
);

test(
  "flèche haut ne descend pas sous le premier élément",
  async () => {
    const onValueChange = vi.fn();
    render(
      <Combobox aria-label="Collection" value="" onValueChange={onValueChange} options={OPTIONS} />,
    );
    const input = screen.getByRole("combobox", { name: "Collection" });
    await userEvent.click(input);
    await userEvent.keyboard("{ArrowUp}{ArrowUp}{Enter}");
    expect(onValueChange).toHaveBeenCalledWith("a");
  },
  OPEN_TIMEOUT,
);

test(
  "affiche 'Aucun résultat' quand le filtre ne correspond à rien",
  async () => {
    const onValueChange = vi.fn();
    render(
      <Combobox aria-label="Collection" value="" onValueChange={onValueChange} options={OPTIONS} />,
    );
    const input = screen.getByRole("combobox", { name: "Collection" });
    await userEvent.click(input);
    await userEvent.type(input, "zzz");
    expect(screen.getByText("Aucun résultat")).toBeInTheDocument();
  },
  OPEN_TIMEOUT,
);

test("préremplit le champ avec le libellé de la valeur courante", () => {
  const onValueChange = vi.fn();
  render(
    <Combobox aria-label="Collection" value="b" onValueChange={onValueChange} options={OPTIONS} />,
  );
  expect(screen.getByRole("combobox", { name: "Collection" })).toHaveValue("Beta");
});

test("resynchronise l'affichage quand value change depuis le parent", () => {
  const onValueChange = vi.fn();
  const { rerender } = render(
    <Combobox aria-label="Collection" value="" onValueChange={onValueChange} options={OPTIONS} />,
  );
  const input = screen.getByRole("combobox", { name: "Collection" });
  expect(input).toHaveValue("");
  rerender(
    <Combobox aria-label="Collection" value="c" onValueChange={onValueChange} options={OPTIONS} />,
  );
  expect(input).toHaveValue("Gamma");
});

test(
  "le clic sur une option la sélectionne",
  async () => {
    const onValueChange = vi.fn();
    render(
      <Combobox aria-label="Collection" value="" onValueChange={onValueChange} options={OPTIONS} />,
    );
    const input = screen.getByRole("combobox", { name: "Collection" });
    await userEvent.click(input);
    await userEvent.click(await screen.findByRole("option", { name: "Beta" }));
    expect(onValueChange).toHaveBeenCalledWith("b");
    expect(input).toHaveValue("Beta");
  },
  OPEN_TIMEOUT,
);
