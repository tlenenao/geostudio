// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { DataTable } from "./DataTable";
import { expectTokenizedClasses } from "./testUtils";

type Row = { id: string; name: string; kind: string };

const ROWS: Row[] = [
  { id: "1", name: "Carte topo", kind: "map" },
  { id: "2", name: "App suivi", kind: "app" },
];

const COLUMNS = [
  { key: "name", label: "Nom", render: (r: Row) => r.name },
  { key: "kind", label: "Type", render: (r: Row) => r.kind },
];

test("clic sur un en-tête de colonne triable notifie onSortChange", async () => {
  const onSortChange = vi.fn();
  const { container } = render(
    <DataTable columns={COLUMNS} rows={ROWS} getRowId={(r) => r.id} onSortChange={onSortChange} />,
  );
  await userEvent.click(screen.getByRole("columnheader", { name: "Nom" }));
  expect(onSortChange).toHaveBeenCalledWith("name");
  expectTokenizedClasses(container);
});

test("aria-sort reflète sortDirection (REV-090)", () => {
  render(
    <DataTable
      columns={COLUMNS}
      rows={ROWS}
      getRowId={(r) => r.id}
      sortKey="name"
      sortDirection="desc"
    />,
  );
  expect(screen.getByRole("columnheader", { name: "Nom" })).toHaveAttribute(
    "aria-sort",
    "descending",
  );
  expect(screen.getByRole("columnheader", { name: "Type" })).toHaveAttribute("aria-sort", "none");
});

test("cocher une ligne ajoute son id à selectedIds", async () => {
  const onSelectedIdsChange = vi.fn();
  render(
    <DataTable
      columns={COLUMNS}
      rows={ROWS}
      getRowId={(r) => r.id}
      selectedIds={new Set()}
      onSelectedIdsChange={onSelectedIdsChange}
    />,
  );
  await userEvent.click(screen.getByRole("checkbox", { name: "Sélectionner Carte topo" }));
  expect(onSelectedIdsChange).toHaveBeenCalledWith(new Set(["1"]));
});

test("colonne 0 rendant un ReactNode : aria-label générique, pas '[object Object]'", async () => {
  const onSelectedIdsChange = vi.fn();
  const columnsWithNode = [
    { key: "name", label: "Nom", render: (r: Row) => <strong>{r.name}</strong> },
    { key: "kind", label: "Type", render: (r: Row) => r.kind },
  ];
  render(
    <DataTable
      columns={columnsWithNode}
      rows={ROWS}
      getRowId={(r) => r.id}
      selectedIds={new Set()}
      onSelectedIdsChange={onSelectedIdsChange}
    />,
  );
  // ROWS contient 2 lignes ; les deux rendent un ReactNode non-string en
  // colonne 0, donc les deux reçoivent le même aria-label générique — on
  // cible la première occurrence plutôt qu'un nom unique.
  const [checkbox] = screen.getAllByRole("checkbox", { name: "Sélectionner la ligne" });
  await userEvent.click(checkbox);
  expect(onSelectedIdsChange).toHaveBeenCalledWith(new Set(["1"]));
});

test("trie au clavier (Entrée) sur un en-tête de colonne triable", async () => {
  const onSortChange = vi.fn();
  render(
    <DataTable
      columns={COLUMNS}
      rows={ROWS}
      getRowId={(r) => r.id}
      sortKey="name"
      sortDirection="asc"
      onSortChange={onSortChange}
    />,
  );
  const header = screen.getByRole("columnheader", { name: /Nom/i });
  header.focus();
  await userEvent.keyboard("{Enter}");
  expect(onSortChange).toHaveBeenCalledWith("name");
});

test("appelle onRowClick au clic sur une ligne", async () => {
  const onRowClick = vi.fn();
  render(
    <DataTable columns={COLUMNS} rows={ROWS} getRowId={(r) => r.id} onRowClick={onRowClick} />,
  );
  await userEvent.click(screen.getAllByRole("row")[1]);
  expect(onRowClick).toHaveBeenCalledWith(ROWS[0]);
});

test("appelle onRowClick sur Entrée quand une ligne est focus (pipeline builder, Tâche 23)", () => {
  const onRowClick = vi.fn();
  render(
    <DataTable columns={COLUMNS} rows={ROWS} getRowId={(r) => r.id} onRowClick={onRowClick} />,
  );
  const row = screen.getAllByRole("row")[1];
  row.focus();
  fireEvent.keyDown(row, { key: "Enter" });
  expect(onRowClick).toHaveBeenCalledWith(ROWS[0]);
});

test("un Espace sur un bouton imbriqué n'est pas intercepté par la ligne (pipeline builder, Tâche 23)", async () => {
  const onRowClick = vi.fn();
  const onButtonClick = vi.fn();
  const columnsWithButton = [
    {
      key: "name",
      label: "Nom",
      render: (r: Row) => (
        <button
          type="button"
          onClick={(e) => {
            e.stopPropagation();
            onButtonClick(r);
          }}
        >
          {r.name}
        </button>
      ),
    },
    { key: "kind", label: "Type", render: (r: Row) => r.kind },
  ];
  render(
    <DataTable
      columns={columnsWithButton}
      rows={ROWS}
      getRowId={(r) => r.id}
      onRowClick={onRowClick}
    />,
  );
  const user = userEvent.setup();
  const button = screen.getByRole("button", { name: "Carte topo" });
  button.focus();
  await user.keyboard(" ");
  expect(onButtonClick).toHaveBeenCalledWith(ROWS[0]);
  expect(onRowClick).not.toHaveBeenCalled();
});

test("getRowClassName ajoute la classe fournie sur la ligne concernée (pipeline builder, Tâche 23)", () => {
  render(
    <DataTable
      columns={COLUMNS}
      rows={ROWS}
      getRowId={(r) => r.id}
      getRowClassName={(r) => (r.id === "2" ? "bg-sunken" : undefined)}
    />,
  );
  const rows = screen.getAllByRole("row");
  expect(rows[1]).not.toHaveClass("bg-sunken");
  expect(rows[2]).toHaveClass("bg-sunken");
});
