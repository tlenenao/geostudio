// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { EmptyState } from "./EmptyState";
import { Button } from "./Button";
import { expectTokenizedClasses } from "./testUtils";

test("rend titre, description et l'action fournie", () => {
  const { container } = render(
    <EmptyState
      title="Aucun résultat"
      description="Essayez un autre filtre."
      action={<Button>Réinitialiser</Button>}
    />,
  );
  expect(screen.getByText("Aucun résultat")).toBeInTheDocument();
  expect(screen.getByText("Essayez un autre filtre.")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Réinitialiser" })).toBeInTheDocument();
  expectTokenizedClasses(container);
});
