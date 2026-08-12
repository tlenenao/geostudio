// SPDX-License-Identifier: Apache-2.0
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CollectionSchema } from "../../api/types";
import { QuerySummaryBuilder } from "./QuerySummaryBuilder";

const SCHEMA: CollectionSchema = {
  collection: "incidents", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string", required: true }, { name: "gravite", type: "integer", required: false }],
};

describe("QuerySummaryBuilder", () => {
  test("ajouter une métrique count ne demande pas de colonne source", async () => {
    const onChange = vi.fn();
    render(<QuerySummaryBuilder schema={SCHEMA} value={{ groupBy: [], metrics: [] }} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Ajouter une métrique" }));
    expect(onChange).toHaveBeenCalledWith({
      groupBy: [], metrics: [{ alias: "metrique_1", function: "count", sourceColumn: null }],
    });
  });

  test("changer la fonction en sum exige alors une colonne source (premier champ numérique, pas le premier champ tout court)", async () => {
    const onChange = vi.fn();
    render(
      <QuerySummaryBuilder
        schema={SCHEMA}
        value={{ groupBy: [], metrics: [{ alias: "metrique_1", function: "count", sourceColumn: null }] }}
        onChange={onChange}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Fonction de la métrique 1"), "sum");
    expect(onChange).toHaveBeenCalledWith({
      groupBy: [], metrics: [{ alias: "metrique_1", function: "sum", sourceColumn: "gravite" }],
    });
  });

  test("cocher une colonne de regroupement l'ajoute à groupBy", async () => {
    const onChange = vi.fn();
    render(<QuerySummaryBuilder schema={SCHEMA} value={{ groupBy: [], metrics: [] }} onChange={onChange} />);
    await userEvent.click(screen.getByLabelText("Regrouper par commune"));
    expect(onChange).toHaveBeenCalledWith({ groupBy: ["commune"], metrics: [] });
  });
});
