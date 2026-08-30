// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { Table } from "./Table";
import { expectTokenizedClasses } from "./testUtils";

test("rend un tableau accessible avec en-têtes de colonne", () => {
  const { container } = render(
    <Table>
      <Table.Head columns={["Nom", "Type"]} />
      <tbody>
        <Table.Row>
          <Table.Cell>Carte topo</Table.Cell>
          <Table.Cell>map</Table.Cell>
        </Table.Row>
      </tbody>
    </Table>,
  );
  expect(screen.getByRole("table")).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "Nom" })).toBeInTheDocument();
  expect(screen.getByText("Carte topo")).toBeInTheDocument();
  expectTokenizedClasses(container);
});
