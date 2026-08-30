// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Panel } from "./Panel";
import { expectTokenizedClasses } from "./testUtils";

test("rend son contenu avec l'ombre d'élévation md", () => {
  const { container } = render(
    <Panel>
      <p>Contenu</p>
    </Panel>,
  );
  expect(screen.getByText("Contenu")).toBeInTheDocument();
  expect(container.firstChild).toHaveClass("shadow-md");
  expectTokenizedClasses(container);
});
