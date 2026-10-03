// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { ifMatchHeader } from "./ifMatch";

test("ifMatchHeader : version connue → If-Match entre guillemets ; inconnue → aucun en-tête", () => {
  expect(ifMatchHeader(3)).toEqual({ "If-Match": '"3"' });
  expect(ifMatchHeader(0)).toEqual({ "If-Match": '"0"' });
  expect(ifMatchHeader(undefined)).toBeUndefined();
});
