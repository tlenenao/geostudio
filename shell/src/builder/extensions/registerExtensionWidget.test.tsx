// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import type { WidgetContext } from "../registry";
import { registerExtensionWidget } from "./registerExtensionWidget";
import { _resetModuleCache } from "./moduleCache";
import type { ExtensionManifest } from "../../api/types";

const manifest: ExtensionManifest = {
  type: "acme.gauge", tag: "test-lazy-ready-widget", label: "Jauge (extension)",
  props: [{ name: "initial", type: "number", label: "Valeur initiale", default: 7 }],
  events: ["changed"], actions: ["reset"],
  defaultSize: { w: 3, h: 2 },
  moduleUrl: "./__fixtures__/dummyLazyWidget.ts",
};

beforeEach(() => {
  _resetRegistry();
  _resetModuleCache();
});

test("registers a WidgetDefinition with the manifest's identity and defaults", () => {
  registerExtensionWidget(manifest);
  const def = getWidget("acme.gauge")!;
  expect(def.label).toBe("Jauge (extension)");
  expect(def.defaultProps).toEqual({ initial: 7 });
  expect(def.defaultSize).toEqual({ w: 3, h: 2 });
  expect(def.events).toEqual(["changed"]);
  expect(def.actions).toEqual(["reset"]);
});

test("the generated props panel edits props through onChange", async () => {
  registerExtensionWidget(manifest);
  const Panel = getWidget("acme.gauge")!.PropsPanel;
  const onChange = vi.fn();
  // Panel is a plain controlled component: onChange must feed back into
  // props (as the real PropsPanel does) or React's controlled-value reset
  // fights every keystroke (cf. generatedPropsPanel.test.tsx, SP-8a).
  function Wrapper() {
    const [props, setProps] = useState<Record<string, unknown>>({ initial: 7 });
    return (
      <Panel
        props={props}
        dataSources={[]}
        onChange={(p) => {
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

test("the generated Component lazily mounts the custom element", async () => {
  registerExtensionWidget(manifest);
  const Component = getWidget("acme.gauge")!.Component;
  const { container } = render(
    <Component props={{ initial: 9 }} ctx={{ mode: "runtime" } as WidgetContext} />,
  );
  await waitFor(() => expect(container.querySelector("test-lazy-ready-widget")).not.toBeNull());
});
