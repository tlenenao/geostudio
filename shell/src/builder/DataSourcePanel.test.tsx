// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { DataSource } from "../api/types";
import { DataSourcePanel } from "./DataSourcePanel";

test("adds a data source", async () => {
  const onChange = vi.fn();
  render(<DataSourcePanel sources={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une source" }));
  const next = onChange.mock.calls[0][0] as DataSource[];
  expect(next).toHaveLength(1);
  expect(next[0].type).toBe("features");
  expect(typeof next[0].id).toBe("string");
});

test("removes a data source", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "features", service: "featureserv", layer: "parcs", query: {} },
  ];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Retirer parcs" }));
  expect(onChange).toHaveBeenCalledWith([]);
});

test("edits a source layer", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "features", service: "featureserv", layer: "", query: {} },
  ];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Collection de la source d1"), "parcs");
  const last = onChange.mock.calls.at(-1)![0] as DataSource[];
  expect(last[0].layer.endsWith("s")).toBe(true);
});

test("offers a statistics type option", () => {
  const sources: DataSource[] = [
    { id: "d1", type: "features", service: "featureserv", layer: "", query: {} },
  ];
  render(<DataSourcePanel sources={sources} onChange={vi.fn()} />);
  const typeSelect = screen.getByLabelText("Type de la source d1");
  expect(within(typeSelect).getByRole("option", { name: "Statistiques" })).toBeInTheDocument();
});

test("edits a statistics source's group-by and split", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "statistics", service: "featureserv", layer: "villes", query: {} },
  ];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  // onChange is a spy, so the controlled inputs stay frozen at "" — each
  // keystroke emits the single typed char (as with "edits a source layer").
  await userEvent.type(screen.getByLabelText("Grouper par (source d1)"), "r");
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.groupBy).toBe("r");
  await userEvent.type(screen.getByLabelText("Séparer par (source d1)"), "a");
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.split).toBe("a");
});

test("adds and configures a measure on a statistics source", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "statistics", service: "featureserv", layer: "villes", query: {} },
  ];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une mesure à d1" }));
  const afterAdd = (onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.measures as unknown[];
  expect(afterAdd).toHaveLength(1);
});

test("edits the default aggregation of a statistics source", async () => {
  const sources: DataSource[] = [
    {
      id: "d1",
      type: "statistics",
      service: "featureserv",
      layer: "villes",
      query: { groupBy: "region" },
    },
  ];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Agrégation (source d1)"), "sum");
  const last = (onChange.mock.calls.at(-1)![0] as DataSource[])[0];
  expect(last.query.agg).toBe("sum");
  expect(last.query.groupBy).toBe("region");
});

test("promoting a features source calls onPromote and then shows it as shared", async () => {
  const onChange = vi.fn();
  const onPromote = vi.fn();
  const sources: DataSource[] = [
    { id: "s1", type: "features", service: "core", layer: "parcs", query: {} },
  ];
  const { rerender } = render(
    <DataSourcePanel
      sources={sources}
      onChange={onChange}
      onPromote={onPromote}
      promotingId={null}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Promouvoir en dataset partagé s1" }));
  expect(onPromote).toHaveBeenCalledWith("s1");

  rerender(
    <DataSourcePanel
      sources={[{ ...sources[0], datasetId: "ds-1" }]}
      onChange={onChange}
      onPromote={onPromote}
      promotingId={null}
    />,
  );
  expect(screen.getByText("Dataset partagé actif")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Promouvoir en dataset partagé s1" }),
  ).not.toBeInTheDocument();
});

test("a comma-separated group-by becomes a string array; a single field stays a string", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "statistics", service: "featureserv", layer: "villes", query: {} },
  ];
  const onChange = vi.fn();
  const { rerender } = render(<DataSourcePanel sources={sources} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Grouper par (source d1)"), {
    target: { value: "origin,destination" },
  });
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.groupBy).toEqual([
    "origin",
    "destination",
  ]);

  const withArray: DataSource[] = [
    { ...sources[0], query: { groupBy: ["origin", "destination"] } },
  ];
  rerender(<DataSourcePanel sources={withArray} onChange={onChange} />);
  expect(screen.getByLabelText("Grouper par (source d1)")).toHaveValue("origin,destination");
});

test("edits the histogram bin count on a statistics source", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "statistics", service: "featureserv", layer: "villes", query: {} },
  ];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Nombre de classes (source d1)"), "8");
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.bins).toBe(8);
});

const STATS_SOURCE: DataSource = {
  id: "s1",
  type: "statistics",
  service: "core",
  layer: "villes",
  query: { groupBy: "region", agg: "count" },
};

test("propose les neuf agrégats analytiques", () => {
  render(<DataSourcePanel sources={[STATS_SOURCE]} onChange={() => {}} />);

  const select = screen.getByLabelText("Agrégation (source s1)");
  const values = Array.from(select.querySelectorAll("option")).map((o) => o.value);
  expect(values).toEqual([
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
});

test("le champ centile n'apparaît que pour percentile et se patche avec un centile par défaut de 50", async () => {
  const onChange = vi.fn();
  render(<DataSourcePanel sources={[STATS_SOURCE]} onChange={onChange} />);

  expect(screen.queryByLabelText("Centile (source s1)")).toBeNull();

  await userEvent.selectOptions(screen.getByLabelText("Agrégation (source s1)"), "percentile");
  expect(onChange).toHaveBeenCalledWith([
    { ...STATS_SOURCE, query: { groupBy: "region", agg: "percentile", p: 50 } },
  ]);
});

test("affiche le champ centile quand la source est déjà en percentile", async () => {
  const onChange = vi.fn();
  const source: DataSource = {
    ...STATS_SOURCE,
    query: { groupBy: "region", agg: "percentile", p: 90 },
  };
  render(<DataSourcePanel sources={[source]} onChange={onChange} />);

  const p = screen.getByLabelText("Centile (source s1)");
  expect((p as HTMLInputElement).value).toBe("90");

  // fireEvent.change plutôt que clear()+type() : onChange est un espion sans
  // rerender ici, donc React restaure la valeur DOM contrôlée ("90") après
  // chaque frappe individuelle — clear()+type("95") produirait un dernier
  // événement à "905" (même piège que le champ "Grouper par" plus haut dans
  // ce fichier, qui utilise déjà fireEvent.change pour la même raison).
  fireEvent.change(p, { target: { value: "95" } });
  expect(onChange).toHaveBeenLastCalledWith([
    { ...source, query: { groupBy: "region", agg: "percentile", p: 95 } },
  ]);
});

test("repasser d'un agrégat percentile à un autre efface le centile p", async () => {
  const onChange = vi.fn();
  const source: DataSource = {
    ...STATS_SOURCE,
    query: { groupBy: "region", agg: "percentile", p: 90 },
  };
  render(<DataSourcePanel sources={[source]} onChange={onChange} />);

  await userEvent.selectOptions(screen.getByLabelText("Agrégation (source s1)"), "avg");
  expect(onChange).toHaveBeenCalledWith([
    { ...source, query: { groupBy: "region", agg: "avg", p: undefined } },
  ]);
});

test("propose les six grains temporels, plus l'absence de grain", async () => {
  const onChange = vi.fn();
  render(<DataSourcePanel sources={[STATS_SOURCE]} onChange={onChange} />);

  const select = screen.getByLabelText("Grain temporel (source s1)");
  const values = Array.from(select.querySelectorAll("option")).map((o) => o.value);
  expect(values).toEqual(["", "hour", "day", "week", "month", "quarter", "year"]);

  await userEvent.selectOptions(select, "year");
  expect(onChange).toHaveBeenCalledWith([
    { ...STATS_SOURCE, query: { groupBy: "region", agg: "count", bucket: "year" } },
  ]);
});

test("le grain temporel est désactivé sans groupBy à un seul champ", () => {
  const multi: DataSource = {
    ...STATS_SOURCE,
    query: { groupBy: ["region", "annee"], agg: "count" },
  };
  render(<DataSourcePanel sources={[multi]} onChange={() => {}} />);

  expect(screen.getByLabelText("Grain temporel (source s1)")).toBeDisabled();
});

test("élargir le groupBy à plusieurs champs efface un bucket devenu invalide", () => {
  const onChange = vi.fn();
  const source: DataSource = {
    ...STATS_SOURCE,
    query: { groupBy: "region", agg: "count", bucket: "month" },
  };
  render(<DataSourcePanel sources={[source]} onChange={onChange} />);

  // fireEvent.change plutôt que userEvent.type : onChange est un espion sans
  // rerender ici, donc React restaure la valeur DOM contrôlée après chaque
  // frappe (même piège que les autres champs "Grouper par" de ce fichier).
  fireEvent.change(screen.getByLabelText("Grouper par (source s1)"), {
    target: { value: "region,city" },
  });
  expect(onChange).toHaveBeenLastCalledWith([
    { ...source, query: { groupBy: ["region", "city"], agg: "count", bucket: undefined } },
  ]);
});

test("vider ou sortir des bornes le champ centile ne produit jamais une requête percentile sans p", () => {
  // Revue finale SP-23 (I2) : `p: e.target.value ? Number(...) : undefined`
  // laissait partir `{agg: "percentile"}` sans `p`, que le cœur refuse
  // systématiquement en 422 — et la config restait enregistrable dans cet
  // état. Les deux champs centile (requête simple et par mesure) réutilisent
  // désormais PercentileInput, qui ne remonte que des valeurs valides.
  const onChange = vi.fn();
  const source: DataSource = {
    ...STATS_SOURCE,
    query: {
      groupBy: "region",
      agg: "percentile",
      p: 90,
      measures: [{ field: "pop", agg: "percentile", p: 75 }],
    },
  };
  render(<DataSourcePanel sources={[source]} onChange={onChange} />);

  for (const label of ["Centile (source s1)", "Centile mesure 1 (source s1)"]) {
    const input = screen.getByLabelText(label);
    for (const value of ["", "0", "100", "abc"]) {
      fireEvent.change(input, { target: { value } });
    }
  }

  expect(onChange).not.toHaveBeenCalled();

  // Une valeur valide, elle, remonte bien.
  fireEvent.change(screen.getByLabelText("Centile (source s1)"), { target: { value: "99" } });
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.p).toBe(99);
});
