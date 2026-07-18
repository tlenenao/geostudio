// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { NavigationPanel } from "./NavigationPanel";
import { _resetRegistry } from "./registry";
import { registerBuiltinWidgets } from "./widgets";
import type { Page } from "../api/types";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

function pageWithMap(): Page {
  return {
    id: "p1", name: "Intro",
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "m1", widget: "map", x: 0, y: 0, w: 4, h: 3, props: {} },
    ] },
    onEnter: [],
  };
}

test("toggles the navigation mode", async () => {
  const onMode = vi.fn();
  render(
    <NavigationPanel navigationMode="tabs" onNavigationModeChange={onMode} page={pageWithMap()} onPageChange={vi.fn()} />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Mode de navigation"), "story");
  expect(onMode).toHaveBeenCalledWith("story");
});

test("adds an onEnter flyTo with a center payload to the active page", async () => {
  const onPageChange = vi.fn();
  render(
    <NavigationPanel navigationMode="story" onNavigationModeChange={vi.fn()} page={pageWithMap()} onPageChange={onPageChange} />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Widget cible"), "m1");
  await userEvent.selectOptions(screen.getByLabelText("Action"), "flyTo");
  await userEvent.type(screen.getByLabelText("Longitude"), "2.35");
  await userEvent.type(screen.getByLabelText("Latitude"), "48.85");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter à ce chapitre" }));

  expect(onPageChange).toHaveBeenCalledTimes(1);
  const updated = onPageChange.mock.calls[0][0] as Page;
  expect(updated.onEnter).toHaveLength(1);
  expect(updated.onEnter![0]).toMatchObject({
    from: "p1", event: "enter", to: "m1", action: "flyTo", payload: { center: [2.35, 48.85] },
  });
});

test("removes an existing onEnter message", async () => {
  const onPageChange = vi.fn();
  const page: Page = {
    ...pageWithMap(),
    onEnter: [{ id: "oe1", from: "p1", event: "enter", to: "m1", action: "flyTo", payload: { center: [1, 2] } }],
  };
  render(
    <NavigationPanel navigationMode="story" onNavigationModeChange={vi.fn()} page={page} onPageChange={onPageChange} />,
  );
  await userEvent.click(screen.getByRole("button", { name: /Retirer l'action oe1/ }));
  const updated = onPageChange.mock.calls[0][0] as Page;
  expect(updated.onEnter).toHaveLength(0);
});

test("shows an inline error for an invalid when condition", async () => {
  const page: Page = {
    ...pageWithMap(),
    onEnter: [{ id: "oe1", from: "p1", event: "enter", to: "m1", action: "flyTo", payload: {}, when: "vars.(" }],
  };
  render(
    <NavigationPanel navigationMode="story" onNavigationModeChange={vi.fn()} page={page} onPageChange={vi.fn()} />,
  );
  expect(screen.getByRole("alert")).toBeInTheDocument();
});

test("rejects adding onEnter when longitude is blank", async () => {
  const onPageChange = vi.fn();
  render(
    <NavigationPanel navigationMode="story" onNavigationModeChange={vi.fn()} page={pageWithMap()} onPageChange={onPageChange} />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Widget cible"), "m1");
  await userEvent.selectOptions(screen.getByLabelText("Action"), "flyTo");
  await userEvent.type(screen.getByLabelText("Latitude"), "48.85");
  // Longitude left blank
  await userEvent.click(screen.getByRole("button", { name: "Ajouter à ce chapitre" }));
  expect(onPageChange).not.toHaveBeenCalled();
});

test("rejects adding onEnter when latitude is blank", async () => {
  const onPageChange = vi.fn();
  render(
    <NavigationPanel navigationMode="story" onNavigationModeChange={vi.fn()} page={pageWithMap()} onPageChange={onPageChange} />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Widget cible"), "m1");
  await userEvent.selectOptions(screen.getByLabelText("Action"), "flyTo");
  await userEvent.type(screen.getByLabelText("Longitude"), "2.35");
  // Latitude left blank
  await userEvent.click(screen.getByRole("button", { name: "Ajouter à ce chapitre" }));
  expect(onPageChange).not.toHaveBeenCalled();
});

test("rejects adding onEnter when both longitude and latitude are blank", async () => {
  const onPageChange = vi.fn();
  render(
    <NavigationPanel navigationMode="story" onNavigationModeChange={vi.fn()} page={pageWithMap()} onPageChange={onPageChange} />,
  );
  await userEvent.selectOptions(screen.getByLabelText("Widget cible"), "m1");
  await userEvent.selectOptions(screen.getByLabelText("Action"), "flyTo");
  // Both left blank
  await userEvent.click(screen.getByRole("button", { name: "Ajouter à ce chapitre" }));
  expect(onPageChange).not.toHaveBeenCalled();
});
