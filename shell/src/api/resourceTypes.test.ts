// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { RESOURCE_TYPE_LABELS, RESOURCE_TYPE_ORDER } from "./resourceTypes";

// Le vrai garde-fou d'exhaustivité est le type `Record<ResourceType, string>`
// lui-même : ajouter une valeur à ResourceType sans son libellé casse la
// compilation. Ce test verrouille en plus que l'ordre d'affichage couvre
// exactement les mêmes clés — un oubli qui, lui, compilerait.
test("l'ordre d'affichage couvre exactement les types étiquetés", () => {
  expect([...RESOURCE_TYPE_ORDER].sort()).toEqual(Object.keys(RESOURCE_TYPE_LABELS).sort());
});

test("les douze types de ressource sont étiquetés", () => {
  expect(RESOURCE_TYPE_ORDER).toHaveLength(12);
});
