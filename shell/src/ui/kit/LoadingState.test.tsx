// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, it } from "vitest";
import { LoadingState } from "./LoadingState";
import { t } from "../../i18n";
import { expectTokenizedClasses } from "./testUtils";

it("affiche un indicateur de chargement avec le libellé par défaut", () => {
  const { container } = render(<LoadingState />);
  expect(screen.getByRole("status")).toHaveTextContent(t("common.loading"));
  expectTokenizedClasses(container);
});

it("accepte un libellé personnalisé", () => {
  const { container } = render(<LoadingState label="Chargement des couches…" />);
  expect(screen.getByRole("status")).toHaveTextContent("Chargement des couches…");
  expectTokenizedClasses(container);
});
