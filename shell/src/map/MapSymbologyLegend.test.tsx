// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { MapSymbologyLegend } from "./MapSymbologyLegend";

// Tâche 35 (SP-C6, D15) : extraction pure de mapWidget.tsx — reprend un cas
// déjà couvert par mapWidget.test.tsx ("shows a categorical symbology legend
// from frozen props.symbology") pour la même fonction, juste importée
// d'ailleurs. Comportement inchangé attendu.
test("rend une entrée de légende catégorielle", () => {
  render(
    <MapSymbologyLegend
      legend={{
        color: { kind: "categorical", field: "type", entries: [{ value: "A", color: "#ff0000" }] },
      }}
    />,
  );
  expect(screen.getByText("A")).toBeInTheDocument();
});

// ARC-17 : légendes des modes avancés.
test("légende bivariée : 9 cases et libellé des axes", () => {
  const colors = Array.from({ length: 9 }, (_, i) => `#00000${i}`);
  const { container } = render(
    <MapSymbologyLegend
      legend={{ advanced: { kind: "bivariate", fieldX: "pop", fieldY: "rev", colors } }}
    />,
  );
  expect(container.querySelectorAll(".grid > span")).toHaveLength(9);
  expect(screen.getByText(/pop.*rev/)).toBeInTheDocument();
});

test("légende prédominante, comparer et densité de points", () => {
  const { rerender } = render(
    <MapSymbologyLegend
      legend={{
        advanced: {
          kind: "predominant",
          entries: [
            { value: "oui", color: "#111111" },
            { value: "non", color: "#222222" },
          ],
        },
      }}
    />,
  );
  expect(screen.getByText("oui")).toBeInTheDocument();
  rerender(
    <MapSymbologyLegend
      legend={{
        advanced: {
          kind: "compare",
          fieldA: "a2024",
          fieldB: "a2020",
          maxAbs: 12,
          colorLow: "#111111",
          colorMid: "#222222",
          colorHigh: "#333333",
        },
      }}
    />,
  );
  expect(screen.getByText("a2024 − a2020")).toBeInTheDocument();
  rerender(
    <MapSymbologyLegend
      legend={{
        advanced: { kind: "dotDensity", field: "pop", valuePerDot: 100, color: "#111111" },
      }}
    />,
  );
  expect(screen.getByText("1 point = 100 (pop)")).toBeInTheDocument();
});
