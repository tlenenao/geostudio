// SPDX-License-Identifier: Apache-2.0
// AUD-061 : le retard du lac est montré, mais seulement quand il est notable.
import { expect, test } from "vitest";
import { LAKE_LAG_NOTICE_MS, lakeNotice } from "./WidgetHost";

const NOW = Date.parse("2026-10-18T12:00:00Z");

test("aucune donnée de fraîcheur, aucun avis", () => {
  expect(lakeNotice(undefined, NOW)).toBeNull();
});

test("réplication pas encore faite : avis explicite (un agrégat vide n'est pas un zéro)", () => {
  expect(lakeNotice({ asOf: null, pending: true }, NOW)).toMatch(/Réplication en cours/);
});

test("lac récent : pas d'avis ; lac en retard : avis daté", () => {
  const fresh = new Date(NOW - 30_000).toISOString();
  expect(lakeNotice({ asOf: fresh, pending: false }, NOW)).toBeNull();
  const stale = new Date(NOW - LAKE_LAG_NOTICE_MS - 1000).toISOString();
  expect(lakeNotice({ asOf: stale, pending: false }, NOW)).toMatch(/en retard/);
});
