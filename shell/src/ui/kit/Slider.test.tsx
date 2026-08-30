// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { Slider } from "./Slider";
import { expectTokenizedClasses } from "./testUtils";

// Radix Slider appelle ResizeObserver sans garde — stub local à ce fichier
// uniquement, même patron que EChart.test.tsx. jsdom n'a pas ResizeObserver,
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

test("flèche droite augmente la valeur d'un pas", async () => {
  const onValueChange = vi.fn();
  const { container } = render(
    <Slider
      aria-label="Opacité"
      value={[50]}
      min={0}
      max={100}
      step={10}
      onValueChange={onValueChange}
    />,
  );
  const thumb = screen.getByRole("slider", { name: "Opacité" });
  expect(thumb).toHaveAttribute("aria-valuenow", "50");
  thumb.focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(onValueChange).toHaveBeenCalledWith([60]);
  expectTokenizedClasses(container);
});

test("disabled empêche le déplacement", async () => {
  const onValueChange = vi.fn();
  render(
    <Slider
      aria-label="Opacité"
      value={[50]}
      min={0}
      max={100}
      step={10}
      disabled
      onValueChange={onValueChange}
    />,
  );
  const thumb = screen.getByRole("slider", { name: "Opacité" });
  thumb.focus();
  await userEvent.keyboard("{ArrowRight}");
  expect(onValueChange).not.toHaveBeenCalled();
});
