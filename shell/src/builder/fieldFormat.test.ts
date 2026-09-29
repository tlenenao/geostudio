// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { formatFieldValue } from "./fieldFormat";

// Revue finale Vague C (point 5) : les 2 premiers tests comparaient la
// sortie à un appel *identique* à celui testé (`new Intl.NumberFormat("fr-FR").format(...)`,
// `new Intl.DateTimeFormat("fr-FR").format(new Date(...))`) — tautologique,
// un bug partagé par l'implémentation et l'assertion aurait été invisible.
// Réécrits en valeurs littérales attendues. Le séparateur de milliers fr-FR
// (ICU récent) est U+202F (espace fine insécable), jamais une espace
// normale U+0020 — vérifié empiriquement, pas supposé.
const NBSP_NARROW = " ";

test("formate un nombre en fr-FR avec le séparateur de milliers réel", () => {
  expect(formatFieldValue(1234.5, "number")).toBe(`1${NBSP_NARROW}234,5`);
});
test("formate une date (type date) en fr-FR", () => {
  expect(formatFieldValue("2026-09-27", "date")).toBe("27/09/2026");
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
test("un champ integer non-année est aussi formaté en fr-FR avec séparateur", () => {
  // 123456 n'entre pas dans la plage d'année plausible (4 chiffres) : garde
  // son séparateur de milliers.
  expect(formatFieldValue(123456, "integer")).toBe(`123${NBSP_NARROW}456`);
});

// Point 5a : datetime doit conserver l'heure, pas seulement la date.
test("un champ datetime conserve la date ET l'heure (ne perd plus l'heure)", () => {
  const result = formatFieldValue("2026-09-27T10:00:00Z", "datetime");
  // Le fuseau du runtime de test influence l'heure locale affichée, jamais
  // sa présence : on vérifie donc la présence d'un composant heure
  // (`HH:MM:SS`) en plus de la date, sans figer un fuseau précis ici (la
  // dépendance au fuseau système est vérifiée séparément ci-dessous avec un
  // TZ explicite).
  expect(result).toMatch(/^\d{2}\/\d{2}\/\d{4} \d{2}:\d{2}:\d{2}$/);
});

// Point 5b : plus de troncature à 3 décimales pour une valeur géospatiale.
test("un nombre à forte précision (ex. coordonnée dérivée) n'est plus tronqué à 3 décimales", () => {
  expect(formatFieldValue(12.3456789, "number")).toBe("12,345679");
});
test("un nombre simple ne gagne pas de zéros de padding avec la précision relevée", () => {
  expect(formatFieldValue(3.5, "number")).toBe("3,5");
});

// Point 5d : un entier "année" ne reçoit pas de séparateur de milliers.
test("un entier à 4 chiffres plausible comme année n'a pas de séparateur de milliers", () => {
  expect(formatFieldValue(2024, "integer")).toBe("2024");
});
test("un champ number (pas integer) à 4 chiffres garde son séparateur (l'heuristique ne s'applique qu'à integer)", () => {
  expect(formatFieldValue(2024, "number")).toBe(`2${NBSP_NARROW}024`);
});

// Point 5c : parsing d'une date-seule (YYYY-MM-DD) sous un fuseau à
// décalage négatif — falsifié : `new Date("2026-09-27")` (minuit UTC)
// affiché sous America/New_York donnait "26/09/2026" avant le correctif
// (vérifié manuellement), jamais "27/09/2026".
//
// `DATE_FORMAT` est un singleton de module (coût de construction
// Intl.DateTimeFormat évité par ligne de tableau, perf perçue oblige) dont
// le fuseau résolu se fige à la *construction*, jamais rafraîchi ensuite
// (ECMA-402) — poser `process.env.TZ` après le premier import de
// fieldFormat.ts (déjà chargé par ce fichier de test, ligne 3) n'a donc
// strictement aucun effet observable ici : une première version de ce test
// (falsification faite AVANT d'écrire ce commentaire) posait juste
// `process.env.TZ` puis appelait `formatFieldValue` importé normalement —
// elle passait aussi bien avec le bug réintroduit qu'avec le correctif
// (singleton déjà lié à Europe/Paris avant la moindre falsification),
// prouvant qu'elle ne testait rien. `vi.resetModules()` + réimport
// dynamique force une nouvelle construction du singleton sous le nouveau
// TZ — vérifié qu'il détecte bien le bug (falsifié : "26/09/2026" avec la
// ligne de correctif retirée, "27/09/2026" restaurée).
test("une date-seule (YYYY-MM-DD) ne recule pas d'un jour sous un fuseau UTC négatif", async () => {
  process.env.TZ = "America/New_York";
  vi.resetModules();
  const reimported = await import("./fieldFormat");
  expect(reimported.formatFieldValue("2026-09-27", "date")).toBe("27/09/2026");
});

let originalTz: string | undefined;
beforeEach(() => {
  originalTz = process.env.TZ;
});
afterEach(() => {
  // `originalTz === undefined` (cas courant : TZ jamais posé par
  // l'environnement de test) ne doit pas réaffecter `process.env.TZ` —
  // Node convertit toute affectation en la chaîne littérale `"undefined"`
  // plutôt que de supprimer la variable, ce qui la laisserait posée à
  // tort pour les fichiers de test suivants.
  if (originalTz === undefined) {
    delete process.env.TZ;
  } else {
    process.env.TZ = originalTz;
  }
});
