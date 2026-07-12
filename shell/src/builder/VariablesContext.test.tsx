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
      <p>message:{String(values.message ?? "unset")}</p>
      <p>count:{String(values.count ?? "unset")}</p>
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

test("useVariables and useSetVariable carry non-string values (number, bool, object, array)", async () => {
  function Probe2() {
    const values = useVariables();
    const setVariable = useSetVariable();
    return (
      <div>
        <p>count:{String(values.count)}</p>
        <button onClick={() => setVariable("count", 42)}>set-number</button>
        <button onClick={() => setVariable("selected", { nom: "A" })}>set-record</button>
      </div>
    );
  }
  render(<VariablesProvider variables={[{ id: "v1", name: "count", type: "number", initialValue: 0 }]}><Probe2 /></VariablesProvider>);
  expect(screen.getByText("count:0")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "set-number" }));
  expect(screen.getByText("count:42")).toBeInTheDocument();
});
