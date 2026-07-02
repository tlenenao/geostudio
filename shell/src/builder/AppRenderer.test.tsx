import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { AppRenderer } from "./AppRenderer";
import type { AppConfig } from "../api/types";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

const config: AppConfig = {
  kind: "app", theme: {}, dataSources: [], messages: [],
  layout: { type: "grid", breakpoints: {}, items: [
    { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Salut" } },
  ] },
};

test("runtime mode renders widgets without edit chrome", () => {
  render(<AppRenderer config={config} mode="runtime" />);
  expect(screen.getByText("Salut")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /Sélectionner/ })).toBeNull();
});

test("edit mode moving a widget calls onChange with the new position", async () => {
  const onChange = vi.fn();
  render(<AppRenderer config={config} mode="edit" selectedId="t1" onSelect={vi.fn()} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-t1 à droite" }));
  const next = onChange.mock.calls[0][0] as AppConfig;
  expect(next.layout.items[0]).toMatchObject({ x: 1 });
});
