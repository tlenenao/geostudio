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

// REV-080 : bg-white/text-white/bg-black/text-black n'ont pas de suffixe
// numérique de nuance (contrairement à bg-slate-900) — le motif d'origine
// exigeait `-\d{2,3}` et laissait donc passer ces quatre classes, précisément
// celles qui ont cassé l'ambiance sombre en SP-34. Chaque cas isolé (aucune
// autre classe de palette codée en dur dans le même `class=`) pour que le
// test falsifie réellement ce cas plutôt que de passer grâce à un voisin.
test("lève pour bg-white isolée", () => {
  const div = document.createElement("div");
  div.innerHTML = '<button class="bg-white">non</button>';
  expect(() => expectTokenizedClasses(div)).toThrow(/codée en dur/);
});

test("lève pour text-white isolée", () => {
  const div = document.createElement("div");
  div.innerHTML = '<button class="text-white">non</button>';
  expect(() => expectTokenizedClasses(div)).toThrow(/codée en dur/);
});

test("lève pour bg-black isolée", () => {
  const div = document.createElement("div");
  div.innerHTML = '<button class="bg-black">non</button>';
  expect(() => expectTokenizedClasses(div)).toThrow(/codée en dur/);
});

test("lève pour text-black isolée", () => {
  const div = document.createElement("div");
  div.innerHTML = '<button class="text-black">non</button>';
  expect(() => expectTokenizedClasses(div)).toThrow(/codée en dur/);
});
