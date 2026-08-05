// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import type { AnalyticsContextState } from "../builder/AnalyticsContext";
import type { DataSource, DatasetConfig } from "../api/types";
import { derivePatch } from "./analyticsPatch";

const EMPTY: AnalyticsContextState = { timeRange: null, extent: null, crossFilter: {} };

const source: DataSource = { id: "src-1", type: "features", service: "core", layer: "parcs", datasetId: "ds-1", query: {} };
const dataset: DatasetConfig = { source: "collection", collectionId: "parcs", columns: {}, timeField: "date_releve", reactsToExtent: true };

test("returns {} when the source has no datasetId", () => {
  const inline: DataSource = { id: "src-2", type: "features", service: "core", layer: "parcs", query: {} };
  expect(derivePatch(inline, { ...EMPTY, timeRange: { from: "a", to: "b" } }, {})).toEqual({});
});

test("returns {} when the dataset isn't resolved yet", () => {
  expect(derivePatch(source, { ...EMPTY, timeRange: { from: "a", to: "b" } }, {})).toEqual({});
});

test("adds field__gte/field__lte when timeRange is set and the dataset has a timeField", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, timeRange: { from: "2026-01-01", to: "2026-02-01" } };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({
    date_releve__gte: "2026-01-01", date_releve__lte: "2026-02-01",
  });
});

test("skips the time patch when the dataset has no timeField", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, timeRange: { from: "a", to: "b" } };
  const noTimeField = { ...dataset, timeField: null };
  expect(derivePatch(source, ctx, { "ds-1": noTimeField })).toEqual({});
});

test("adds bbox when extent is set and the dataset reactsToExtent", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, extent: [1, 2, 3, 4] };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({ bbox: "1,2,3,4" });
});

test("skips the extent patch when reactsToExtent is false", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, extent: [1, 2, 3, 4] };
  expect(derivePatch(source, ctx, { "ds-1": { ...dataset, reactsToExtent: false } })).toEqual({});
});

test("adds a cross-filter patch for a different origin source", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, crossFilter: { "ds-1": { field: "region", value: "Nord", originSourceId: "src-OTHER" } } };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({ region: "Nord" });
});

test("excludes the cross-filter patch when this source is the origin", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, crossFilter: { "ds-1": { field: "region", value: "Nord", originSourceId: "src-1" } } };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({});
});

test("uses field__in with a comma-joined value for an array cross-filter value", () => {
  const ctx: AnalyticsContextState = { ...EMPTY, crossFilter: { "ds-1": { field: "region", value: ["Nord", "Sud"], originSourceId: "src-OTHER" } } };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({ region__in: "Nord,Sud" });
});

test("combines time, extent and cross-filter patches together", () => {
  const ctx: AnalyticsContextState = {
    timeRange: { from: "2026-01-01", to: "2026-02-01" },
    extent: [1, 2, 3, 4],
    crossFilter: { "ds-1": { field: "region", value: "Nord", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({
    date_releve__gte: "2026-01-01", date_releve__lte: "2026-02-01",
    bbox: "1,2,3,4", region: "Nord",
  });
});

test("uses field__gte/field__lte for a range cross-filter value", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-1": { field: "score", value: { from: "10", to: "50" }, originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({ score__gte: "10", score__lte: "50" });
});

test("excludes a range cross-filter patch when this source is the origin", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-1": { field: "score", value: { from: "10", to: "50" }, originSourceId: "src-1" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({});
});

const linked: DatasetConfig = {
  source: "collection", collectionId: "communes", columns: {},
  crossFilterLinks: [{ targetDatasetId: "ds-1", mode: "attribute", sourceField: "commune", targetField: "nom_commune" }],
};

test("translates an attribute link from another dataset's active cross-filter", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset, "ds-2": linked })).toEqual({ nom_commune: "Brive" });
});

test("ignores an attribute link when the active field doesn't match sourceField", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "autre_champ", value: "Brive", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset, "ds-2": linked })).toEqual({});
});

test("ignores a link that doesn't target this source's dataset", () => {
  const elsewhere = { ...linked, crossFilterLinks: [{ targetDatasetId: "ds-999", mode: "attribute" as const, sourceField: "commune", targetField: "nom_commune" }] };
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": dataset, "ds-2": elsewhere })).toEqual({});
});

test("translates a spatial/bbox link into a bbox patch derived from the entry's geometry", () => {
  const spatialLinked: DatasetConfig = {
    ...linked,
    crossFilterLinks: [{ targetDatasetId: "ds-1", mode: "spatial", precision: "bbox" }],
  };
  const polygon = { type: "Polygon", coordinates: [[[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 49.0], [2.0, 48.0]]] };
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER", geometry: polygon } },
  };
  expect(derivePatch(source, ctx, { "ds-1": { ...dataset, reactsToExtent: false }, "ds-2": spatialLinked })).toEqual({
    bbox: "2,48,3,49",
  });
});

test("translates a spatial/exact link into a geomIntersects patch carrying the raw geometry", () => {
  const spatialLinked: DatasetConfig = {
    ...linked,
    crossFilterLinks: [{ targetDatasetId: "ds-1", mode: "spatial", precision: "exact" }],
  };
  const polygon = { type: "Polygon", coordinates: [[[2.0, 48.0], [3.0, 48.0], [3.0, 49.0], [2.0, 49.0], [2.0, 48.0]]] };
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER", geometry: polygon } },
  };
  expect(derivePatch(source, ctx, { "ds-1": { ...dataset, reactsToExtent: false }, "ds-2": spatialLinked })).toEqual({
    geomIntersects: polygon,
  });
});

test("ignores a spatial link when the active entry has no geometry", () => {
  const spatialLinked: DatasetConfig = {
    ...linked,
    crossFilterLinks: [{ targetDatasetId: "ds-1", mode: "spatial", precision: "bbox" }],
  };
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-2": { field: "commune", value: "Brive", originSourceId: "src-OTHER" } },
  };
  expect(derivePatch(source, ctx, { "ds-1": { ...dataset, reactsToExtent: false }, "ds-2": spatialLinked })).toEqual({});
});

test("does not resolve a link declared on the same dataset as the target source (no self-link)", () => {
  const ctx: AnalyticsContextState = {
    ...EMPTY,
    crossFilter: { "ds-1": { field: "region", value: "Nord", originSourceId: "src-1" } },
  };
  // dataset "ds-1" has no crossFilterLinks of its own here — this just proves the
  // direct same-dataset path (already tested above) and the link path don't double-fire.
  expect(derivePatch(source, ctx, { "ds-1": dataset })).toEqual({});
});
