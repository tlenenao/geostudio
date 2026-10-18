// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { inTimeWindow } from "./mapApplyLayers";

const range = { from: "2024-01-01", to: "2024-01-07" };

test("inTimeWindow : bornes inclusives, jour `to` entier, valeur absente exclue (AUD-049)", () => {
  expect(inTimeWindow({ d: "2024-01-01" }, "d", range)).toBe(true);
  expect(inTimeWindow({ d: "2024-01-07T18:30:00" }, "d", range)).toBe(true);
  expect(inTimeWindow({ d: "2024-01-08" }, "d", range)).toBe(false);
  expect(inTimeWindow({ d: "2023-12-31" }, "d", range)).toBe(false);
  expect(inTimeWindow({}, "d", range)).toBe(false);
  expect(inTimeWindow({}, "d", null)).toBe(true);
});
