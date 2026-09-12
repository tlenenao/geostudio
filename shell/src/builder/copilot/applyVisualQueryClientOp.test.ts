// SPDX-License-Identifier: Apache-2.0
import { describe, expect, it, vi } from "vitest";
import type { CollectionSchema } from "../../api/types";
import { applyVisualQueryClientOp } from "./applyVisualQueryClientOp";

function setters() {
  return { setFilters: vi.fn(), setJoin: vi.fn(), setSummary: vi.fn() };
}

function schema(names: string[]): CollectionSchema {
  return {
    collection: "c",
    pk: "id",
    geometry: null,
    fields: names.map((name) => ({ name, type: "string" as const, required: false })),
  };
}

// Contexte réel du wizard (I2/I3, revue finale de branche GAP-17) : les
// colonnes connues et les collections visibles servent à rejeter une
// colonne/collection hallucinée AVANT qu'elle n'atteigne le formulaire.
const KNOWN = {
  baseSchema: schema(["titre", "population"]),
  joinedSchema: null,
  collectionIds: ["communes"],
};

describe("applyVisualQueryClientOp", () => {
  it("applies a valid filters array", () => {
    const s = setters();
    applyVisualQueryClientOp(
      {
        op: "applyVisualQueryDraft",
        args: { filters: [{ column: "titre", operator: "eq", value: "x" }] },
      },
      s,
      KNOWN,
    );
    expect(s.setFilters).toHaveBeenCalledWith([{ column: "titre", operator: "eq", value: "x" }]);
    expect(s.setJoin).not.toHaveBeenCalled();
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  // I4 (revue finale de branche GAP-17) : cette assertion disait auparavant
  // `toHaveBeenCalledWith([])`. C'était exactement le comportement
  // destructeur que I4 demande de supprimer — l'unique ligne générée étant
  // invalide, le résultat filtré est vide et écrasait silencieusement les
  // filtres déjà construits à la main par l'utilisateur, sans undo (le
  // wizard n'est pas branché sur la pile SP-19). Le nouveau contrat : une
  // proposition entièrement invalide est un no-op.
  it("does not touch existing filters when every generated row is invalid", () => {
    const s = setters();
    applyVisualQueryClientOp(
      {
        op: "applyVisualQueryDraft",
        args: { filters: [{ column: "titre", operator: "startswith", value: "x" }] },
      },
      s,
      KNOWN,
    );
    expect(s.setFilters).not.toHaveBeenCalled();
  });

  it("drops only the invalid rows when at least one row survives", () => {
    const s = setters();
    applyVisualQueryClientOp(
      {
        op: "applyVisualQueryDraft",
        args: {
          filters: [
            { column: "titre", operator: "startswith", value: "x" },
            { column: "titre", operator: "eq", value: "y" },
          ],
        },
      },
      s,
      KNOWN,
    );
    expect(s.setFilters).toHaveBeenCalledWith([{ column: "titre", operator: "eq", value: "y" }]);
  });

  it("applies an explicitly empty filters array (the model asked to clear them)", () => {
    const s = setters();
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { filters: [] } }, s, KNOWN);
    expect(s.setFilters).toHaveBeenCalledWith([]);
  });

  // I2 : la validation de colonnes du tool MCP côté serveur n'est jamais
  // rejouée ici — c'est le LLM, pas le JSON validé, qui compose l'appel
  // applyVisualQueryDraft. Sans ce contrôle, un pipeline réel se crée en
  // référençant une colonne inexistante et n'échoue qu'à l'exécution.
  it("drops a filter row whose column is not in the known schema", () => {
    const s = setters();
    applyVisualQueryClientOp(
      {
        op: "applyVisualQueryDraft",
        args: {
          filters: [
            { column: "colonne_hallucinee", operator: "eq", value: "x" },
            { column: "titre", operator: "eq", value: "y" },
          ],
        },
      },
      s,
      KNOWN,
    );
    expect(s.setFilters).toHaveBeenCalledWith([{ column: "titre", operator: "eq", value: "y" }]);
  });

  it("accepts a filter on a joined column, aliased like the server does", () => {
    const s = setters();
    applyVisualQueryClientOp(
      {
        op: "applyVisualQueryDraft",
        args: { filters: [{ column: "joined_titre", operator: "eq", value: "x" }] },
      },
      s,
      { ...KNOWN, joinedSchema: schema(["titre", "code_insee"]) },
    );
    expect(s.setFilters).toHaveBeenCalledWith([
      { column: "joined_titre", operator: "eq", value: "x" },
    ]);
  });

  it("applies join:null", () => {
    const s = setters();
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { join: null } }, s, KNOWN);
    expect(s.setJoin).toHaveBeenCalledWith(null);
  });

  it("applies a valid join object on a known collection", () => {
    const s = setters();
    const join = { collectionId: "communes", on: "code_insee", how: "inner" as const };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { join } }, s, KNOWN);
    expect(s.setJoin).toHaveBeenCalledWith(join);
  });

  // I3 : `joinValid` (VisualQueryWizardPage) n'exige que des chaînes non
  // vides, et compilePipeline n'émet le SQL de jointure que sous
  // `if (state.join && joinedSchema)` — une collection hallucinée donnait
  // donc un formulaire qui AFFICHE une jointure et un pipeline réel qui ne
  // la porte pas. Silencieux de bout en bout.
  it("ignores a join whose collectionId is not a visible collection", () => {
    const s = setters();
    applyVisualQueryClientOp(
      {
        op: "applyVisualQueryDraft",
        args: { join: { collectionId: "collection_inventee", on: "code_insee", how: "inner" } },
      },
      s,
      KNOWN,
    );
    expect(s.setJoin).not.toHaveBeenCalled();
  });

  it("ignores an invalid join object (missing fields)", () => {
    const s = setters();
    applyVisualQueryClientOp(
      { op: "applyVisualQueryDraft", args: { join: { collectionId: "communes" } } },
      s,
      KNOWN,
    );
    expect(s.setJoin).not.toHaveBeenCalled();
  });

  it("applies a valid summary object", () => {
    const s = setters();
    const summary = {
      groupBy: ["titre"],
      metrics: [{ alias: "total", function: "count" as const, sourceColumn: null, p: null }],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s, KNOWN);
    expect(s.setSummary).toHaveBeenCalledWith(summary);
  });

  // I2, volet résumé : groupBy et sourceColumn sont eux aussi des noms de
  // colonnes composés par le LLM.
  it("ignores a summary whose groupBy names an unknown column", () => {
    const s = setters();
    const summary = {
      groupBy: ["colonne_hallucinee"],
      metrics: [{ alias: "total", function: "count" as const, sourceColumn: null, p: null }],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s, KNOWN);
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("ignores a summary whose metric sourceColumn is an unknown column", () => {
    const s = setters();
    const summary = {
      groupBy: ["titre"],
      metrics: [
        { alias: "somme", function: "sum" as const, sourceColumn: "colonne_hallucinee", p: null },
      ],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s, KNOWN);
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("ignores a summary whose metric requires sourceColumn but omits it", () => {
    const s = setters();
    const summary = {
      groupBy: ["titre"],
      // "sum" requires a non-null sourceColumn (metricExpr quoteIdent's it) —
      // this metric is schema-conformant (alias/function both valid) but
      // omits the field entirely.
      metrics: [{ alias: "total_pop", function: "sum" as const }],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s, KNOWN);
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("ignores a summary whose metric has sourceColumn: null for a function that needs one", () => {
    const s = setters();
    const summary = {
      groupBy: [],
      metrics: [{ alias: "avg_pop", function: "avg" as const, sourceColumn: null, p: null }],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s, KNOWN);
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("ignores a summary whose percentile metric is missing p", () => {
    const s = setters();
    const summary = {
      groupBy: [],
      metrics: [{ alias: "p90", function: "percentile" as const, sourceColumn: "population" }],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s, KNOWN);
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("ignores a summary whose percentile metric has a non-numeric p", () => {
    const s = setters();
    const summary = {
      groupBy: [],
      metrics: [
        { alias: "p90", function: "percentile" as const, sourceColumn: "population", p: "90" },
      ],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s, KNOWN);
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("ignores a summary whose percentile metric has p out of the (0, 100) range", () => {
    const s = setters();
    const summary = {
      groupBy: [],
      metrics: [
        { alias: "p90", function: "percentile" as const, sourceColumn: "population", p: 150 },
      ],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s, KNOWN);
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  it("applies a valid summary with a count metric and sourceColumn: null", () => {
    // "count" compiles to count(*) (compilePipeline.ts::metricExpr) and never
    // reads sourceColumn — the round-trip contract with decompileMetrics is
    // that count's sourceColumn is always exactly null.
    const s = setters();
    const summary = {
      groupBy: ["titre"],
      metrics: [{ alias: "n", function: "count" as const, sourceColumn: null, p: null }],
    };
    applyVisualQueryClientOp({ op: "applyVisualQueryDraft", args: { summary } }, s, KNOWN);
    expect(s.setSummary).toHaveBeenCalledWith(summary);
  });

  it("ignores an unknown op", () => {
    const s = setters();
    applyVisualQueryClientOp({ op: "somethingElse", args: {} }, s, KNOWN);
    expect(s.setFilters).not.toHaveBeenCalled();
    expect(s.setJoin).not.toHaveBeenCalled();
    expect(s.setSummary).not.toHaveBeenCalled();
  });

  // M1 (revue finale de branche GAP-17) : CopilotChat affichait « Requête
  // visuelle mise à jour. » même quand tout avait été rejeté. Le retour dit
  // si quelque chose a réellement été appliqué.
  it("reports whether anything was actually applied", () => {
    expect(
      applyVisualQueryClientOp(
        {
          op: "applyVisualQueryDraft",
          args: { filters: [{ column: "titre", operator: "eq", value: "x" }] },
        },
        setters(),
        KNOWN,
      ),
    ).toBe(true);
    expect(
      applyVisualQueryClientOp(
        {
          op: "applyVisualQueryDraft",
          args: { filters: [{ column: "titre", operator: "startswith", value: "x" }] },
        },
        setters(),
        KNOWN,
      ),
    ).toBe(false);
    expect(applyVisualQueryClientOp({ op: "somethingElse", args: {} }, setters(), KNOWN)).toBe(
      false,
    );
  });
});
