import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import { PropsPanel } from "./PropsPanel";
import type { WidgetItem } from "../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const item: WidgetItem = { id: "t", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } };

test("edits the selected widget's props", async () => {
  const onChange = vi.fn();
  render(<PropsPanel item={item} onChange={onChange} />);
  const area = screen.getByLabelText("Texte du widget");
  await userEvent.type(area, "!");
  expect(onChange).toHaveBeenCalled();
  const last = onChange.mock.calls.at(-1)![0];
  expect(String(last.text).startsWith("Hi")).toBe(true);
});

test("shows a placeholder when nothing is selected", () => {
  render(<PropsPanel item={null} onChange={vi.fn()} />);
  expect(screen.getByText(/aucun widget/i)).toBeInTheDocument();
});
