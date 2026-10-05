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

test("pose aria-invalid et aria-describedby sur le contrôle quand une erreur est fournie", () => {
  render(
    <Field label="Titre" htmlFor="titre" error="Champ requis" hint="ignoré">
      <Input id="titre" />
    </Field>,
  );
  const input = screen.getByLabelText("Titre");
  expect(input).toHaveAttribute("aria-invalid", "true");
  expect(input).toHaveAccessibleDescription("Champ requis");
});

test("sans erreur : l'indice décrit le contrôle, pas d'aria-invalid", () => {
  render(
    <Field label="Titre" htmlFor="titre" hint="Visible dans le catalogue">
      <Input id="titre" />
    </Field>,
  );
  const input = screen.getByLabelText("Titre");
  expect(input).not.toHaveAttribute("aria-invalid");
  expect(input).toHaveAccessibleDescription("Visible dans le catalogue");
});

test("ne pose rien sur l'enfant sans erreur ni indice", () => {
  render(
    <Field label="Titre" htmlFor="titre">
      <Input id="titre" aria-describedby="ext" aria-invalid />
    </Field>,
  );
  const input = screen.getByLabelText("Titre");
  expect(input).toHaveAttribute("aria-describedby", "ext");
  expect(input).toHaveAttribute("aria-invalid", "true");
});

test("fusionne aria-describedby de l'enfant et conserve son aria-invalid", () => {
  render(
    <>
      <p id="ext">Aide externe</p>
      <Field label="Titre" htmlFor="titre" error="Champ requis">
        <Input id="titre" aria-describedby="ext" aria-invalid="grammar" />
      </Field>
    </>,
  );
  const input = screen.getByLabelText("Titre");
  expect(input).toHaveAttribute("aria-describedby", "ext titre-error");
  expect(input).toHaveAttribute("aria-invalid", "grammar");
});
