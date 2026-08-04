// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";
import type { AuthState } from "../../auth/useAuth";

const authState: AuthState = {
  isLoading: false, isAuthenticated: true, username: "tanguy",
  error: null, getAccessToken: () => "t", signIn: vi.fn(), signOut: vi.fn(),
};
vi.mock("../../auth/useAuth", () => ({ useAuth: () => authState }));

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

test("declares open/close actions", () => {
  expect(getWidget("modal")!.actions).toEqual(["open", "close"]);
});

test("closed by default, opens on the open action, closes on Escape", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m1", from: "trigger", event: "clicked", to: "modal1", action: "open" }]);
  const Modal = getWidget("modal")!.Component;
  render(
    <Modal
      props={{ title: "Détail", items: [{ id: "c", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Corps" } }] }}
      ctx={{ mode: "runtime", bus, widgetId: "modal1" } as WidgetContext}
    />,
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  bus.emit("trigger", "clicked");
  expect(await screen.findByRole("dialog", { name: "Détail" })).toBeInTheDocument();
  expect(screen.getByText("Corps")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("closes on the close action too", async () => {
  const bus = new ActionBus();
  bus.configure([
    { id: "m1", from: "opener", event: "clicked", to: "modal1", action: "open" },
    { id: "m2", from: "closer", event: "clicked", to: "modal1", action: "close" },
  ]);
  const Modal = getWidget("modal")!.Component;
  render(<Modal props={{ title: "Détail", items: [] }} ctx={{ mode: "runtime", bus, widgetId: "modal1" } as WidgetContext} />);
  bus.emit("opener", "clicked");
  expect(await screen.findByRole("dialog")).toBeInTheDocument();
  bus.emit("closer", "clicked");
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("edit mode shows a static badge and never opens", () => {
  const Modal = getWidget("modal")!.Component;
  render(<Modal props={{ title: "Détail", items: [] }} ctx={{ mode: "edit" } as WidgetContext} />);
  expect(screen.getByText("Modale : Détail")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("PropsPanel edits the title and the wide flag", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("modal")!.PropsPanel;
  render(<Panel props={{ title: "Détail", items: [] }} dataSources={[]} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Titre de la modale"), "!");
  expect(onChange.mock.calls.at(-1)![0].title).toBe("Détail!");
  await userEvent.click(screen.getByLabelText("Modale large"));
  expect(onChange.mock.calls.at(-1)![0].wide).toBe(true);
});
