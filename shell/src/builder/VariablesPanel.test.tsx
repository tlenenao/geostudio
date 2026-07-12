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

test("adds a variable defaulting to type string", async () => {
  const onChange = vi.fn();
  render(<VariablesPanel variables={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une variable" }));
  const next = onChange.mock.calls[0][0] as Variable[];
  expect(next[0].type).toBe("string");
});

test("changes a variable's type and resets its initial value to a default for that type", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "count", type: "string", initialValue: "abc" }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Type de la variable v1"), "number");
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(next[0].type).toBe("number");
  expect(next[0].initialValue).toBe(0);
});

test("edits a number variable's initial value as a number", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "count", type: "number", initialValue: 0 }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Valeur initiale de la variable v1"), "5");
  const next = onChange.mock.calls.at(-1)![0] as Variable[];
  expect(typeof next[0].initialValue).toBe("number");
});

test("toggles a bool variable's initial value", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "gate", type: "bool", initialValue: false }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  await userEvent.click(screen.getByLabelText("Valeur initiale de la variable v1"));
  expect(onChange).toHaveBeenCalledWith([{ id: "v1", name: "gate", type: "bool", initialValue: true }]);
});

test("shows no editable initial value for a record-typed variable", () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "selected", type: "record", initialValue: null }];
  render(<VariablesPanel variables={variables} onChange={onChange} />);
  expect(screen.queryByLabelText("Valeur initiale de la variable v1")).not.toBeInTheDocument();
  expect(screen.getByText("Définie par câblage d'action")).toBeInTheDocument();
});
