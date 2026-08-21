// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { EMPTY_ANALYTICS_CONTEXT, type AnalyticsContextState } from "../builder/AnalyticsContext";
import { decodeAnalyticsContext, encodeAnalyticsContext } from "./analyticsContextUrl";

test("round-trips a full context through encode/decode", () => {
  const state: AnalyticsContextState = {
    timeRange: { from: "2026-01-01", to: "2026-02-01" },
    extent: [1, 2, 3, 4],
    crossFilter: { "ds-1": { field: "région", value: "Île-de-France", originSourceId: "src-1" } },
  };
  expect(decodeAnalyticsContext(encodeAnalyticsContext(state))).toEqual(state);
});

test("decodes null/missing raw as the empty context", () => {
  expect(decodeAnalyticsContext(null)).toEqual(EMPTY_ANALYTICS_CONTEXT);
});

test("decodes garbage as the empty context, never throws", () => {
  expect(decodeAnalyticsContext("%%%not-base64%%%")).toEqual(EMPTY_ANALYTICS_CONTEXT);
});

test("encoded output is URL-safe (no +, /, or = padding)", () => {
  const state: AnalyticsContextState = {
    timeRange: null,
    extent: null,
    crossFilter: { "ds-1": { field: "f", value: ["a", "b", "c"], originSourceId: "s" } },
  };
  const encoded = encodeAnalyticsContext(state);
  expect(encoded).not.toMatch(/[+/=]/);
});
