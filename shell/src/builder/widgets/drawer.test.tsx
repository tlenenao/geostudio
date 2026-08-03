// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
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
  expect(getWidget("drawer")!.actions).toEqual(["open", "close"]);
});

test("closed by default, opens on the open action, closes on Escape and backdrop click", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m1", from: "trigger", event: "clicked", to: "drawer1", action: "open" }]);
  const Drawer = getWidget("drawer")!.Component;
  render(
    <Drawer
      props={{ title: "Filtres", items: [{ id: "c", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Corps" } }], side: "right" }}
      ctx={{ mode: "runtime", bus, widgetId: "drawer1" } as WidgetContext}
    />,
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  bus.emit("trigger", "clicked");
  expect(await screen.findByRole("dialog", { name: "Filtres" })).toBeInTheDocument();
  expect(screen.getByText("Corps")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("edit mode shows a static badge and never opens", () => {
  const Drawer = getWidget("drawer")!.Component;
  render(<Drawer props={{ title: "Filtres", items: [], side: "right" }} ctx={{ mode: "edit" } as WidgetContext} />);
  expect(screen.getByText("Tiroir : Filtres")).toBeInTheDocument();
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("PropsPanel edits the title and the side", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("drawer")!.PropsPanel;
  render(<Panel props={{ title: "Filtres", items: [], side: "right" }} dataSources={[]} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Côté du tiroir"), "left");
  expect(onChange.mock.calls.at(-1)![0].side).toBe("left");
});
