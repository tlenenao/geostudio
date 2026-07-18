// SPDX-License-Identifier: Apache-2.0
import type { CollectionSchema, DataRecord, DataSource, ItemClient } from "../api/types";

const PAGE_SIZE = 1000;
const CSV_ROW_CAP = 10000;

export function csvAvailable(featureCount: number | null): boolean {
  return featureCount !== null && featureCount <= CSV_ROW_CAP;
}

// OGC API Features caps `limit` server-side at 1000 (core/app/features/routes.py
// MAX_LIMIT, verified while writing this plan) — a direct browser download of a
// collection with more features than that only returns the first page. Accepted
// v1 limitation: full exports beyond 1000 features wait on SP-15's server-side
// export. GeoJSON stays "always available" (unlike CSV, never disabled).
export function geojsonDownloadUrl(client: Pick<ItemClient, "featuresUrl">, collectionId: string): string {
  const source: DataSource = {
    id: `dataset-geojson-${collectionId}`, type: "features", service: "core",
    layer: collectionId, query: { limit: PAGE_SIZE },
  };
  return client.featuresUrl(source);
}

export async function fetchRecordsForCsv(
  queryPage: (offset: number, limit: number) => Promise<DataRecord[]>,
  totalCount: number,
): Promise<DataRecord[]> {
  const cap = Math.min(totalCount, CSV_ROW_CAP);
  const out: DataRecord[] = [];
  let offset = 0;
  while (offset < cap) {
    const limit = Math.min(PAGE_SIZE, cap - offset);
    const page = await queryPage(offset, limit);
    out.push(...page);
    offset += page.length;
    if (page.length < limit) break; // fewer than requested: no more data upstream
  }
  return out;
}

function csvEscape(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

export function recordsToCsv(schema: CollectionSchema, records: DataRecord[]): string {
  const columns = [schema.pk, ...schema.fields.map((f) => f.name), "geometry"];
  const lines = [columns.map(csvEscape).join(",")];
  for (const r of records) {
    const cells = columns.map((col) => {
      if (col === schema.pk) return csvEscape(String(r.id));
      if (col === "geometry") return csvEscape(r.geometry ? JSON.stringify(r.geometry) : "");
      const v = r.properties[col];
      return csvEscape(v === null || v === undefined ? "" : String(v));
    });
    lines.push(cells.join(","));
  }
  return lines.join("\r\n");
}

export function triggerCsvDownload(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function downloadCsv(opts: {
  client: Pick<ItemClient, "queryDataSource">;
  collectionId: string;
  schema: CollectionSchema;
  featureCount: number;
}): Promise<void> {
  const queryPage = (offset: number, limit: number) =>
    opts.client.queryDataSource({
      id: `dataset-csv-${opts.collectionId}`, type: "features", service: "core",
      layer: opts.collectionId, query: { limit, offset },
    });
  const records = await fetchRecordsForCsv(queryPage, opts.featureCount);
  const csv = recordsToCsv(opts.schema, records);
  triggerCsvDownload(`${opts.collectionId}.csv`, csv);
}
