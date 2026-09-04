// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { CollectionSchema, DataRecord, ItemClient } from "../api/types";
import {
  csvAvailable,
  csvTooLarge,
  downloadCsv,
  fetchRecordsForCsv,
  geojsonDownloadUrl,
  recordsToCsv,
  triggerCsvDownload,
} from "./datasetDownload";

test.each([
  [10000, true],
  [10001, false],
  [0, true],
  [null, false],
])("csvAvailable(%s) = %s", (count, expected) => {
  expect(csvAvailable(count)).toBe(expected);
});

// csvTooLarge is true only for a *known* count above the cap — a null (unknown)
// count is unavailable but not "too large", so the two predicates must diverge
// on null (guards against showing the "trop volumineux" message for an unknown
// count).
test.each([
  [10000, false],
  [10001, true],
  [0, false],
  [null, false],
])("csvTooLarge(%s) = %s", (count, expected) => {
  expect(csvTooLarge(count)).toBe(expected);
});

test("geojsonDownloadUrl delegates to client.featuresUrl with a synthetic features source capped at the server's max page size", () => {
  const client = {
    featuresUrl: vi.fn().mockReturnValue("https://core.test/collections/parcs/items?limit=1000"),
  };
  const url = geojsonDownloadUrl(client, "parcs");
  expect(client.featuresUrl).toHaveBeenCalledWith({
    id: expect.any(String),
    type: "features",
    service: "core",
    layer: "parcs",
    query: { limit: 1000 },
  });
  expect(url).toBe("https://core.test/collections/parcs/items?limit=1000");
});

test("fetchRecordsForCsv stops after a single page when the server returns fewer rows than requested", async () => {
  const queryPage = vi
    .fn<(offset: number, limit: number) => Promise<DataRecord[]>>()
    .mockResolvedValueOnce([{ id: 1, properties: {}, geometry: null }]);
  const records = await fetchRecordsForCsv(queryPage, 10000);
  expect(records).toHaveLength(1);
  expect(queryPage).toHaveBeenCalledTimes(1);
  expect(queryPage).toHaveBeenCalledWith(0, 1000);
});

test("fetchRecordsForCsv paginates across multiple full pages until totalCount is reached", async () => {
  const page1: DataRecord[] = Array.from({ length: 1000 }, (_, i) => ({
    id: i,
    properties: {},
    geometry: null,
  }));
  const page2: DataRecord[] = [{ id: 1000, properties: {}, geometry: null }];
  const queryPage = vi
    .fn<(offset: number, limit: number) => Promise<DataRecord[]>>()
    .mockResolvedValueOnce(page1)
    .mockResolvedValueOnce(page2);
  const records = await fetchRecordsForCsv(queryPage, 1001);
  expect(records).toHaveLength(1001);
  expect(queryPage).toHaveBeenNthCalledWith(1, 0, 1000);
  expect(queryPage).toHaveBeenNthCalledWith(2, 1000, 1);
});

test("fetchRecordsForCsv never fetches beyond the 10000-row CSV cap even when totalCount is larger", async () => {
  const bigPage: DataRecord[] = Array.from({ length: 1000 }, (_, i) => ({
    id: i,
    properties: {},
    geometry: null,
  }));
  const queryPage = vi
    .fn<(offset: number, limit: number) => Promise<DataRecord[]>>()
    .mockResolvedValue(bigPage);
  const records = await fetchRecordsForCsv(queryPage, 25000);
  expect(records).toHaveLength(10000);
  expect(queryPage).toHaveBeenCalledTimes(10);
  expect(queryPage).toHaveBeenLastCalledWith(9000, 1000);
});

const schema: CollectionSchema = {
  collection: "parcs",
  pk: "id",
  geometry: null,
  fields: [{ name: "nom", type: "string", required: true }],
};

test("recordsToCsv emits pk + schema fields + geometry columns, escaping commas/quotes/newlines", () => {
  const records: DataRecord[] = [
    { id: 1, properties: { nom: 'Parc, du "Test"' }, geometry: null },
    { id: 2, properties: { nom: "Bois" }, geometry: { type: "Point", coordinates: [1, 2] } },
  ];
  const csv = recordsToCsv(schema, records);
  expect(csv).toBe(
    "id,nom,geometry\r\n" +
      '1,"Parc, du ""Test""",\r\n' +
      '2,Bois,"{""type"":""Point"",""coordinates"":[1,2]}"',
  );
});

test("recordsToCsv renders an empty geometry cell when the record has no geometry", () => {
  const csv = recordsToCsv(schema, [{ id: 1, properties: { nom: "X" }, geometry: null }]);
  expect(csv).toBe("id,nom,geometry\r\n1,X,");
});

test("recordsToCsv omet les pseudo-champs attachment, qui n'ont pas de colonne réelle (revue finale, I3)", () => {
  const schemaWithAttachment: CollectionSchema = {
    ...schema,
    fields: [...schema.fields, { name: "photos", type: "attachment", required: false }],
  };
  const csv = recordsToCsv(schemaWithAttachment, [
    { id: 1, properties: { nom: "X" }, geometry: null },
  ]);
  // Sans le filtre, "photos" apparaîtrait comme colonne toujours vide
  // (aucune valeur dans properties pour un pseudo-champ sans colonne SQL).
  expect(csv).toBe("id,nom,geometry\r\n1,X,");
});

// jsdom (25.0.1) does not implement URL.createObjectURL/revokeObjectURL, and
// clicking a real <a> triggers jsdom's "Not implemented: navigation" — both
// must be stubbed before exercising the DOM-download side effect.
beforeEach(() => {
  Object.defineProperty(URL, "createObjectURL", {
    value: vi.fn(() => "blob:mock"),
    writable: true,
    configurable: true,
  });
  Object.defineProperty(URL, "revokeObjectURL", {
    value: vi.fn(),
    writable: true,
    configurable: true,
  });
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("triggerCsvDownload creates an object URL, clicks a download anchor, then revokes it", () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  triggerCsvDownload("parcs.csv", "id,nom\r\n1,X");
  expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  expect(clickSpy).toHaveBeenCalledTimes(1);
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock");
});

test("downloadCsv fetches bounded records via the client, builds the CSV, and triggers the download", async () => {
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const client: Pick<ItemClient, "queryDataSource"> = {
    queryDataSource: vi
      .fn()
      .mockResolvedValue([{ id: 1, properties: { nom: "Parc du Test" }, geometry: null }]),
  };
  await downloadCsv({ client, collectionId: "parcs", schema, featureCount: 1 });
  expect(client.queryDataSource).toHaveBeenCalledWith({
    id: expect.any(String),
    type: "features",
    service: "core",
    layer: "parcs",
    query: { limit: 1, offset: 0 },
  });
});
