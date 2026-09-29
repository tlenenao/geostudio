// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { formatCelError } from "./celError";

test("un message par ligne, préfixé", () => {
  expect(formatCelError("erreur A; erreur B")).toBe("• erreur A\n• erreur B");
});

test("un message unique reste préfixé sans saut de ligne superflu", () => {
  expect(formatCelError("erreur unique")).toBe("• erreur unique");
});
