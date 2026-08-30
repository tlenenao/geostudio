// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { Tooltip } from "./Tooltip";
import { expectTokenizedClasses } from "./testUtils";

// react-use-size (utilisé par TooltipPrimitive.Content/Arrow) appelle
// ResizeObserver sans garde — stub local à ce fichier uniquement, même
// patron que Slider.test.tsx/EChart.test.tsx. jsdom n'a pas ResizeObserver,
// un noop suffit ici.
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function renderWithProvider(ui: React.ReactElement) {
  return render(<TooltipPrimitive.Provider delayDuration={0}>{ui}</TooltipPrimitive.Provider>);
}

// Le repositionnement Popper (@floating-ui/react-dom) sous jsdom coûte
// réellement ~16s ici même avec avoidCollisions=false posé dans
// Tooltip.tsx (qui élimine la vraie boucle de reset shift/flip, cf.
// Combobox.tsx/Combobox.test.tsx Task 13, Popover.tsx/Popover.test.tsx
// Task 20, Menu.tsx/Menu.test.tsx Task 21) — mesuré: dépasse largement le
// testTimeout par défaut du dépôt (5000ms, aucune surcharge dans
// vitest.config.ts), y compris en lançant ce fichier seul. Relevé local à
// ce fichier, pas touché à shell/src/test/setup.ts ni à vitest.config.ts —
// même précédent que Combobox.test.tsx/Popover.test.tsx/Menu.test.tsx.
// Porté à 45000 (Task 31, portes de qualité) : sous couverture v8, le même
// dépassement se reproduisait même à parallélisme réduit — 45000 stable sur
// 2 exécutions consécutives avec couverture, parallélisme par défaut.
const OPEN_TIMEOUT = 45000;

test(
  "le survol du déclencheur affiche le contenu du tooltip",
  async () => {
    const { baseElement } = renderWithProvider(
      <Tooltip content="Verrouillé — modification réservée aux éditeurs">
        <button>×</button>
      </Tooltip>,
    );
    await userEvent.hover(screen.getByRole("button"));
    expect(
      await screen.findByText("Verrouillé — modification réservée aux éditeurs"),
    ).toBeInTheDocument();
    expectTokenizedClasses(baseElement);
  },
  OPEN_TIMEOUT,
);
