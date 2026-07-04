import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { Variable } from "../api/types";
import { VariablesPanel } from "./VariablesPanel";

test("adds a variable with an empty initial value", async () => {
  const onChange = vi.fn();
  render(<VariablesPanel variables={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une variable" }));
  const next = onChange.mock.calls[0][0] as Variable[];
  expect(next).toHaveLength(1);
  expect(next[0].name).toBe("Variable 1");
  expect(next[0].initialValue).toBe("");
});

test("renames a variable", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "", initialValue: "" }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Renommer la variable v1"), "message");
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(next[0].name).toBe("message");
});

test("edits a variable's initial value", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "message", initialValue: "" }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Valeur initiale de la variable v1"), "salut");
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(next[0].initialValue).toBe("salut");
});

test("removes a variable", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "message", initialValue: "" }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Retirer la variable v1" }));
  expect(onChange).toHaveBeenCalledWith([]);
});
