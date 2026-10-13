// SPDX-License-Identifier: Apache-2.0
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { beforeAll, expect, test } from "vitest";
import { TEMPLATES, getTemplate } from "./templates";
import { getWidget } from "./registry";
import { registerBuiltinWidgets } from "./widgets";

test("exposes the expected number of templates per kind", () => {
  expect(TEMPLATES.filter((t) => t.kind === "app")).toHaveLength(9);
  expect(TEMPLATES.filter((t) => t.kind === "dashboard")).toHaveLength(2);
  expect(TEMPLATES.filter((t) => t.kind === "site")).toHaveLength(2);
});

test("story cartographique template has 3 chapters each with a flyTo onEnter", () => {
  const story = getTemplate("story-cartographique");
  expect(story?.navigationMode).toBe("story");
  expect(story?.pages).toHaveLength(3);
  for (const page of story!.pages!) {
    expect(page.onEnter).toHaveLength(1);
    expect(page.onEnter![0].action).toBe("flyTo");
    expect(page.onEnter![0].payload).toHaveProperty("center");
  }
});

test("every template has at least one layout item", () => {
  for (const t of TEMPLATES) {
    expect(t.layout.items.length).toBeGreaterThan(0);
  }
});

test("getTemplate resolves a template by id", () => {
  const first = TEMPLATES[0];
  expect(getTemplate(first.id)).toBe(first);
});

test("getTemplate returns undefined for an unknown id", () => {
  expect(getTemplate("nope")).toBeUndefined();
});

test("application-de-saisie template wires a Formulaire, une Carte et une Table sur la même source", () => {
  const tpl = getTemplate("application-de-saisie")!;
  expect(tpl.kind).toBe("app");
  expect(tpl.dataSources).toHaveLength(1);
  const ds = tpl.dataSources![0];
  expect(ds).toMatchObject({ type: "features", service: "core", layer: "incidents" });
  const widgetTypes = tpl.layout.items.map((i) => i.widget).sort();
  expect(widgetTypes).toEqual(["form", "map", "table"]);
  tpl.layout.items.forEach((item) => {
    if (item.widget === "form" || item.widget === "map" || item.widget === "table") {
      expect(item.props.dataSourceId).toBe(ds.id);
    }
  });
  const formItem = tpl.layout.items.find((i) => i.widget === "form")!;
  expect(formItem.props.submitLabel).toBe("Déclarer l'incident");
  expect(tpl.messages).toHaveLength(1);
  const tableItem = tpl.layout.items.find((i) => i.widget === "table")!;
  expect(tpl.messages![0]).toMatchObject({
    from: tableItem.id,
    event: "itemSelected",
    to: formItem.id,
    action: "loadRecord",
  });
});

test("portail-de-donnees template wires Hero, Gallery, DatasetCard, and a Carte/Table demo on the same public collection", () => {
  const tpl = getTemplate("portail-de-donnees")!;
  expect(tpl.kind).toBe("site");
  expect(tpl.dataSources).toHaveLength(1);
  const ds = tpl.dataSources![0];
  expect(ds).toMatchObject({ type: "features", service: "core", layer: "incidents" });
  const widgetTypes = tpl.layout.items.map((i) => i.widget).sort();
  expect(widgetTypes).toEqual(["datasetCard", "gallery", "hero", "map", "table"]);
  for (const item of tpl.layout.items) {
    if (item.widget === "datasetCard" || item.widget === "map" || item.widget === "table") {
      expect(item.props.dataSourceId).toBe(ds.id);
    }
  }
});

test("les widgets d'un même type d'un modèle portent un ordinal croissant (nom stable après suppression)", () => {
  for (const t of TEMPLATES) {
    const seen = new Map<string, number[]>();
    for (const i of t.layout.items.filter((i) => i.widget === "text"))
      seen.set(i.widget, [...(seen.get(i.widget) ?? []), i.ordinal ?? 0]);
    for (const ords of seen.values()) expect(ords).toEqual(ords.map((_, k) => k + 1));
  }
});

// ARC-26 : 8 gabarits supplémentaires, des données déclaratives qui se
// vérifient mécaniquement (types de widgets connus, références de sources et
// de câblage résolues, ids uniques).
beforeAll(() => registerBuiltinWidgets());

const ARC26_IDS = [
  "tableau-de-bord-territorial",
  "suivi-de-chantier",
  "enquete-citoyenne",
  "observatoire-donnees-ouvertes",
  "comparateur-de-cartes",
  "galerie-de-fonds-de-carte",
  "fiches-d-entites",
  "atlas-par-entite",
];

test("les 8 gabarits ARC-26 sont au catalogue, avec un nom i18n", () => {
  for (const id of ARC26_IDS) {
    const tpl = getTemplate(id);
    expect(tpl, id).toBeDefined();
    expect(tpl!.name).not.toMatch(/^template\./);
  }
});

test.each(TEMPLATES.map((t) => [t.id, t] as const))(
  "gabarit %s : widgets connus, sources et câblage résolus, ids uniques",
  (_id, tpl) => {
    const layouts = tpl.pages ? tpl.pages.map((p) => p.layout) : [tpl.layout];
    const items = layouts.flatMap((l) => l.items);
    const ids = items.map((i) => i.id);
    expect(new Set(ids).size).toBe(ids.length);
    const dsIds = new Set((tpl.dataSources ?? []).map((d) => d.id));
    for (const item of items) {
      const def = getWidget(item.widget);
      expect(def, `widget ${item.widget}`).toBeDefined();
      if (item.props.dataSourceId) expect(dsIds.has(String(item.props.dataSourceId))).toBe(true);
    }
    for (const m of tpl.messages ?? []) {
      const from = items.find((i) => i.id === m.from);
      const to = items.find((i) => i.id === m.to);
      expect(from, `from ${m.from}`).toBeDefined();
      expect(to, `to ${m.to}`).toBeDefined();
      expect(getWidget(from!.widget)!.events ?? [], m.id).toContain(m.event);
      expect(getWidget(to!.widget)!.actions ?? [], m.id).toContain(m.action);
    }
  },
);

test("galerie de fonds de carte : câblée vers l'action setBasemap de la carte", () => {
  const tpl = getTemplate("galerie-de-fonds-de-carte")!;
  expect(tpl.messages).toEqual([
    expect.objectContaining({ event: "basemapChanged", action: "setBasemap" }),
  ]);
});

test("atlas-par-entite : printLayout.atlas pointe une source du gabarit", () => {
  const tpl = getTemplate("atlas-par-entite")!;
  const atlas = (tpl.printLayout as { atlas?: { dataSourceId: string; maxPages: number } }).atlas!;
  expect(tpl.dataSources!.map((d) => d.id)).toContain(atlas.dataSourceId);
  expect(atlas.maxPages).toBe(50);
});

test("la copie cœur des gabarits (create_item MCP) est identique aux données du shell", () => {
  const core = readFileSync(
    resolve(process.cwd(), "../core/app/configs/builder_templates.json"),
    "utf-8",
  );
  const shell = readFileSync(resolve(process.cwd(), "src/builder/templates.data.json"), "utf-8");
  expect(JSON.parse(core)).toEqual(JSON.parse(shell));
});
