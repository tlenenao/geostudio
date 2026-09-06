// SPDX-License-Identifier: Apache-2.0
// Vérifie : (1) le PropsPanel liste les variables disponibles par nom ;
// (2) le Component en mode edit rend un contrôle désactivé ; (3) en mode
// preview/runtime, taper dans le contrôle appelle useSetVariable avec le
// nom courant de la variable référencée par id (pas un nom figé) ; (4) le
// type de contrôle suit VariableType (number → input[type=number], bool →
// checkbox, date → input[type=date], string → text) ; (5) un variableId
// qui ne résout plus affiche un état "Variable introuvable" sans planter.
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import type { Variable } from "../../api/types";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { VariablesProvider } from "../VariablesContext";
import { registerBuiltinWidgets } from "./index";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

test("PropsPanel lists the app's variables by name", () => {
  const variables: Variable[] = [
    { id: "v1", name: "seuil", type: "number", initialValue: 0 },
    { id: "v2", name: "message", type: "string", initialValue: "" },
  ];
  const Panel = getWidget("variableInput")!.PropsPanel;
  render(
    <Panel
      props={{ variableId: "", label: "" }}
      dataSources={[]}
      onChange={vi.fn()}
      variables={variables}
    />,
  );
  const select = screen.getByLabelText("Variable liée");
  expect(screen.getByRole("option", { name: "seuil" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "message" })).toBeInTheDocument();
  expect(select).toBeInTheDocument();
});

test("edit mode renders a disabled control", () => {
  const variables: Variable[] = [{ id: "v1", name: "seuil", type: "number", initialValue: 0 }];
  const Widget = getWidget("variableInput")!.Component;
  render(
    <VariablesProvider variables={variables}>
      <Widget props={{ variableId: "v1", label: "" }} ctx={{ mode: "edit" } as WidgetContext} />
    </VariablesProvider>,
  );
  expect(screen.getByLabelText("seuil")).toBeDisabled();
});

test("typing in preview mode calls useSetVariable with the variable's current name", async () => {
  const variables: Variable[] = [{ id: "v1", name: "seuil", type: "number", initialValue: 0 }];
  function Probe() {
    return (
      <VariablesProvider variables={variables}>
        <ProbeInner />
      </VariablesProvider>
    );
  }
  function ProbeInner() {
    const Widget = getWidget("variableInput")!.Component;
    return (
      <Widget props={{ variableId: "v1", label: "" }} ctx={{ mode: "preview" } as WidgetContext} />
    );
  }
  render(<Probe />);
  const input = screen.getByLabelText("seuil");
  expect(input).not.toBeDisabled();
  await userEvent.clear(input);
  await userEvent.type(input, "42");
  expect(input).toHaveValue(42);
});

test("the control type follows the variable's VariableType", () => {
  const cases: Array<{ variable: Variable; expectedType: string }> = [
    {
      variable: { id: "v1", name: "n", type: "number", initialValue: 0 },
      expectedType: "number",
    },
    {
      variable: { id: "v1", name: "n", type: "bool", initialValue: false },
      expectedType: "checkbox",
    },
    {
      variable: { id: "v1", name: "n", type: "date", initialValue: "" },
      expectedType: "date",
    },
    {
      variable: { id: "v1", name: "n", type: "string", initialValue: "" },
      expectedType: "text",
    },
  ];
  for (const { variable, expectedType } of cases) {
    const Widget = getWidget("variableInput")!.Component;
    const { unmount } = render(
      <VariablesProvider variables={[variable]}>
        <Widget
          props={{ variableId: "v1", label: "" }}
          ctx={{ mode: "preview" } as WidgetContext}
        />
      </VariablesProvider>,
    );
    expect(screen.getByLabelText("n")).toHaveAttribute("type", expectedType);
    unmount();
  }
});

test("a variableId that no longer resolves shows an error state without crashing", () => {
  const Widget = getWidget("variableInput")!.Component;
  render(
    <VariablesProvider variables={[]}>
      <Widget
        props={{ variableId: "gone", label: "" }}
        ctx={{ mode: "preview" } as WidgetContext}
      />
    </VariablesProvider>,
  );
  expect(screen.getByText("Variable introuvable.")).toBeInTheDocument();
});
