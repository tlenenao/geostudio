// SPDX-License-Identifier: Apache-2.0
import { describe, expect, test, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CollectionSchema } from "../../api/types";
import { QuerySummaryBuilder } from "./QuerySummaryBuilder";

const SCHEMA: CollectionSchema = {
  collection: "incidents",
  pk: "id",
  geometry: null,
  fields: [
    { name: "commune", type: "string", required: true },
    { name: "gravite", type: "integer", required: false },
  ],
};

describe("QuerySummaryBuilder", () => {
  test("ajouter une métrique count ne demande pas de colonne source", async () => {
    const onChange = vi.fn();
    render(
      <QuerySummaryBuilder
        schema={SCHEMA}
        value={{ groupBy: [], metrics: [] }}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Ajouter une métrique" }));
    expect(onChange).toHaveBeenCalledWith({
      groupBy: [],
      metrics: [{ alias: "metrique_1", function: "count", sourceColumn: null, p: null }],
    });
  });

  test("changer la fonction en sum exige alors une colonne source (premier champ numérique, pas le premier champ tout court)", async () => {
    const onChange = vi.fn();
    render(
      <QuerySummaryBuilder
        schema={SCHEMA}
        value={{
          groupBy: [],
          metrics: [{ alias: "metrique_1", function: "count", sourceColumn: null, p: null }],
        }}
        onChange={onChange}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Fonction de la métrique 1"), "sum");
    expect(onChange).toHaveBeenCalledWith({
      groupBy: [],
      metrics: [{ alias: "metrique_1", function: "sum", sourceColumn: "gravite", p: null }],
    });
  });

  test("cocher une colonne de regroupement l'ajoute à groupBy", async () => {
    const onChange = vi.fn();
    render(
      <QuerySummaryBuilder
        schema={SCHEMA}
        value={{ groupBy: [], metrics: [] }}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByLabelText("Regrouper par commune"));
    expect(onChange).toHaveBeenCalledWith({ groupBy: ["commune"], metrics: [] });
  });

  test("propose les neuf fonctions et un champ centile pour percentile", async () => {
    const onChange = vi.fn();
    render(
      <QuerySummaryBuilder
        schema={SCHEMA}
        value={{
          groupBy: [],
          metrics: [{ alias: "m1", function: "count", sourceColumn: null, p: null }],
        }}
        onChange={onChange}
      />,
    );

    const select = screen.getByLabelText("Fonction de la métrique 1");
    expect(Array.from(select.querySelectorAll("option")).map((o) => o.value)).toEqual([
      "count",
      "countDistinct",
      "sum",
      "avg",
      "median",
      "percentile",
      "stddev",
      "min",
      "max",
    ]);
    expect(screen.queryByLabelText("Centile de la métrique 1")).toBeNull();

    await userEvent.selectOptions(select, "percentile");
    expect(onChange).toHaveBeenCalledWith({
      groupBy: [],
      metrics: [{ alias: "m1", function: "percentile", sourceColumn: expect.any(String), p: 50 }],
    });
  });

  test("vider le champ centile ou taper une valeur hors bornes ne remonte jamais un p invalide", async () => {
    const onChange = vi.fn();
    render(
      <QuerySummaryBuilder
        schema={SCHEMA}
        value={{
          groupBy: [],
          metrics: [{ alias: "m1", function: "percentile", sourceColumn: "gravite", p: 50 }],
        }}
        onChange={onChange}
      />,
    );

    const input = screen.getByLabelText("Centile de la métrique 1") as HTMLInputElement;
    expect(input.value).toBe("50");

    // fireEvent.change plutôt que clear()+type() : onChange est un espion sans
    // rerender ici, donc React restaurerait la valeur DOM contrôlée après
    // chaque frappe individuelle (même piège que DataSourcePanel.test.tsx,
    // qui utilise déjà fireEvent.change pour la même raison). Number("") vaut
    // 0, pas null : sans la garde locale, ce serait exactement l'entrée
    // silencieuse en `quantile_cont(col, 0)` décrite par la revue.
    fireEvent.change(input, { target: { value: "" } });
    expect(onChange).not.toHaveBeenCalled();
    // Le champ affiche bien le vide tapé — pas de retour forcé au défaut
    // pendant la frappe, sinon l'auteur ne pourrait plus retaper de valeur.
    expect(input.value).toBe("");

    // Les attributs HTML min={1}/max={99} sont cosmétiques : rien ne bloque
    // onChange. La garde applicative doit donc rejeter elle-même 150 et -5.
    fireEvent.change(input, { target: { value: "150" } });
    expect(onChange).not.toHaveBeenCalled();
    fireEvent.change(input, { target: { value: "-5" } });
    expect(onChange).not.toHaveBeenCalled();

    // Un auteur qui laisse le champ vide et clique ailleurs (blur) sans avoir
    // retapé de valeur valide ne doit ni déclencher onChange, ni laisser le
    // champ affiché dans un état invalide : il retombe sur la dernière
    // valeur validée (ici toujours 50, jamais committée invalide).
    fireEvent.blur(input);
    expect(onChange).not.toHaveBeenCalled();
    expect(input.value).toBe("50");
  });

  test("vider le champ centile puis retaper une valeur aboutit exactement à cette valeur, sans effet de bord au défaut", () => {
    const onChange = vi.fn();
    render(
      <QuerySummaryBuilder
        schema={SCHEMA}
        value={{
          groupBy: [],
          metrics: [{ alias: "m1", function: "percentile", sourceColumn: "gravite", p: 50 }],
        }}
        onChange={onChange}
      />,
    );

    const input = screen.getByLabelText("Centile de la métrique 1") as HTMLInputElement;

    fireEvent.change(input, { target: { value: "" } });
    // Frappe caractère par caractère de "90", comme le ferait un vrai clavier.
    fireEvent.change(input, { target: { value: "9" } });
    fireEvent.change(input, { target: { value: "90" } });

    // Aucun des deux appels (9 puis 90) ne doit jamais avoir snappé sur le
    // défaut 50 : le dernier appel reflète exactement la dernière frappe.
    expect(onChange).toHaveBeenLastCalledWith({
      groupBy: [],
      metrics: [{ alias: "m1", function: "percentile", sourceColumn: "gravite", p: 90 }],
    });
    expect(input.value).toBe("90");
  });

  test("un p NaN dans la config retombe sur le centile par défaut à l'affichage (?? ne suffit pas pour NaN)", () => {
    const onChange = vi.fn();
    render(
      <QuerySummaryBuilder
        schema={SCHEMA}
        value={{
          groupBy: [],
          metrics: [{ alias: "m1", function: "percentile", sourceColumn: "gravite", p: NaN }],
        }}
        onChange={onChange}
      />,
    );

    expect((screen.getByLabelText("Centile de la métrique 1") as HTMLInputElement).value).toBe(
      "50",
    );
  });
});
