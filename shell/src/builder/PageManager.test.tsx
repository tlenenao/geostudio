// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { Page } from "../api/types";
import { PageManager } from "./PageManager";

const emptyLayout = { type: "grid" as const, breakpoints: {}, items: [] };

test("adds a page and selects it", async () => {
  const onChange = vi.fn();
  const onSelectPage = vi.fn();
  const pages: Page[] = [{ id: "p1", name: "Page 1", layout: emptyLayout }];
  render(
    <PageManager pages={pages} activePageId="p1" onChange={onChange} onSelectPage={onSelectPage} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une page" }));
  const next = onChange.mock.calls[0][0] as Page[];
  expect(next).toHaveLength(2);
  expect(onSelectPage).toHaveBeenCalledWith(next[1].id);
});

test("removes a page and falls back to the first remaining page if it was active", async () => {
  const onChange = vi.fn();
  const onSelectPage = vi.fn();
  const pages: Page[] = [
    { id: "p1", name: "Accueil", layout: emptyLayout },
    { id: "p2", name: "Détails", layout: emptyLayout },
  ];
  render(
    <PageManager pages={pages} activePageId="p2" onChange={onChange} onSelectPage={onSelectPage} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Retirer la page p2" }));
  expect(onChange).toHaveBeenCalledWith([pages[0]]);
  expect(onSelectPage).toHaveBeenCalledWith("p1");
});

test("cannot remove the last remaining page", () => {
  const pages: Page[] = [{ id: "p1", name: "Accueil", layout: emptyLayout }];
  render(<PageManager pages={pages} activePageId="p1" onChange={vi.fn()} onSelectPage={vi.fn()} />);
  expect(screen.getByRole("button", { name: "Retirer la page p1" })).toBeDisabled();
});

test("renames a page", async () => {
  const onChange = vi.fn();
  const pages: Page[] = [{ id: "p1", name: "", layout: emptyLayout }];
  render(
    <PageManager pages={pages} activePageId="p1" onChange={onChange} onSelectPage={vi.fn()} />,
  );
  await userEvent.type(screen.getByLabelText("Renommer la page p1"), "A");
  const next = onChange.mock.calls.at(-1)![0] as Page[];
  expect(next[0].name).toBe("A");
});

test("reorders pages with the move buttons", async () => {
  const onChange = vi.fn();
  const pages: Page[] = [
    { id: "p1", name: "A", layout: emptyLayout },
    { id: "p2", name: "B", layout: emptyLayout },
  ];
  render(
    <PageManager pages={pages} activePageId="p1" onChange={onChange} onSelectPage={vi.fn()} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Descendre la page p1" }));
  const next = onChange.mock.calls[0][0] as Page[];
  expect(next.map((p) => p.id)).toEqual(["p2", "p1"]);
});

test("selecting a page calls onSelectPage", async () => {
  const onSelectPage = vi.fn();
  const pages: Page[] = [{ id: "p1", name: "Accueil", layout: emptyLayout }];
  render(
    <PageManager pages={pages} activePageId="p1" onChange={vi.fn()} onSelectPage={onSelectPage} />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Ouvrir la page p1" }));
  expect(onSelectPage).toHaveBeenCalledWith("p1");
});
