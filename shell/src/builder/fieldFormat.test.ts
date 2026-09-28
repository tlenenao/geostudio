// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import { formatFieldValue } from "./fieldFormat";

test("formate un nombre en fr-FR", () => {
  // Le séparateur de milliers exact (U+202F, espace fine insécable) est un
  // détail d'implémentation ICU dépendant de la version de Node — comparé à
  // la sortie réelle de la même API plutôt qu'à un littéral, comme le fait
  // déjà le test de date ci-dessous, pour ne pas dépendre d'une version ICU
  // particulière (déviation du brief, qui donnait un littéral "1 234,5" à
  // espace normale — faux dans cet environnement, cf. rapport de tâche).
  expect(formatFieldValue(1234.5, "number")).toBe(new Intl.NumberFormat("fr-FR").format(1234.5));
});
test("formate une date en fr-FR", () => {
  expect(formatFieldValue("2026-09-27", "date")).toBe(
    new Intl.DateTimeFormat("fr-FR").format(new Date("2026-09-27")),
  );
});
test("passe une chaîne inchangée", () => {
  expect(formatFieldValue("abc", "string")).toBe("abc");
});
test("sans type de champ, comportement String() historique", () => {
  expect(formatFieldValue(42, undefined)).toBe("42");
});
test("une valeur null ou undefined reste une chaîne vide", () => {
  expect(formatFieldValue(null, "string")).toBe("");
  expect(formatFieldValue(undefined, "number")).toBe("");
});
test("un champ integer est aussi formaté en fr-FR", () => {
  expect(formatFieldValue(1234, "integer")).toBe(new Intl.NumberFormat("fr-FR").format(1234));
});
test("un champ datetime est aussi formaté en fr-FR", () => {
  expect(formatFieldValue("2026-09-27T10:00:00Z", "datetime")).toBe(
    new Intl.DateTimeFormat("fr-FR").format(new Date("2026-09-27T10:00:00Z")),
  );
});
