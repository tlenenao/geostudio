// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import type { ActionMessage, Variable, WidgetItem } from "../api/types";
import { _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { ActionsPanel } from "./ActionsPanel";
import { enableMockAuth } from "../auth/useAuth";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { ItemClient } from "../api/types";
import { expectTokenizedClasses } from "../ui/kit/testUtils";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

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
  const messages: ActionMessage[] = [
    { id: "m1", from: "f1", event: "changed", to: "l1", action: "setFilter" },
  ];
  const { container } = render(
    <ActionsPanel items={items} messages={messages} onChange={onChange} />,
  );
  // SP-B12c : pas de couleur Tailwind de palette codée en dur — un token
  // --gs-* à la place.
  expectTokenizedClasses(container);
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

test("edits a message's condition", async () => {
  const onChange = vi.fn();
  const messages: ActionMessage[] = [
    { id: "m1", from: "f1", event: "changed", to: "l1", action: "setFilter" },
  ];
  render(<ActionsPanel items={items} messages={messages} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Condition de l'action m1"), "vars.x ==");
  expect(onChange).toHaveBeenCalled();
  const next = onChange.mock.calls.at(-1)![0] as ActionMessage[];
  expect(next[0].id).toBe("m1");
  expect(typeof next[0].when).toBe("string");
});

test("shows a validation error for an invalid message condition", () => {
  const messages: ActionMessage[] = [
    { id: "m1", from: "f1", event: "changed", to: "l1", action: "setFilter", when: "vars.x ==" },
  ];
  const { container } = render(
    <ActionsPanel items={items} messages={messages} onChange={vi.fn()} />,
  );
  // D35 : le message brut de cel-js est préfixé « • » (formatCelError),
  // pas affiché tel quel.
  expect(screen.getByRole("alert")).toHaveTextContent("•");
  // SP-B12c : pas de couleur Tailwind de palette codée en dur — un token
  // --gs-* à la place.
  expectTokenizedClasses(container);
});

test("shows no validation error for a valid message condition", () => {
  const messages: ActionMessage[] = [
    {
      id: "m1",
      from: "f1",
      event: "changed",
      to: "l1",
      action: "setFilter",
      when: "vars.x == 'a'",
    },
  ];
  render(<ActionsPanel items={items} messages={messages} onChange={vi.fn()} />);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("offers the CEL generator on an action condition; invalid draft not applied (REV-183)", async () => {
  enableMockAuth();
  const copilotTurn = vi
    .fn()
    .mockResolvedValueOnce({
      reply: "",
      clientOps: [{ op: "applyCelDraft", args: { expression: 'vars.statut == "ok"' } }],
    })
    .mockResolvedValueOnce({
      reply: "",
      clientOps: [{ op: "applyCelDraft", args: { expression: "vars.statut ==" } }],
    });
  const onChange = vi.fn();
  const messages: ActionMessage[] = [
    { id: "m1", from: "f1", event: "changed", to: "l1", action: "setFilter" },
  ];
  const variables: Variable[] = [{ id: "v1", name: "statut", initialValue: "" }];
  render(
    <ItemClientProvider client={{ copilotTurn } as unknown as ItemClient}>
      <ActionsPanel
        items={items}
        variables={variables}
        messages={messages}
        onChange={onChange}
        generateItemId="9"
      />
    </ItemClientProvider>,
  );
  await userEvent.click(await screen.findByText("Générer"));
  await userEvent.type(screen.getByLabelText("Décrire la condition"), "statut ok");
  await userEvent.click(screen.getByRole("button", { name: "Proposer" }));
  await screen.findByText('vars.statut == "ok"');
  expect(copilotTurn.mock.calls[0][1].surface).toBe("action_condition");
  expect(copilotTurn.mock.calls[0][1].currentConfig.availableFields).toContain("vars.statut");
  await userEvent.click(screen.getByRole("button", { name: "Appliquer" }));
  expect(onChange.mock.calls.at(-1)![0][0].when).toBe('vars.statut == "ok"');
  onChange.mockClear();
  await userEvent.click(screen.getByRole("button", { name: "Proposer" }));
  await screen.findByText("vars.statut ==");
  expect(screen.getByRole("button", { name: "Appliquer" })).toBeDisabled();
  expect(onChange).not.toHaveBeenCalled();
});
