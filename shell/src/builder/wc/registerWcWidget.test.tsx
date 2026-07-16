// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import type { WidgetContext } from "../registry";
import { registerWcWidget } from "./registerWcWidget";
import type { WcWidgetManifest } from "./manifest";

class RegisterTestWidget extends HTMLElement {
  props?: unknown;
}
if (!customElements.get("register-test-widget")) {
  customElements.define("register-test-widget", RegisterTestWidget);
}

const manifest: WcWidgetManifest = {
  type: "test.register",
  tag: "register-test-widget",
  label: "Test enregistré",
  props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 7 }],
  events: ["changed"],
  actions: ["reset"],
  defaultSize: { w: 3, h: 2 },
};

beforeEach(() => _resetRegistry());

test("registers a WidgetDefinition with the manifest's identity and defaults", () => {
  registerWcWidget(manifest);
  const def = getWidget("test.register")!;
  expect(def.label).toBe("Test enregistré");
  expect(def.defaultProps).toEqual({ initial: 7 });
  expect(def.defaultSize).toEqual({ w: 3, h: 2 });
  expect(def.events).toEqual(["changed"]);
  expect(def.actions).toEqual(["reset"]);
});

test("the generated props panel edits props through onChange", async () => {
  registerWcWidget(manifest);
  const Panel = getWidget("test.register")!.PropsPanel;
  const onChange = vi.fn();
  // Feed onChange back into props, like the real PropsPanel usage in the
  // builder — a controlled number input otherwise fights React's value reset.
  function Wrapper() {
    const [props, setProps] = useState<Record<string, unknown>>({ initial: 7 });
    return (
      <Panel
        props={props}
        dataSources={[]}
        onChange={(p: Record<string, unknown>) => {
          setProps(p);
          onChange(p);
        }}
      />
    );
  }
  render(<Wrapper />);
  await userEvent.clear(screen.getByLabelText("Valeur initiale"));
  await userEvent.type(screen.getByLabelText("Valeur initiale"), "9");
  expect(onChange).toHaveBeenLastCalledWith({ initial: 9 });
});

test("the generated Component mounts the custom element with its props", () => {
  registerWcWidget(manifest);
  const Component = getWidget("test.register")!.Component;
  const { container } = render(
    <Component props={{ initial: 9 }} ctx={{ mode: "runtime" } as WidgetContext} />,
  );
  const el = container.querySelector("register-test-widget") as RegisterTestWidget;
  expect(el.props).toEqual({ initial: 9 });
});
