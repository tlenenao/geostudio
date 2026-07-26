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
