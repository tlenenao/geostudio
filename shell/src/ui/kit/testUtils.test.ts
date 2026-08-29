// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { expectTokenizedClasses } from "./testUtils";

test("ne lève rien pour des classes tokenisées", () => {
  const div = document.createElement("div");
  div.innerHTML = '<button class="bg-surface text-ink border-rule">ok</button>';
  expect(() => expectTokenizedClasses(div)).not.toThrow();
});

test("lève pour une classe de palette codée en dur", () => {
  const div = document.createElement("div");
  div.innerHTML = '<button class="bg-slate-900 text-white">non</button>';
  expect(() => expectTokenizedClasses(div)).toThrow(/codée en dur/);
});
