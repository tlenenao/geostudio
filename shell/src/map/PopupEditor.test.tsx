// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { PopupEditor } from "./PopupEditor";

const fields = ["id", "nom", "population"];

test("enabling the popup posts an empty config, disabling it clears the field", async () => {
  const onChange = vi.fn();
  const { rerender } = render(
    <PopupEditor value={undefined} availableFields={fields} onChange={onChange} />,
  );
  await userEvent.click(screen.getByRole("checkbox", { name: "Afficher les attributs au clic" }));
  expect(onChange).toHaveBeenLastCalledWith({});
  rerender(<PopupEditor value={{}} availableFields={fields} onChange={onChange} />);
  await userEvent.click(screen.getByRole("checkbox", { name: "Afficher les attributs au clic" }));
  expect(onChange).toHaveBeenLastCalledWith(undefined);
});

test("the field controls are hidden while the popup is disabled", () => {
  render(<PopupEditor value={undefined} availableFields={fields} onChange={() => {}} />);
  expect(screen.queryByLabelText("Champ titre")).not.toBeInTheDocument();
});

test("typing a title field posts it", async () => {
  const onChange = vi.fn();
  render(<PopupEditor value={{}} availableFields={fields} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Champ titre"), "n");
  expect(onChange).toHaveBeenLastCalledWith({ titleField: "n" });
});

test("an arbitrary field name can be added when no schema is available", async () => {
  // Surface du widget carte : PropsPanel ne reçoit ni schéma ni
  // enregistrements (registry.ts:33-37), donc availableFields est vide et
  // l'auteur saisit le nom du champ — comme les champs « Champ couleur » et
  // « Champ taille » voisins, qui sont déjà des saisies libres.
  const onChange = vi.fn();
  render(<PopupEditor value={{}} availableFields={[]} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Nom du champ à ajouter"), "nom");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le champ" }));
  expect(onChange).toHaveBeenLastCalledWith({ fields: [{ name: "nom" }] });
});

test("adding a blank field name does nothing", async () => {
  const onChange = vi.fn();
  render(<PopupEditor value={{}} availableFields={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le champ" }));
  expect(onChange).not.toHaveBeenCalled();
});

test("adding a field already in the list does not duplicate it", async () => {
  const onChange = vi.fn();
  render(
    <PopupEditor value={{ fields: [{ name: "nom" }] }} availableFields={[]} onChange={onChange} />,
  );
  await userEvent.type(screen.getByLabelText("Nom du champ à ajouter"), "nom");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le champ" }));
  expect(onChange).not.toHaveBeenCalled();
});

test("checking a field adds it to the list, unchecking removes it", async () => {
  const onChange = vi.fn();
  const { rerender } = render(
    <PopupEditor value={{}} availableFields={fields} onChange={onChange} />,
  );
  await userEvent.click(screen.getByRole("checkbox", { name: "population" }));
  expect(onChange).toHaveBeenLastCalledWith({ fields: [{ name: "population" }] });
  rerender(
    <PopupEditor
      value={{ fields: [{ name: "population" }] }}
      availableFields={fields}
      onChange={onChange}
    />,
  );
  await userEvent.click(screen.getByRole("checkbox", { name: "population" }));
  expect(onChange).toHaveBeenLastCalledWith({ fields: [] });
});

test("a field label can be overridden", async () => {
  const onChange = vi.fn();
  render(
    <PopupEditor
      value={{ fields: [{ name: "population" }] }}
      availableFields={fields}
      onChange={onChange}
    />,
  );
  await userEvent.type(screen.getByLabelText("Libellé de population"), "H");
  expect(onChange).toHaveBeenLastCalledWith({ fields: [{ name: "population", label: "H" }] });
});

test("the advanced mode posts a template", async () => {
  const onChange = vi.fn();
  render(<PopupEditor value={{}} availableFields={fields} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Avancé (gabarit)" }));
  await userEvent.type(screen.getByLabelText("Gabarit"), "x");
  expect(onChange).toHaveBeenLastCalledWith({ template: "x" });
});

test("an invalid placeholder is reported without blocking typing", async () => {
  render(
    <PopupEditor value={{ template: "${(((}" }} availableFields={fields} onChange={() => {}} />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Expression invalide");
});

test("an unclosed placeholder is reported", () => {
  render(
    <PopupEditor
      value={{ template: "${record.nom" }}
      availableFields={fields}
      onChange={() => {}}
    />,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("Expression non fermée");
});

test("a valid template reports nothing", () => {
  render(
    <PopupEditor
      value={{ template: "${record.nom}" }}
      availableFields={fields}
      onChange={() => {}}
    />,
  );
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});
