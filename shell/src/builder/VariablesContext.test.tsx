import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test } from "vitest";
import type { Variable } from "../api/types";
import { VariablesProvider, useVariables, useSetVariable } from "./VariablesContext";

function Probe() {
  const values = useVariables();
  const setVariable = useSetVariable();
  return (
    <div>
      <p>message:{values.message ?? "unset"}</p>
      <p>count:{values.count ?? "unset"}</p>
      <button onClick={() => setVariable("message", "hello")}>set</button>
    </div>
  );
}

test("seeds values from each variable's initialValue", () => {
  const variables: Variable[] = [{ id: "v1", name: "message", initialValue: "salut" }];
  render(<VariablesProvider variables={variables}><Probe /></VariablesProvider>);
  expect(screen.getByText("message:salut")).toBeInTheDocument();
});

test("useSetVariable updates the value read by useVariables", async () => {
  const variables: Variable[] = [{ id: "v1", name: "message", initialValue: "" }];
  render(<VariablesProvider variables={variables}><Probe /></VariablesProvider>);
  await userEvent.click(screen.getByRole("button", { name: "set" }));
  expect(screen.getByText("message:hello")).toBeInTheDocument();
});

test("picks up a variable added after the provider first mounted", async () => {
  const variables: Variable[] = [{ id: "v1", name: "message", initialValue: "salut" }];
  const { rerender } = render(<VariablesProvider variables={variables}><Probe /></VariablesProvider>);
  const next: Variable[] = [...variables, { id: "v2", name: "count", initialValue: "0" }];
  rerender(<VariablesProvider variables={next}><Probe /></VariablesProvider>);
  await waitFor(() => expect(screen.getByText("count:0")).toBeInTheDocument());
  expect(screen.getByText("message:salut")).toBeInTheDocument(); // untouched
});
