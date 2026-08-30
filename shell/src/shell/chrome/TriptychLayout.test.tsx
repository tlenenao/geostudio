// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { TriptychLayout } from "./TriptychLayout";

vi.mock("./useNarrowViewport", () => ({ useNarrowViewport: vi.fn() }));
import { useNarrowViewport } from "./useNarrowViewport";

const TABS = {
  browse: { id: "browse", label: "Parcourir", content: <p>Contenu Parcourir</p> },
  work: { id: "work", label: "Travailler", content: <p>Contenu Travailler</p> },
  inspect: { id: "inspect", label: "Inspecter", content: <p>Contenu Inspecter</p> },
};

test("large : les trois volets sont visibles en même temps", () => {
  vi.mocked(useNarrowViewport).mockReturnValue(false);
  render(<TriptychLayout {...TABS} />);
  expect(screen.getByText("Contenu Parcourir")).toBeVisible();
  expect(screen.getByText("Contenu Travailler")).toBeVisible();
  expect(screen.getByText("Contenu Inspecter")).toBeVisible();
  expect(screen.queryByRole("tablist")).not.toBeInTheDocument();
});

test("étroit : un seul volet à la fois, par défaut Travailler", () => {
  vi.mocked(useNarrowViewport).mockReturnValue(true);
  render(<TriptychLayout {...TABS} />);
  expect(screen.getByText("Contenu Travailler")).toBeVisible();
  expect(screen.queryByText("Contenu Parcourir")).not.toBeInTheDocument();
});

test("étroit : basculer d'onglet change le volet affiché", async () => {
  vi.mocked(useNarrowViewport).mockReturnValue(true);
  render(<TriptychLayout {...TABS} />);
  await userEvent.click(screen.getByRole("tab", { name: "Parcourir" }));
  expect(screen.getByText("Contenu Parcourir")).toBeVisible();
  expect(screen.queryByText("Contenu Travailler")).not.toBeInTheDocument();
});

test("étroit : respecte defaultTabId quand fourni", () => {
  vi.mocked(useNarrowViewport).mockReturnValue(true);
  render(<TriptychLayout {...TABS} defaultTabId="browse" />);
  expect(screen.getByText("Contenu Parcourir")).toBeVisible();
});
