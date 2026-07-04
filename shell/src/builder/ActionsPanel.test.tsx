import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import type { ActionMessage, Variable, WidgetItem } from "../api/types";
import { _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { ActionsPanel } from "./ActionsPanel";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const items: WidgetItem[] = [
  { id: "f1", widget: "filter", x: 0, y: 0, w: 3, h: 1, props: {} },
  { id: "l1", widget: "list", x: 0, y: 0, w: 4, h: 4, props: {} },
];

test("composes a message from emitter/event to target/action", async () => {
  const onChange = vi.fn();
  render(<ActionsPanel items={items} messages={[]} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Widget émetteur"), "f1");
  await userEvent.selectOptions(screen.getByLabelText("Événement"), "changed");
  await userEvent.selectOptions(screen.getByLabelText("Widget cible"), "l1");
  await userEvent.selectOptions(screen.getByLabelText("Action"), "setFilter");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une action" }));
  const next = onChange.mock.calls.at(-1)![0] as ActionMessage[];
  expect(next).toHaveLength(1);
  expect(next[0]).toMatchObject({ from: "f1", event: "changed", to: "l1", action: "setFilter" });
});

test("removes a message", async () => {
  const onChange = vi.fn();
  const messages: ActionMessage[] = [{ id: "m1", from: "f1", event: "changed", to: "l1", action: "setFilter" }];
  render(<ActionsPanel items={items} messages={messages} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Retirer l'action m1" }));
  expect(onChange).toHaveBeenCalledWith([]);
});

test("wires an emitter to a variable's set action", async () => {
  const onChange = vi.fn();
  const variables: Variable[] = [{ id: "v1", name: "message", initialValue: "" }];
  render(<ActionsPanel items={items} variables={variables} messages={[]} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Widget émetteur"), "f1");
  await userEvent.selectOptions(screen.getByLabelText("Événement"), "changed");
  await userEvent.selectOptions(screen.getByLabelText("Widget cible"), "var:v1");
  await userEvent.selectOptions(screen.getByLabelText("Action"), "set");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une action" }));
  const next = onChange.mock.calls.at(-1)![0] as ActionMessage[];
  expect(next).toHaveLength(1);
  expect(next[0]).toMatchObject({ from: "f1", event: "changed", to: "var:v1", action: "set" });
});

test("hides a message whose endpoints are not on the current page", () => {
  const messages: ActionMessage[] = [
    { id: "m1", from: "f1", event: "changed", to: "l1", action: "setFilter" },
    { id: "m2", from: "ghost", event: "changed", to: "l1", action: "setFilter" },
  ];
  render(<ActionsPanel items={items} messages={messages} onChange={vi.fn()} />);
  expect(screen.getByText("Filtre.changed → Liste.setFilter")).toBeInTheDocument();
  expect(screen.queryByText(/ghost/)).not.toBeInTheDocument();
});
