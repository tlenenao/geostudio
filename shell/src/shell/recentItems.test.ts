// SPDX-License-Identifier: Apache-2.0
import { beforeEach, expect, test } from "vitest";
import { readRecentItems, recordRecentItem } from "./recentItems";

beforeEach(() => localStorage.clear());

test("le plus récent d'abord, sans doublon, plafonné à 5", () => {
  for (const n of [1, 2, 3, 4, 5, 6])
    recordRecentItem({ pk: `p${n}`, type: "map", title: `T${n}` });
  recordRecentItem({ pk: "p4", type: "map", title: "T4" });
  expect(readRecentItems().map((r) => r.pk)).toEqual(["p4", "p6", "p5", "p3", "p2"]);
});

test("un stockage corrompu donne une liste vide", () => {
  localStorage.setItem("geostudio.recentItems", "{pas du json");
  expect(readRecentItems()).toEqual([]);
});
