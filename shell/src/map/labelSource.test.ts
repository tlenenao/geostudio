// SPDX-License-Identifier: Apache-2.0
import { expect, test, vi } from "vitest";
import { buildLabelFeatureCollection } from "./labelSource";

const point = (lng: number, lat: number) => ({
  type: "Point" as const,
  coordinates: [lng, lat],
});

test("interpole un gabarit mono-champ par entité", () => {
  const fc = buildLabelFeatureCollection(
    [
      { id: 1, properties: { nom: "Tulle" }, geometry: point(1, 2) },
      { id: 2, properties: { nom: "Brive" }, geometry: point(3, 4) },
    ],
    "${record.nom}",
  );
  expect(fc.type).toBe("FeatureCollection");
  expect(fc.features.map((f) => f.properties.label)).toEqual(["Tulle", "Brive"]);
  expect(fc.features[0].geometry).toEqual(point(1, 2));
});

test("évalue une condition CEL complète par entité", () => {
  const fc = buildLabelFeatureCollection(
    [
      { id: 1, properties: { nom: "Tulle", pop: 15000 }, geometry: point(1, 2) },
      { id: 2, properties: { nom: "Hameau", pop: 40 }, geometry: point(3, 4) },
    ],
    '${record.pop > 10000 ? "grande ville" : "commune"}',
  );
  expect(fc.features.map((f) => f.properties.label)).toEqual(["grande ville", "commune"]);
});

test("un gabarit multi-champs est conservé tel quel", () => {
  const fc = buildLabelFeatureCollection(
    [{ id: 1, properties: { nom: "Tulle", pop: 14000 }, geometry: point(1, 2) }],
    "${record.nom} (${record.pop})",
  );
  expect(fc.features[0].properties.label).toBe("Tulle (14000)");
});

test("une propriété absente donne une chaîne vide, jamais une exception", () => {
  const fc = buildLabelFeatureCollection(
    [{ id: 1, properties: {}, geometry: point(1, 2) }],
    "${record.nom}",
  );
  expect(fc.features).toEqual([]);
});

test("du texte littéral sans placeholder passe tel quel", () => {
  const fc = buildLabelFeatureCollection(
    [{ id: 1, properties: {}, geometry: point(1, 2) }],
    "Sans donnée",
  );
  expect(fc.features[0].properties.label).toBe("Sans donnée");
});

// querySourceFeatures renvoie un morceau d'entité PAR TUILE : sans
// déduplication, une commune à cheval sur quatre tuiles reçoit quatre
// étiquettes superposées.
test("déduplique par id d'entité", () => {
  const fc = buildLabelFeatureCollection(
    [
      { id: 19108, properties: { nom: "Tulle" }, geometry: point(1, 2) },
      { id: 19108, properties: { nom: "Tulle" }, geometry: point(1.001, 2.001) },
    ],
    "${record.nom}",
  );
  expect(fc.features).toHaveLength(1);
});

test("déduplique par colonne de clé primaire quand l'id de tuile est absent", () => {
  const fc = buildLabelFeatureCollection(
    [
      { id: undefined, properties: { code: "19272", nom: "Tulle" }, geometry: point(1, 2) },
      { id: undefined, properties: { code: "19272", nom: "Tulle" }, geometry: point(1.1, 2.1) },
      { id: undefined, properties: { code: "19031", nom: "Brive" }, geometry: point(5, 6) },
    ],
    "${record.nom}",
    { pkColumn: "code" },
  );
  expect(fc.features.map((f) => f.properties.label)).toEqual(["Tulle", "Brive"]);
});

// Constat N4 : sans plafond, une couche dense fait payer nb_entités x
// nb_placeholders lex+parse CEL par rafraîchissement, dans le thread principal.
test("plafonne le nombre d'étiquettes et n'avertit qu'une fois", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  const many = Array.from({ length: 5 }, (_, i) => ({
    id: i,
    properties: { nom: `C${i}` },
    geometry: point(i, i),
  }));
  const fc = buildLabelFeatureCollection(many, "${record.nom}", { maxFeatures: 2 });
  expect(fc.features).toHaveLength(2);
  expect(warn).toHaveBeenCalledTimes(1);
  expect(warn.mock.calls[0][0]).toContain("3 entités ignorées");
  warn.mockRestore();
});

// Un avertissement AGRÉGÉ, pas un par entité : cel-js lève sur une propriété
// absente et evaluateExpression journalise à chaque appel.
test("n'émet qu'un seul avertissement pour toutes les entités sans étiquette", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  const fc = buildLabelFeatureCollection(
    [
      { id: 1, properties: {}, geometry: point(1, 1) },
      { id: 2, properties: {}, geometry: point(2, 2) },
      { id: 3, properties: { nom: "Tulle" }, geometry: point(3, 3) },
    ],
    "${record.nom}",
  );
  expect(fc.features.map((f) => f.properties.label)).toEqual(["Tulle"]);
  // Les warnings de evaluateExpression lui-même comptent aussi : n'asserter
  // que sur la ligne agrégée de labelSource, pas sur le total.
  const aggregated = warn.mock.calls.filter((c) => String(c[0]).startsWith("labelSource:"));
  expect(aggregated).toHaveLength(1);
  expect(String(aggregated[0][0])).toContain("2 entités");
  warn.mockRestore();
});

test("ignore une entité sans géométrie", () => {
  const fc = buildLabelFeatureCollection(
    [{ id: 1, properties: { nom: "Tulle" }, geometry: undefined }],
    "${record.nom}",
  );
  expect(fc.features).toEqual([]);
});
