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
