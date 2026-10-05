// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { TriptychLayout } from "./TriptychLayout";

vi.mock("./useNarrowViewport", () => ({ useViewportMode: vi.fn() }));
import { useViewportMode } from "./useNarrowViewport";

const TABS = {
  browse: { id: "browse", label: "Parcourir", content: <p>Contenu Parcourir</p> },
  work: { id: "work", label: "Travailler", content: <p>Contenu Travailler</p> },
  inspect: { id: "inspect", label: "Inspecter", content: <p>Contenu Inspecter</p> },
};

test("large : les trois volets sont visibles en même temps", () => {
  vi.mocked(useViewportMode).mockReturnValue("wide");
  render(<TriptychLayout {...TABS} />);
  expect(screen.getByText("Contenu Parcourir")).toBeVisible();
  expect(screen.getByText("Contenu Travailler")).toBeVisible();
  expect(screen.getByText("Contenu Inspecter")).toBeVisible();
  expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
});

test("large : la colonne centrale a un plancher CSS explicite, pas un 1fr nu", () => {
  vi.mocked(useViewportMode).mockReturnValue("wide");
  const { container } = render(<TriptychLayout {...TABS} />);
  const grid = container.querySelector(".grid");
  expect(grid).not.toBeNull();
  expect(grid?.className).toContain(
    "grid-cols-[minmax(220px,280px)_minmax(360px,1fr)_minmax(260px,320px)]",
  );
});

test("étroit : un seul volet à la fois, par défaut Travailler", () => {
  vi.mocked(useViewportMode).mockReturnValue("narrow");
  render(<TriptychLayout {...TABS} />);
  expect(screen.getByText("Contenu Travailler")).toBeVisible();
  expect(screen.queryByText("Contenu Parcourir")).not.toBeInTheDocument();
});

test("étroit : basculer d'onglet change le volet affiché", async () => {
  vi.mocked(useViewportMode).mockReturnValue("narrow");
  render(<TriptychLayout {...TABS} />);
  await userEvent.click(screen.getByRole("tab", { name: "Parcourir" }));
  expect(screen.getByText("Contenu Parcourir")).toBeVisible();
  expect(screen.queryByText("Contenu Travailler")).not.toBeInTheDocument();
});

test("étroit : respecte defaultTabId quand fourni", () => {
  vi.mocked(useViewportMode).mockReturnValue("narrow");
  render(<TriptychLayout {...TABS} defaultTabId="browse" />);
  expect(screen.getByText("Contenu Parcourir")).toBeVisible();
});

test("étroit : flèches, Home et End déplacent sélection et focus (WAI-ARIA tablist)", async () => {
  vi.mocked(useViewportMode).mockReturnValue("narrow");
  render(<TriptychLayout {...TABS} />);
  const user = userEvent.setup();
  screen.getByRole("tab", { name: "Travailler" }).focus();
  await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "Inspecter" })).toHaveFocus();
  expect(screen.getByText("Contenu Inspecter")).toBeVisible();
  await user.keyboard("{ArrowRight}");
  expect(screen.getByRole("tab", { name: "Parcourir" })).toHaveFocus();
  await user.keyboard("{ArrowLeft}");
  expect(screen.getByRole("tab", { name: "Inspecter" })).toHaveFocus();
  await user.keyboard("{Home}");
  expect(screen.getByRole("tab", { name: "Parcourir" })).toHaveAttribute("aria-selected", "true");
  await user.keyboard("{End}");
  expect(screen.getByRole("tab", { name: "Inspecter" })).toHaveAttribute("aria-selected", "true");
  await user.keyboard("a");
  expect(screen.getByRole("tab", { name: "Inspecter" })).toHaveAttribute("aria-selected", "true");
});

test("étroit, mode contrôlé : activeTabId gouverne l'onglet et le clic notifie", async () => {
  vi.mocked(useViewportMode).mockReturnValue("narrow");
  const onActiveTabChange = vi.fn();
  render(<TriptychLayout {...TABS} activeTabId="inspect" onActiveTabChange={onActiveTabChange} />);
  expect(screen.getByText("Contenu Inspecter")).toBeVisible();
  await userEvent.click(screen.getByRole("tab", { name: "Parcourir" }));
  expect(onActiveTabChange).toHaveBeenCalledWith("browse");
});

test("medium : travail + volet latéral à onglets (Parcourir/Inspecter), pas la grille 3 colonnes", async () => {
  vi.mocked(useViewportMode).mockReturnValue("medium");
  const { container } = render(<TriptychLayout {...TABS} />);
  expect(screen.getByText("Contenu Travailler")).toBeVisible();
  expect(screen.getByText("Contenu Parcourir")).toBeVisible();
  expect(screen.queryByText("Contenu Inspecter")).not.toBeInTheDocument();
  expect(screen.getAllByRole("tab").map((tab) => tab.textContent)).toEqual([
    "Parcourir",
    "Inspecter",
  ]);
  expect(container.querySelector(".grid")?.className).toContain(
    "grid-cols-[minmax(360px,1fr)_minmax(240px,300px)]",
  );
  await userEvent.click(screen.getByRole("tab", { name: "Inspecter" }));
  expect(screen.getByText("Contenu Inspecter")).toBeVisible();
  expect(screen.queryByText("Contenu Parcourir")).not.toBeInTheDocument();
});

test("medium, mode contrôlé : activeTabId = inspect ouvre le volet latéral sur Inspecter", () => {
  vi.mocked(useViewportMode).mockReturnValue("medium");
  render(<TriptychLayout {...TABS} activeTabId="inspect" />);
  expect(screen.getByText("Contenu Inspecter")).toBeVisible();
});

test("medium : le volet latéral suit le patron WAI-ARIA (flèches, Home, End, tabindex itinérant)", async () => {
  vi.mocked(useViewportMode).mockReturnValue("medium");
  render(<TriptychLayout {...TABS} />);
  const browseTab = screen.getByRole("tab", { name: "Parcourir" });
  const inspectTab = screen.getByRole("tab", { name: "Inspecter" });
  browseTab.focus();
  expect(browseTab).toHaveAttribute("tabindex", "0");
  expect(inspectTab).toHaveAttribute("tabindex", "-1");
  await userEvent.keyboard("{ArrowRight}");
  expect(inspectTab).toHaveAttribute("aria-selected", "true");
  expect(inspectTab).toHaveFocus();
  await userEvent.keyboard("{ArrowRight}");
  expect(browseTab).toHaveAttribute("aria-selected", "true");
  await userEvent.keyboard("{End}");
  expect(inspectTab).toHaveFocus();
  await userEvent.keyboard("{Home}");
  expect(browseTab).toHaveFocus();
  await userEvent.keyboard("{ArrowLeft}");
  expect(inspectTab).toHaveAttribute("aria-selected", "true");
});
