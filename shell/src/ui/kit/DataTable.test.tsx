// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
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
