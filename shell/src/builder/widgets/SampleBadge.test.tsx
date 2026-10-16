// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { expect, test } from "vitest";
import { SampleBadge, isSampled } from "./SampleBadge";

const rec = (n: number) => Array.from({ length: n }, (_, i) => ({ id: i, properties: {} }));
const feat = { id: "s", type: "features" as const, service: "core", layer: "c", query: {} };

test("badge affiché quand total > records et source features", () => {
  render(<SampleBadge data={{ records: rec(100), total: 5000, resolvedSource: feat }} />);
  expect(screen.getByRole("status")).toHaveTextContent("Échantillon : 100 sur 5000");
});
test("rien si total inconnu, complet, ou source statistics", () => {
  expect(isSampled({ records: rec(100), total: null })).toBe(false);
  expect(isSampled({ records: rec(100), total: 100 })).toBe(false);
  expect(
    isSampled({ records: rec(1), total: 9, resolvedSource: { ...feat, type: "statistics" } }),
  ).toBe(false);
});
