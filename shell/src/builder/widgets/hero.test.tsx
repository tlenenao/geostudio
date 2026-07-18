// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ActionBus } from "../ActionBus";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

test("hero declares a cta event", () => {
  expect(getWidget("hero")!.events).toContain("cta");
});

test("hero renders title and subtitle", () => {
  const Hero = getWidget("hero")!.Component;
  render(<Hero props={{ title: "Bienvenue", subtitle: "Un sous-titre" }} ctx={{ mode: "runtime" } as WidgetContext} />);
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
  render(<Hero props={{ title: "Bienvenue", backgroundImageUrl: "https://example.com/bg.png" }} ctx={{ mode: "runtime" } as WidgetContext} />);
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
