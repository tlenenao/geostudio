// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { TEMPLATES, getTemplate } from "./templates";

test("exposes the expected number of templates per kind", () => {
  expect(TEMPLATES.filter((t) => t.kind === "app")).toHaveLength(3);
  expect(TEMPLATES.filter((t) => t.kind === "dashboard")).toHaveLength(1);
  expect(TEMPLATES.filter((t) => t.kind === "site")).toHaveLength(1);
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
    from: tableItem.id, event: "itemSelected", to: formItem.id, action: "loadRecord",
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
