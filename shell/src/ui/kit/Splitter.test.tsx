// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Splitter } from "./Splitter";
import { expectTokenizedClasses } from "./testUtils";

// jsdom n'implémente pas PointerEvent (typeof PointerEvent === "undefined") —
// fireEvent.pointerDown/Move retombent sur un Event générique sans clientX.
// Polyfill local à ce fichier uniquement, jamais setup.ts (piège documenté,
// cf. Task 8/Slider).
class FakePointerEvent extends MouseEvent {
  constructor(type: string, params: PointerEventInit = {}) {
    super(type, params);
  }
}
if (typeof PointerEvent === "undefined") {
  // @ts-expect-error jsdom n'a pas de PointerEvent natif
  global.PointerEvent = FakePointerEvent;
}

test("expose un séparateur avec la largeur courante en aria-valuenow", () => {
  const { container } = render(
    <Splitter first={<div>Gauche</div>} second={<div>Droite</div>} defaultFirstWidth={300} />,
  );
  const handle = screen.getByRole("separator");
  expect(handle).toHaveAttribute("aria-orientation", "vertical");
  expect(handle).toHaveAttribute("aria-valuenow", "300");
  expectTokenizedClasses(container);
});

test("glisser la poignée change la largeur du premier panneau, bornée par min/max", () => {
  render(
    <Splitter
      first={<div>Gauche</div>}
      second={<div>Droite</div>}
      defaultFirstWidth={300}
      min={200}
      max={500}
    />,
  );
  const handle = screen.getByRole("separator");
  fireEvent.pointerDown(handle, { clientX: 300 });
  fireEvent.pointerMove(handle, { clientX: 350 });
  fireEvent.pointerUp(handle);
  expect(handle).toHaveAttribute("aria-valuenow", "350");
});

test("le glissement est borné par max", () => {
  render(
    <Splitter
      first={<div>Gauche</div>}
      second={<div>Droite</div>}
      defaultFirstWidth={300}
      min={200}
      max={400}
    />,
  );
  const handle = screen.getByRole("separator");
  fireEvent.pointerDown(handle, { clientX: 300 });
  fireEvent.pointerMove(handle, { clientX: 1000 });
  fireEvent.pointerUp(handle);
  expect(handle).toHaveAttribute("aria-valuenow", "400");
});
