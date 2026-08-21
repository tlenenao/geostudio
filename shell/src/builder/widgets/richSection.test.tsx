// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

test("richSection renders sanitized Markdown", () => {
  const RichSection = getWidget("richSection")!.Component;
  render(
    <RichSection
      props={{ markdown: "# Titre\n\n**gras**" }}
      ctx={{ mode: "runtime" } as WidgetContext}
    />,
  );
  expect(screen.getByRole("heading", { level: 1, name: "Titre" })).toBeInTheDocument();
  expect(screen.getByText("gras").tagName).toBe("STRONG");
});

test("richSection strips a script tag (adversarial)", () => {
  const RichSection = getWidget("richSection")!.Component;
  const { container } = render(
    <RichSection
      props={{ markdown: "# Titre\n\n<script>window.__pwned = true;</script>" }}
      ctx={{ mode: "runtime" } as WidgetContext}
    />,
  );
  expect(container.querySelector("script")).toBeNull();
});

test("richSection shows a discreet placeholder in edit mode when markdown is empty", () => {
  const RichSection = getWidget("richSection")!.Component;
  render(<RichSection props={{ markdown: "" }} ctx={{ mode: "edit" } as WidgetContext} />);
  expect(screen.getByText(/vide/i)).toBeInTheDocument();
});

test("richSection renders nothing when markdown is empty outside edit mode", () => {
  const RichSection = getWidget("richSection")!.Component;
  const { container } = render(
    <RichSection props={{ markdown: "" }} ctx={{ mode: "runtime" } as WidgetContext} />,
  );
  expect(container).toBeEmptyDOMElement();
});
