// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";
import { isSafeHref } from "./hero";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

// Plusieurs tests font vi.spyOn(window, "open") : sans restauration, un
// second spyOn sur la même méthode réutilise l'espion existant (son
// historique d'appels y compris) au lieu d'en créer un nouveau.
afterEach(() => {
  vi.restoreAllMocks();
});

test("hero declares a cta event", () => {
  expect(getWidget("hero")!.events).toContain("cta");
});

test("hero renders title and subtitle", () => {
  const Hero = getWidget("hero")!.Component;
  render(
    <Hero
      props={{ title: "Bienvenue", subtitle: "Un sous-titre" }}
      ctx={{ mode: "runtime" } as WidgetContext}
    />,
  );
  expect(screen.getByText("Bienvenue")).toBeInTheDocument();
  expect(screen.getByText("Un sous-titre")).toBeInTheDocument();
});

test("hero without ctaLabel renders no button", () => {
  const Hero = getWidget("hero")!.Component;
  render(<Hero props={{ title: "Bienvenue" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.queryByRole("button")).not.toBeInTheDocument();
});

test("hero without backgroundImageUrl falls back to a theme color flat background", () => {
  const Hero = getWidget("hero")!.Component;
  render(<Hero props={{ title: "Bienvenue" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  const container = screen.getByText("Bienvenue").parentElement!;
  expect(container).toHaveStyle({ backgroundColor: "var(--gs-color-primary)" });
});

test("hero with backgroundImageUrl renders it as a CSS background-image", () => {
  const Hero = getWidget("hero")!.Component;
  render(
    <Hero
      props={{ title: "Bienvenue", backgroundImageUrl: "https://example.com/bg.png" }}
      ctx={{ mode: "runtime" } as WidgetContext}
    />,
  );
  const container = screen.getByText("Bienvenue").parentElement!;
  expect(container.style.backgroundImage).toContain("https://example.com/bg.png");
});

test("hero cta click emits the wired action and opens ctaHref in a new tab", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("sink", "run", handler);
  bus.configure([{ id: "m", from: "hero1", event: "cta", to: "sink", action: "run" }]);
  const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

  const Hero = getWidget("hero")!.Component;
  render(
    <Hero
      props={{ title: "Bienvenue", ctaLabel: "Voir", ctaHref: "https://example.com" }}
      ctx={{ mode: "runtime", bus, widgetId: "hero1" } as WidgetContext}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Voir" }));
  expect(handler).toHaveBeenCalled();
  expect(openSpy).toHaveBeenCalledWith("https://example.com", "_blank", "noopener");
});

test("hero cta click with a javascript: ctaHref does not open a window", async () => {
  const bus = new ActionBus();
  const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

  const Hero = getWidget("hero")!.Component;
  render(
    <Hero
      props={{ title: "Bienvenue", ctaLabel: "Voir", ctaHref: "javascript:alert(1)" }}
      ctx={{ mode: "runtime", bus, widgetId: "hero1" } as WidgetContext}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Voir" }));
  expect(openSpy).not.toHaveBeenCalled();
});

test("isSafeHref rejects an unparseable href", () => {
  expect(isSafeHref("http://[::1")).toBe(false);
});

test("hero PropsPanel edits title, subtitle, background image, cta label and href", async () => {
  const onChange = vi.fn();
  const PropsPanel = getWidget("hero")!.PropsPanel!;
  render(
    <PropsPanel
      props={{ title: "Bienvenue" }}
      onChange={onChange}
      ctx={{ mode: "edit" } as WidgetContext}
    />,
  );
  await userEvent.type(screen.getByLabelText("Titre du bandeau"), "!");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ title: "Bienvenue!" });

  await userEvent.type(screen.getByLabelText("Sous-titre"), "s");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ subtitle: "s" });

  await userEvent.type(screen.getByLabelText("URL de l'image de fond"), "u");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ backgroundImageUrl: "u" });

  await userEvent.type(screen.getByLabelText("Libellé du CTA"), "c");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ ctaLabel: "c" });

  await userEvent.type(screen.getByLabelText("Lien du CTA"), "h");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ ctaHref: "h" });
});

test("hero PropsPanel switches alignment to center", async () => {
  const onChange = vi.fn();
  const PropsPanel = getWidget("hero")!.PropsPanel!;
  render(
    <PropsPanel
      props={{ title: "Bienvenue", align: "left" }}
      onChange={onChange}
      ctx={{ mode: "edit" } as WidgetContext}
    />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Alignement"), "center");
  expect(onChange.mock.calls.at(-1)![0]).toMatchObject({ align: "center" });
});

test("hero with align center centers its content", () => {
  const Hero = getWidget("hero")!.Component;
  render(
    <Hero
      props={{ title: "Bienvenue", align: "center" }}
      ctx={{ mode: "runtime" } as WidgetContext}
    />,
  );
  expect(screen.getByText("Bienvenue").parentElement).toHaveClass("items-center", "text-center");
});

test("hero cta click with a relative ctaHref still opens it", async () => {
  const bus = new ActionBus();
  const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);

  const Hero = getWidget("hero")!.Component;
  render(
    <Hero
      props={{ title: "Bienvenue", ctaLabel: "Voir", ctaHref: "/some-page" }}
      ctx={{ mode: "runtime", bus, widgetId: "hero1" } as WidgetContext}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Voir" }));
  expect(openSpy).toHaveBeenCalledWith("/some-page", "_blank", "noopener");
});
