// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Field } from "./Field";
import { Input } from "./Input";
import { expectTokenizedClasses } from "./testUtils";

test("associe le label au contrôle via htmlFor/id", () => {
  const { container } = render(
    <Field label="Titre" htmlFor="titre">
      <Input id="titre" />
    </Field>,
  );
  expect(screen.getByLabelText("Titre")).toBeInTheDocument();
  expectTokenizedClasses(container);
});

test("affiche l'erreur avec role=alert quand fournie", () => {
  render(
    <Field label="Titre" htmlFor="titre" error="Champ requis">
      <Input id="titre" />
    </Field>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Champ requis");
});

test("affiche l'indice quand fourni et pas d'erreur", () => {
  render(
    <Field label="Titre" htmlFor="titre" hint="Visible dans le catalogue">
      <Input id="titre" />
    </Field>,
  );
  expect(screen.getByText("Visible dans le catalogue")).toBeInTheDocument();
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
