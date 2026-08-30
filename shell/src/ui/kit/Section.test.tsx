// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Section } from "./Section";
import { expectTokenizedClasses } from "./testUtils";

test("rend un titre de section et son contenu", () => {
  const { container } = render(
    <Section title="Permissions">
      <p>Détail</p>
    </Section>,
  );
  expect(screen.getByRole("heading", { name: "Permissions" })).toBeInTheDocument();
  expect(screen.getByText("Détail")).toBeInTheDocument();
  expectTokenizedClasses(container);
});
