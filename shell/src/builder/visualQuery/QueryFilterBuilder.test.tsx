// SPDX-License-Identifier: Apache-2.0
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CollectionSchema } from "../../api/types";
import { QueryFilterBuilder } from "./QueryFilterBuilder";

const SCHEMA: CollectionSchema = {
  collection: "incidents",
  pk: "id",
  geometry: null,
  fields: [
    { name: "commune", type: "string", required: true },
    { name: "gravite", type: "integer", required: false },
  ],
};

describe("QueryFilterBuilder", () => {
  test("ajoute une ligne de filtre et notifie le parent", async () => {
    const onChange = vi.fn();
    render(<QueryFilterBuilder schema={SCHEMA} rows={[]} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Ajouter un filtre" }));
    expect(onChange).toHaveBeenCalledWith([{ column: "commune", operator: "eq", value: "" }]);
  });

  test("modifier la colonne d'une ligne existante notifie le parent avec la ligne mise à jour", async () => {
    const onChange = vi.fn();
    render(
      <QueryFilterBuilder
        schema={SCHEMA}
        rows={[{ column: "commune", operator: "eq", value: "" }]}
        onChange={onChange}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Colonne du filtre 1"), "gravite");
    expect(onChange).toHaveBeenCalledWith([{ column: "gravite", operator: "eq", value: "" }]);
  });

  test("supprime une ligne", async () => {
    const onChange = vi.fn();
    render(
      <QueryFilterBuilder
        schema={SCHEMA}
        rows={[{ column: "commune", operator: "eq", value: "" }]}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Supprimer le filtre 1" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
