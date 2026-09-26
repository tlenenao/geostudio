// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { expectTokenizedClasses } from "../../ui/kit/testUtils";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

test("PropsPanel edits the markdown source", async () => {
  const onChange = vi.fn();
  const Panel = getWidget("richSection")!.PropsPanel!;
  const { container } = render(<Panel props={{}} dataSources={[]} onChange={onChange} />);
  // SP-B12c : pas de couleur Tailwind de palette codée en dur — un token
  // --gs-* à la place.
  expectTokenizedClasses(container);
  await userEvent.type(screen.getByLabelText("Markdown"), "#");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ markdown: "#" });
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
