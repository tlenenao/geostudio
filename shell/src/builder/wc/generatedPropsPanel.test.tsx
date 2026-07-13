import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState } from "react";
import { expect, test, vi } from "vitest";
import { makeGeneratedPropsPanel } from "./generatedPropsPanel";
import type { WcWidgetManifest } from "./manifest";

// Panel is a plain controlled component: like the real PropsPanel usage in
// the builder, onChange must feed back into props for typed input to work
// (otherwise React's controlled-value reset fights every keystroke).
function renderControlled(
  Panel: ReturnType<typeof makeGeneratedPropsPanel>,
  initial: Record<string, unknown>,
  onChange: (props: Record<string, unknown>) => void,
) {
  function Wrapper() {
    const [props, setProps] = useState(initial);
    return (
      <Panel
        props={props}
        onChange={(p) => {
          setProps(p);
          onChange(p);
        }}
      />
    );
  }
  return render(<Wrapper />);
}

const manifest: WcWidgetManifest = {
  type: "test.panel",
  tag: "test-panel-widget",
  label: "Test panneau",
  props: [
    { name: "initial", type: "number", label: "Valeur initiale", default: 0 },
    { name: "title", type: "string", label: "Titre", default: "" },
    { name: "loud", type: "boolean", label: "Bruyant", default: false },
  ],
  defaultSize: { w: 2, h: 2 },
};

test("renders one field per manifest prop, typed accordingly", () => {
  const Panel = makeGeneratedPropsPanel(manifest);
  render(<Panel props={{ initial: 3, title: "X", loud: true }} onChange={() => {}} />);
  expect(screen.getByLabelText("Valeur initiale")).toHaveAttribute("type", "number");
  expect(screen.getByLabelText("Valeur initiale")).toHaveValue(3);
  expect(screen.getByLabelText("Titre")).toHaveAttribute("type", "text");
  expect(screen.getByLabelText("Titre")).toHaveValue("X");
  expect(screen.getByLabelText("Bruyant")).toHaveAttribute("type", "checkbox");
  expect(screen.getByLabelText("Bruyant")).toBeChecked();
});

test("editing a number field calls onChange with a coerced number", async () => {
  const Panel = makeGeneratedPropsPanel(manifest);
  const onChange = vi.fn();
  renderControlled(Panel, { initial: 3, title: "", loud: false }, onChange);
  await userEvent.clear(screen.getByLabelText("Valeur initiale"));
  await userEvent.type(screen.getByLabelText("Valeur initiale"), "7");
  expect(onChange).toHaveBeenLastCalledWith({ initial: 7, title: "", loud: false });
});

test("editing a boolean field calls onChange with a boolean", async () => {
  const Panel = makeGeneratedPropsPanel(manifest);
  const onChange = vi.fn();
  renderControlled(Panel, { initial: 3, title: "", loud: false }, onChange);
  await userEvent.click(screen.getByLabelText("Bruyant"));
  expect(onChange).toHaveBeenLastCalledWith({ initial: 3, title: "", loud: true });
});
