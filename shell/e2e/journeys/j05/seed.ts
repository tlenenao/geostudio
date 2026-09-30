/* eslint-disable @typescript-eslint/no-explicit-any -- corps JSON du cœur, forme libre */
import { existsSync, readFileSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { stamp } from "../_fixtures/env";
import { psql } from "../j02/helpers";
import { apiFor, ingest } from "../j03/api";

export interface Seed {
  tag: string;
  eventsCollection: string;
  eventsItem: string;
  zonesCollection: string;
  zonesItem: string;
  tabCollection: string;
  tabZonesCollection: string;
  ventes: string;
  zonesRef: string;
}

const CACHE = join(tmpdir(), "aud-j05-seed.json");

// 60 événements : cat a/b/c (+ null), zone z1..z3, montant numérique (+ null), date ISO
// répartie sur 2025-2026, note contenant virgule/guillemet/retour ligne/formule.
export function eventsGeoJson(): Buffer {
  const features = Array.from({ length: 60 }, (_, i) => {
    const month = (i % 12) + 1;
    const props: Record<string, unknown> = {
      nom: `E${i}`,
      cat: i % 10 === 9 ? null : ["a", "b", "c"][i % 3],
      zone: `z${(i % 3) + 1}`,
      montant: i % 7 === 0 ? null : i * 10,
      date: `${i < 30 ? 2025 : 2026}-${String(month).padStart(2, "0")}-15T10:00:00Z`,
      note: i === 0 ? '=1+1,"cité"\nligne2' : i === 1 ? "@SUM(A1)" : `n${i}`,
    };
    return {
      type: "Feature",
      properties: props,
      geometry: { type: "Point", coordinates: [2 + (i % 10) * 0.1, 46 + Math.floor(i / 10) * 0.1] },
    };
  });
  return Buffer.from(JSON.stringify({ type: "FeatureCollection", features }));
}

export function zonesGeoJson(): Buffer {
  const features = ["z1", "z2", "z3", "z4"].map((z, i) => ({
    type: "Feature",
    properties: { zone: z, label: `Zone ${z}`, habitants: (i + 1) * 1000 },
    geometry: { type: "Point", coordinates: [2 + i * 0.5, 47] },
  }));
  return Buffer.from(JSON.stringify({ type: "FeatureCollection", features }));
}

function csvCell(v: unknown): string {
  if (v === null || v === undefined) return "";
  const s = String(v);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

// Versions tabulaires (sans géométrie) : SQL Lab ne sait pas lire une collection à
// géométrie (j05-001), ces deux tables servent donc aux parcours SQL et jointure.
export function eventsCsv(): Buffer {
  const feats = JSON.parse(eventsGeoJson().toString()).features as { properties: any }[];
  const cols = ["nom", "cat", "zone", "montant", "date", "note"];
  const lines = [cols.join(",")].concat(
    feats.map((f) => cols.map((c) => csvCell(f.properties[c])).join(",")),
  );
  return Buffer.from(lines.join("\n") + "\n");
}

export function zonesCsv(): Buffer {
  return Buffer.from(
    "zone,label,habitants\nz1,Zone z1,1000\nz2,Zone z2,2000\nz3,Zone z3,3000\nz4,Zone z4,4000\n",
  );
}

// Attend que le lac CDC ait absorbé la collection (cohérence à terme, j05-002).
export async function waitAnalytics(
  api: Awaited<ReturnType<typeof apiFor>>,
  collectionId: string,
  timeoutMs = 90_000,
): Promise<number> {
  const t0 = Date.now();
  for (;;) {
    const r = await api.send("POST", `/v1/collections/${collectionId}/aggregate`, { agg: "count" });
    const n = r.body?.rows?.[0]?.value;
    if (typeof n === "number" && n > 0) return Date.now() - t0;
    if (Date.now() - t0 > timeoutMs) throw new Error(`analytics vide: ${JSON.stringify(r)}`);
    await new Promise((res) => setTimeout(res, 2000));
  }
}

// Deux collections importées par API (rattrapage j03-001) et mises en cache disque.
export async function getSeed(): Promise<Seed> {
  const creator = await apiFor("creator");
  if (existsSync(CACHE)) {
    const cached = JSON.parse(readFileSync(CACHE, "utf8")) as Seed;
    const r = await creator.get(`/v1/items/${cached.eventsItem}`);
    if (r.status === 200) return cached;
  }
  const tag = stamp("j05");
  const ev = await ingest(creator, "events.geojson", eventsGeoJson(), {
    collectionTitle: `${tag}-events`,
  });
  if (ev.job?.status !== "done") throw new Error(`seed events: ${JSON.stringify(ev)}`);
  const zo = await ingest(creator, "zones.geojson", zonesGeoJson(), {
    collectionTitle: `${tag}-zones`,
  });
  if (zo.job?.status !== "done") throw new Error(`seed zones: ${JSON.stringify(zo)}`);
  const te = await ingest(creator, "events-tab.csv", eventsCsv(), {
    collectionTitle: `${tag}-tab-events`,
    geometryMode: "none",
  });
  if (te.job?.status !== "done") throw new Error(`seed tab events: ${JSON.stringify(te)}`);
  const tz = await ingest(creator, "zones-tab.csv", zonesCsv(), {
    collectionTitle: `${tag}-tab-zones`,
    geometryMode: "none",
  });
  if (tz.job?.status !== "done") throw new Error(`seed tab zones: ${JSON.stringify(tz)}`);
  for (const c of [ev, zo, te, tz]) {
    const r = await creator.send("PUT", `/v1/collections/${c.job.collectionId}/sharing`, {
      public: true,
      groups: [],
    });
    if (r.status !== 200) throw new Error(`sharing: ${JSON.stringify(r)}`);
  }
  await waitAnalytics(creator, te.job.collectionId);
  await waitAnalytics(creator, tz.job.collectionId);
  await waitAnalytics(creator, ev.job.collectionId);
  // Tables tabulaires TYPÉES : le POST /items est cassé (j02-003), on insère en SQL.
  const ventes = await creator.send("POST", "/v1/collections/empty", {
    title: `${tag}-ventes`,
    columns: [
      { name: "cat", sqlType: "text" },
      { name: "zone", sqlType: "text" },
      { name: "montant", sqlType: "double precision" },
      { name: "qte", sqlType: "integer" },
      { name: "d", sqlType: "timestamptz" },
      { name: "note", sqlType: "text" },
    ],
  });
  const zonesRef = await creator.send("POST", "/v1/collections/empty", {
    title: `${tag}-zones-ref`,
    columns: [
      { name: "zone", sqlType: "text" },
      { name: "label", sqlType: "text" },
      { name: "habitants", sqlType: "integer" },
    ],
  });
  if (ventes.status !== 201 || zonesRef.status !== 201) throw new Error("seed typed");
  const vt = ventes.body.id as string;
  const zr = zonesRef.body.id as string;
  const rows: string[] = [];
  for (let i = 0; i < 60; i++) {
    const cat = i % 10 === 9 ? "NULL" : `'${["a", "b", "c"][i % 3]}'`;
    const montant = i % 7 === 0 ? "NULL" : String(i * 10);
    const month = String((i % 12) + 1).padStart(2, "0");
    const note = i === 0 ? `'=1+1,"cité"\nligne2'` : i === 1 ? `'@SUM(A1)'` : `'n${i}'`;
    rows.push(
      `('default',${cat},'z${(i % 3) + 1}',${montant},${i % 5},'${i < 30 ? 2025 : 2026}-${month}-15T10:00:00Z',${note})`,
    );
  }
  psql(`INSERT INTO ${vt} (tenant_id,cat,zone,montant,qte,d,note) VALUES ${rows.join(",")}`);
  psql(
    `INSERT INTO ${zr} (tenant_id,zone,label,habitants) VALUES ('default','z1','Zone 1',1000),('default','z2','Zone 2',2000),('default','z3','Zone 3',3000),('default','z4','Zone 4',4000)`,
  );
  for (const id of [vt, zr]) {
    const r = await creator.send("PUT", `/v1/collections/${id}/sharing`, {
      public: true,
      groups: [],
    });
    if (r.status !== 200) throw new Error(`sharing: ${JSON.stringify(r)}`);
  }
  await waitAnalytics(creator, vt);
  await waitAnalytics(creator, zr);
  const seed: Seed = {
    tag,
    eventsCollection: ev.job.collectionId,
    eventsItem: ev.job.itemId,
    zonesCollection: zo.job.collectionId,
    zonesItem: zo.job.itemId,
    tabCollection: te.job.collectionId,
    tabZonesCollection: tz.job.collectionId,
    ventes: vt,
    zonesRef: zr,
  };
  writeFileSync(CACHE, JSON.stringify(seed));
  return seed;
}
