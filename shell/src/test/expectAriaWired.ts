// SPDX-License-Identifier: Apache-2.0
import { expect } from "vitest";

/**
 * Vérifie qu'un déclencheur est correctement câblé à son panneau
 * (aria-controls pointant sur panelId, aria-expanded reflétant
 * expectedExpanded — passé explicitement par l'appelant, jamais déduit de
 * l'état observé) et que le panneau existe dans le DOM quand il est ouvert.
 *
 * Note SP-43 Tâche 7 : un premier brouillon comparait
 * trigger.getAttribute("aria-expanded") à lui-même (assertion
 * auto-référentielle, ne prouve rien) — remplacé par cette forme stricte à
 * 3 paramètres qui compare à la valeur explicitement attendue.
 */
export function expectAriaWired(trigger: HTMLElement, panelId: string, expectedExpanded: boolean) {
  expect(trigger).toHaveAttribute("aria-controls", panelId);
  expect(trigger).toHaveAttribute("aria-expanded", String(expectedExpanded));
  if (expectedExpanded) {
    expect(document.getElementById(panelId)).not.toBeNull();
  }
}
